"""Daily posts on @raiz.connect through Meta's official API (instagram_content_publish), authorized by Matheus on
13/10 ("1 por dia, nas legendas não use emoticons"). The calendar lives in /a0/usr/conteudo/agenda.json and only
changes through this file: agendar() validates, the job loop publishes what is due, and every state change goes
through _mudar() (TRANSICOES) and lands in the journal. Rules that are code, not text:
- at most one post per day (BRT), never twice the same item;
- captions without emoji, at most 2200 characters and 30 hashtags;
- a post whose publish call was made but not confirmed becomes "incerta" and is never retried by itself;
- 20/10: when the especialistas plugin exists, the Crítico judges each post right before it goes out; "reprova" or any
  error blocks it ("bloqueada", fail closed) until Matheus releases it (liberar(), his override is recorded);
- 22/10: each post is judged up to CONFERIR_HORAS before (conferir_antes), a reproved one is redone by the agent and
  judged again, and at the hour an approval of the same files and caption (impressao) is the gate."""

import datetime as dt
import fcntl
import importlib.util
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path

PASTA = Path(os.environ.get("CONTEUDO_PASTA", "/a0/usr/conteudo"))
BUCKET = "agentepessoal-backup-964862484412"
PREFIXO = "conteudo/"
GRAPH = "https://graph.facebook.com/v25.0"
PROXY = "http://host.docker.internal:8787"  # host proxy: the only holder of AWS credentials
FUSO = "America/Sao_Paulo"
TIPOS = ("REELS", "CARROSSEL", "IMAGE", "STORY")  # IMAGE: one feed photo (17/10: Matheus wanted the iFood art as a photo, not a still Reel)
# STORY (22/10, Matheus: "story sim todo dia"): one .jpg or one .mp4, 1080x1920; the Graph API takes no caption,
# poll, link or music on a story. A story has its own slot: one feed post and one story a day.
JPG = (".jpg", ".jpeg")  # the Graph API takes JPEG only for images
MAX_LEGENDA, MAX_HASHTAGS, MAX_CARROSSEL = 2200, 30, 10
CAPA_MS = 1500  # Reel cover frame when no cover image is given (ms)
ESPERA_PROCESSAR = 600  # seconds Meta may take to process a video before we give up
AUTOR = {"quem": "agente"}  # operator scripts set "operador: <why>"
LOGIN = "matheus"
# the Crítico (plugins/especialistas): next to this plugin, else the installed one (a staging copy alone in /tmp)
ESPECIALISTAS = (Path(__file__).resolve().parents[2] / "especialistas" / "helpers" / "especialistas.py",
                 Path("/a0/usr/plugins/especialistas/helpers/especialistas.py"))

# any pictograph, dingbat, arrow-ish symbol or emoji joiner: Matheus wants plain text captions
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U0001F900-\U0001F9FF☀-➿⬀-⯿←-⇿️‍⃣]")

TRANSICOES = {
    "pendente": {"publicando", "cancelada", "bloqueada"},
    "bloqueada": {"pendente", "cancelada"},  # the Crítico's gate stopped it; back to pendente only by liberar()
    "publicando": {"publicada", "falhou", "incerta"},
    "incerta": {"publicada", "falhou"},  # checked on the profile by a person before anything else
    "publicada": set(), "falhou": {"pendente"}, "cancelada": set(),  # falhou → pendente only by the operator
}


class TransicaoInvalida(ValueError):
    pass


def _tz():
    from zoneinfo import ZoneInfo
    return ZoneInfo(FUSO)


def _arq() -> Path:
    return PASTA / "agenda.json"


@contextmanager
def _exclusivo():
    PASTA.mkdir(parents=True, exist_ok=True)
    with open(PASTA / "agenda.lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def carregar() -> dict:
    arq = _arq()
    if not arq.exists():
        return {"itens": []}
    d = json.loads(arq.read_text(encoding="utf-8"))  # unreadable: raise, never start empty
    if not isinstance(d, dict) or not isinstance(d.get("itens"), list):
        raise ValueError("agenda.json ilegível")
    return d


def _gravar(d: dict) -> None:
    tmp = _arq().with_suffix(f".{os.getpid()}.{time.time_ns()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, _arq())


def _diario(evento: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    with open(PASTA / "diario.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"em": time.time(), "quem": AUTOR["quem"], **evento}, ensure_ascii=False) + "\n")


def _mudar(item: dict, para: str, **campos) -> None:
    de = item["estado"]
    if para not in TRANSICOES.get(de, set()):
        raise TransicaoInvalida(f"{item['id']}: {de} → {para} não é permitido")
    item["estado"] = para
    item.update(campos)
    item["mudou_em"] = time.time()
    _diario({"item": item["id"], "de": de, "para": para, **{k: v for k, v in campos.items() if k != "legenda"}})


# ------------------------------------------------------------------ rules

def validar_legenda(texto: str) -> str:
    """'' when fine, else why not."""
    texto = str(texto or "").strip()
    if not texto:
        return "legenda vazia"
    if EMOJI.search(texto):
        return "a legenda tem emoji (o Matheus pediu legendas sem emoticons)"
    if len(texto) > MAX_LEGENDA:
        return f"legenda com {len(texto)} caracteres (máximo {MAX_LEGENDA})"
    if len(re.findall(r"#\w+", texto)) > MAX_HASHTAGS:
        return f"mais de {MAX_HASHTAGS} hashtags"
    return ""


def canal(it: dict) -> str:
    """"story" or "feed": each has its own one-a-day slot."""
    return "story" if it.get("tipo") == "STORY" else "feed"


def _validar_item(it: dict) -> str:
    try:
        dt.date.fromisoformat(str(it.get("data")))
        h, m = str(it.get("hora", "")).split(":")
        if not (0 <= int(h) < 24 and 0 <= int(m) < 60):
            raise ValueError
    except Exception:
        return "data (AAAA-MM-DD) ou hora (HH:MM) inválida"
    if it.get("tipo") not in TIPOS:
        return f"tipo deve ser {' ou '.join(TIPOS)}"
    arqs = it.get("arquivos") or []
    if not arqs or not all(isinstance(a, str) and a.startswith(PREFIXO) for a in arqs):
        return f"arquivos: chaves do S3 começando por {PREFIXO}"
    if it["tipo"] == "REELS" and (len(arqs) != 1 or not arqs[0].lower().endswith(".mp4")):
        return "Reel: um único .mp4"
    if it["tipo"] == "STORY" and (len(arqs) != 1 or not arqs[0].lower().endswith(JPG + (".mp4",))):
        return "story: uma única .jpg ou .mp4"
    if it["tipo"] == "IMAGE" and (len(arqs) != 1 or not arqs[0].lower().endswith(JPG)):
        return "foto (IMAGE): uma única imagem .jpg"
    capa = it.get("capa")
    if capa and (it["tipo"] != "REELS" or not str(capa).startswith(PREFIXO) or not str(capa).lower().endswith(JPG)):
        return f"capa: só em Reel, uma .jpg do S3 começando por {PREFIXO}"
    if it["tipo"] == "IMAGE" and it.get("capa_ms"):
        return "capa_ms: só em Reel"
    if it["tipo"] == "CARROSSEL" and not (2 <= len(arqs) <= MAX_CARROSSEL and all(a.lower().endswith(JPG) for a in arqs)):
        return f"carrossel: de 2 a {MAX_CARROSSEL} imagens .jpg"
    for campo in ("origem", "liberado"):
        if campo in it and not isinstance(it[campo], dict):
            return f"{campo}: objeto"
    if it["tipo"] == "STORY":  # no caption goes out on a story; "legenda" is only what it is about (for the Crítico)
        texto = str(it.get("legenda") or "").strip()
        return "" if not texto else ("a descrição do story tem emoji" if EMOJI.search(texto) else "")
    return validar_legenda(it.get("legenda", ""))


def agendar(itens: list, agora: float | None = None) -> dict:
    """Adds posts to the calendar. All or nothing: any invalid item refuses the whole batch."""
    agora = time.time() if agora is None else agora
    hoje = dt.datetime.fromtimestamp(agora, _tz()).date().isoformat()
    with _exclusivo():
        d = carregar()
        ocupadas = {(i["data"], canal(i)) for i in d["itens"] if i["estado"] not in ("cancelada", "falhou")}
        ids = {i["id"] for i in d["itens"]}
        novos = []
        for it in itens:
            erro = _validar_item(it)
            if not erro and it["data"] < hoje:
                erro = "data no passado"
            if not erro and ((it["data"], canal(it)) in ocupadas or (it["data"], canal(it)) in {(n["data"], canal(n)) for n in novos}):
                erro = f"já existe {'story' if canal(it) == 'story' else 'post'} para {it['data']} (um por dia)"
            if not erro and (not it.get("id") or it["id"] in ids or it["id"] in {n["id"] for n in novos}):
                erro = "id vazio ou repetido"
            if erro:
                return {"ok": False, "erro": f"{it.get('id', '?')}: {erro}"}
            novos.append({"id": it["id"], "data": it["data"], "hora": it["hora"], "tipo": it["tipo"],
                          "arquivos": list(it["arquivos"]), "legenda": str(it.get("legenda") or "").strip(), "estado": "pendente",
                          "criado_em": agora,
                          **{k: it[k] for k in ("capa", "capa_ms", "origem", "liberado") if it.get(k)}})
        d["itens"].extend(novos)
        _gravar(d)
        for n in novos:
            _diario({"item": n["id"], "para": "pendente", "data": n["data"], "hora": n["hora"], "tipo": n["tipo"]})
    return {"ok": True, "agendados": [n["id"] for n in novos]}


def tentar_de_novo(item_id: str) -> dict:
    """falhou → pendente, only by the operator (AUTOR "operador: <why>") after the cause is fixed. The job loop then
    publishes it on its next pass if it is still that post's day and nothing else went out that day."""
    if not str(AUTOR["quem"]).startswith("operador:"):
        return {"ok": False, "erro": "só o operador manda tentar de novo (AUTOR['quem'] = 'operador: <motivo>')"}
    with _exclusivo():
        d = carregar()
        alvo = next((i for i in d["itens"] if i["id"] == item_id), None)
        if not alvo:
            return {"ok": False, "erro": f"{item_id}: não existe"}
        try:
            _mudar(alvo, "pendente", erro_anterior=alvo.get("erro", ""))
        except TransicaoInvalida as exc:
            return {"ok": False, "erro": str(exc)}
        alvo.pop("erro", None)
        _gravar(d)
    return {"ok": True, "id": item_id, "data": alvo["data"], "hora": alvo["hora"]}


def cancelar(item_id: str, motivo: str = "") -> dict:
    """pendente → cancelada, only by the operator (14/10: the old brigadeiro Reel is replaced by the kit version and
    replanejar() cannot change the files). The day becomes free for agendar(); nothing published is ever touched."""
    if not str(AUTOR["quem"]).startswith("operador:"):
        return {"ok": False, "erro": "só o operador cancela um post (AUTOR['quem'] = 'operador: <motivo>')"}
    with _exclusivo():
        d = carregar()
        alvo = next((i for i in d["itens"] if i["id"] == item_id), None)
        if not alvo:
            return {"ok": False, "erro": f"{item_id}: não existe"}
        try:
            _mudar(alvo, "cancelada", motivo=str(motivo)[:200])
        except TransicaoInvalida as exc:
            return {"ok": False, "erro": str(exc)}
        _gravar(d)
    return {"ok": True, "id": item_id, "data": alvo["data"]}


def adiar_a_partir(data: str, dias: int = 1, agora: float | None = None) -> dict:
    """Moves every pending post on `data` or later `dias` days ahead, keeping their order and hour (13/10: Matheus put a
    new video on the 14th and wanted the rest to skip a day). Only the operator; nothing is published or cancelled.
    Refuses when a moved post would land on a day already taken by a post that is not moving."""
    if not str(AUTOR["quem"]).startswith("operador:"):
        return {"ok": False, "erro": "só o operador remarca a agenda (AUTOR['quem'] = 'operador: <motivo>')"}
    try:
        inicio = dt.date.fromisoformat(str(data))
    except ValueError:
        return {"ok": False, "erro": "data (AAAA-MM-DD) inválida"}
    if int(dias) < 1:
        return {"ok": False, "erro": "dias tem de ser 1 ou mais"}
    agora = time.time() if agora is None else agora
    if inicio < dt.datetime.fromtimestamp(agora, _tz()).date():
        return {"ok": False, "erro": "data no passado"}
    with _exclusivo():
        d = carregar()
        mover = [i for i in d["itens"] if i["estado"] == "pendente" and i["data"] >= inicio.isoformat()]
        # one feed post and one story a day: a moved item only collides with a fixed one of the same slot
        fixos = {(i["data"], canal(i)) for i in d["itens"] if i not in mover and i["estado"] not in ("cancelada", "falhou")}
        novas = {i["id"]: (dt.date.fromisoformat(i["data"]) + dt.timedelta(days=int(dias))).isoformat() for i in mover}
        choque = sorted({data for data, can in {(novas[i["id"]], canal(i)) for i in mover} & fixos})
        if choque:
            return {"ok": False, "erro": f"cairia em dia já ocupado: {', '.join(choque)}"}
        for i in mover:
            antes = i["data"]
            i["data"] = novas[i["id"]]
            _diario({"item": i["id"], "remarcado": True, "de_data": antes, "para_data": i["data"]})
        _gravar(d)
    return {"ok": True, "movidos": {i["id"]: i["data"] for i in mover}}


def replanejar(mudancas: list, agora: float | None = None) -> dict:
    """Changes the day, caption and/or Reel cover of pending posts in one go: [{"id", "data"?, "legenda"?, "capa"?, "capa_ms"?}] (14/10: Matheus asked
    to redo the week around the new offer, which swaps days and rewrites captions). Only the operator; all or
    nothing; the final calendar must still have one post per day, no day in the past and only valid captions."""
    if not str(AUTOR["quem"]).startswith("operador:"):
        return {"ok": False, "erro": "só o operador replaneja a agenda (AUTOR['quem'] = 'operador: <motivo>')"}
    agora = time.time() if agora is None else agora
    hoje = dt.datetime.fromtimestamp(agora, _tz()).date().isoformat()
    with _exclusivo():
        d = carregar()
        por_id = {i["id"]: i for i in d["itens"]}
        novo = {}
        for m in mudancas:
            it = por_id.get(m.get("id"))
            if not it:
                return {"ok": False, "erro": f"{m.get('id')}: não existe"}
            if it["estado"] != "pendente":
                return {"ok": False, "erro": f"{it['id']}: só post pendente muda (está {it['estado']})"}
            if it["id"] in novo:
                return {"ok": False, "erro": f"{it['id']}: repetido na lista"}
            alvo = dict(it, **{k: m[k] for k in ("data", "legenda", "capa", "capa_ms") if k in m})
            alvo["legenda"] = str(alvo.get("legenda", "")).strip()
            erro = _validar_item(alvo) or ("data no passado" if alvo["data"] < hoje else "")
            if erro:
                return {"ok": False, "erro": f"{it['id']}: {erro}"}
            novo[it["id"]] = alvo
        dias = {}
        for i in d["itens"]:
            final = novo.get(i["id"], i)
            if final["estado"] in ("cancelada", "falhou"):
                continue
            vaga = (final["data"], canal(final))  # one feed post and one story a day
            if vaga in dias:
                return {"ok": False, "erro": f"dois {'stories' if vaga[1] == 'story' else 'posts'} em {final['data']}: "
                                             f"{dias[vaga]} e {i['id']}"}
            dias[vaga] = i["id"]
        for i in d["itens"]:
            if i["id"] not in novo:
                continue
            antes = dict(i)
            i.update(data=novo[i["id"]]["data"], legenda=novo[i["id"]]["legenda"],
                     **{k: novo[i["id"]][k] for k in ("capa", "capa_ms") if novo[i["id"]].get(k)})
            _diario({"item": i["id"], "replanejado": True, "de_data": antes["data"], "para_data": i["data"],
                     "legenda_mudou": antes.get("legenda") != i["legenda"]})
        _gravar(d)
    return {"ok": True, "agenda": {i["id"]: i["data"] for i in d["itens"] if i["id"] in novo}}


def trocar_formato(item_id: str, tipo: str, arquivos: list, capa: str = "", agora: float | None = None) -> dict:
    """Swaps the format and files of ONE pending post, keeping its id, day, hour, caption, state and creation time
    (17/10: the iFood post was a still Reel and Matheus wanted a single feed photo). Only the operator; the old
    Reel cover (capa/capa_ms) goes away unless the new format is a Reel with a new capa. Before writing, an exact copy
    of agenda.json is saved next to it, inside the same lock. Files in S3 are never touched."""
    if not str(AUTOR["quem"]).startswith("operador:"):
        return {"ok": False, "erro": "só o operador troca o formato (AUTOR['quem'] = 'operador: <motivo>')"}
    agora = time.time() if agora is None else agora
    hoje = dt.datetime.fromtimestamp(agora, _tz()).date().isoformat()
    with _exclusivo():
        bruto = _arq().read_bytes() if _arq().exists() else b""
        d = carregar()
        alvo = next((i for i in d["itens"] if i["id"] == item_id), None)
        if not alvo:
            return {"ok": False, "erro": f"{item_id}: não existe"}
        if alvo["estado"] != "pendente":
            return {"ok": False, "erro": f"{item_id}: só post pendente muda (está {alvo['estado']})"}
        novo = {k: v for k, v in alvo.items() if k not in ("capa", "capa_ms")}
        novo.update(tipo=tipo, arquivos=list(arquivos or []), **({"capa": capa} if capa else {}))
        erro = _validar_item(novo) or ("data no passado" if novo["data"] < hoje else "")
        if erro:
            return {"ok": False, "erro": f"{item_id}: {erro}"}
        if novo == alvo:  # already in this format: write nothing, log nothing
            return {"ok": True, "id": item_id, "tipo": tipo, "arquivos": novo["arquivos"], "sem_mudanca": True}
        copia = PASTA / f"agenda.backup-formato-{item_id}-{time.strftime('%Y%m%d-%H%M%S', time.localtime(agora))}.json"
        copia.write_bytes(bruto)
        antes = {k: alvo.get(k) for k in ("tipo", "arquivos", "capa", "capa_ms") if k in alvo}
        alvo.clear()
        alvo.update(novo)
        _gravar(d)
        _diario({"item": item_id, "formato_trocado": True, "de_formato": antes,
                 "para_formato": {k: novo[k] for k in ("tipo", "arquivos", "capa") if k in novo}})
    return {"ok": True, "id": item_id, "tipo": tipo, "arquivos": novo["arquivos"], "backup": str(copia)}


def devido(agora: float | None = None) -> dict | None:
    """Today's post (or story) when its hour has come, unless one of the same slot was already published or
    attempted today."""
    agora = time.time() if agora is None else agora
    momento = dt.datetime.fromtimestamp(agora, _tz())
    hoje, hora = momento.date().isoformat(), momento.strftime("%H:%M")
    d = carregar()
    do_dia = [i for i in d["itens"] if i["data"] == hoje]
    feitos = {canal(i) for i in do_dia if i["estado"] in ("publicando", "publicada", "incerta")}
    return next((i for i in sorted(do_dia, key=lambda i: i["hora"])
                 if i["estado"] == "pendente" and i["hora"] <= hora and canal(i) not in feitos), None)


# ------------------------------------------------------------------ publishing

class Api:
    """The real Graph API with the Page token from the vault; media served by short-lived S3 links."""

    def __init__(self, token: str, ig: str):
        self.token, self.ig = token, ig

    def _pedir(self, metodo: str, caminho: str, params: dict) -> dict:
        import urllib.error
        import urllib.parse
        import urllib.request
        dados = urllib.parse.urlencode({**params, "access_token": self.token})
        if metodo == "GET":
            req = urllib.request.Request(f"{GRAPH}/{caminho}?{dados}")
        else:
            req = urllib.request.Request(f"{GRAPH}/{caminho}", data=dados.encode(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read())
            except Exception:
                return {"error": {"message": f"http {e.code}"}}

    def post(self, caminho, params):
        return self._pedir("POST", caminho, params)

    def get(self, caminho, params):
        return self._pedir("GET", caminho, params)

    def url(self, chave: str) -> str:
        """Short-lived S3 link from the host proxy, which holds the VM's AWS identity: the agent container has
        none (13/10: s1-pov failed with "Unable to locate credentials")."""
        import urllib.error
        import urllib.request
        req = urllib.request.Request(f"{PROXY}/arquivos/conteudo", data=json.dumps({"chave": chave}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                out = json.loads(e.read())
            except Exception:
                out = {"error": f"http {e.code}"}
        except OSError as e:
            out = {"error": f"proxy fora do ar ({e})"}
        if not out.get("url"):
            raise RuntimeError(f"link do arquivo {chave}: {out.get('error', 'sem resposta')}")
        return out["url"]


def _ok(r: dict, etapa: str) -> dict:
    if not isinstance(r, dict) or r.get("error") or not r.get("id"):
        msg = (r or {}).get("error", {}).get("message", "sem resposta") if isinstance(r, dict) else "sem resposta"
        raise RuntimeError(f"{etapa}: {msg[:200]}")
    return r


def _esperar_pronto(api, cid: str, dormir=time.sleep) -> None:
    limite = time.time() + ESPERA_PROCESSAR
    while True:
        st = api.get(cid, {"fields": "status_code"}).get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"a Meta recusou o arquivo ({st})")
        if time.time() > limite:
            raise RuntimeError("a Meta não terminou de processar o arquivo em 10 min")
        dormir(10)


def preparar(item: dict, api, dormir=time.sleep) -> str:
    """Creates the media container(s) and waits until Meta has processed them. Nothing is public yet."""
    ig = api.ig
    if item["tipo"] == "REELS":
        # 14/10: with no cover Meta took the first frame, and the "Raiz invisível" Reel opens on black: a black square
        # in the grid. A cover image ("capa", S3 jpg) wins; else the frame at "capa_ms", 1.5 s by default.
        params = {"media_type": "REELS", "video_url": api.url(item["arquivos"][0]), "caption": item["legenda"],
                  "share_to_feed": "true"}
        if item.get("capa"):
            params["cover_url"] = api.url(item["capa"])
        else:
            params["thumb_offset"] = str(int(item.get("capa_ms") or CAPA_MS))
        cid = _ok(api.post(f"{ig}/media", params), "criar o Reel")["id"]
    elif item["tipo"] == "IMAGE":
        # single feed photo: image_url + caption only. "IMAGE" is our schema name; the Graph API takes no media_type
        # for a feed photo (media_type is only CAROUSEL, REELS or STORIES).
        cid = _ok(api.post(f"{ig}/media", {"image_url": api.url(item["arquivos"][0]), "caption": item["legenda"]}),
                  "criar a foto")["id"]
    elif item["tipo"] == "STORY":
        arq = item["arquivos"][0]
        midia = {"video_url": api.url(arq)} if arq.lower().endswith(".mp4") else {"image_url": api.url(arq)}
        cid = _ok(api.post(f"{ig}/media", {"media_type": "STORIES", **midia}), "criar o story")["id"]
    elif item["tipo"] == "CARROSSEL":
        filhos = [_ok(api.post(f"{ig}/media", {"image_url": api.url(k), "is_carousel_item": "true"}), f"imagem {n + 1}")["id"]
                  for n, k in enumerate(item["arquivos"])]
        for f in filhos:
            _esperar_pronto(api, f, dormir)
        cid = _ok(api.post(f"{ig}/media", {"media_type": "CAROUSEL", "children": ",".join(filhos),
                                           "caption": item["legenda"]}), "criar o carrossel")["id"]
    else:  # never guess: an unknown type must not go out as a carousel
        raise ValueError(f"tipo desconhecido: {item.get('tipo')!r}")
    _esperar_pronto(api, cid, dormir)
    return cid


_PADRAO = object()


def especialistas():
    """plugins/especialistas' helper, or None when no copy is installed (then posts go out as before). A copy that
    exists but does not load raises: the gate treats that as an error and blocks (fail closed)."""
    caminho = next((p for p in ESPECIALISTAS if p.exists()), None)
    if caminho is None:
        return None
    nome, mtime = "especialistas_conteudo", caminho.stat().st_mtime_ns
    antigo = sys.modules.get(nome)
    if antigo is None or getattr(antigo, "_mtime", None) != (str(caminho), mtime):
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = (str(caminho), mtime)
        sys.modules[nome] = m
    return sys.modules[nome]


def uma_linha(motivos, limite: int = 200) -> str:
    texto = "; ".join(str(m).strip() for m in (motivos if isinstance(motivos, list) else [motivos]) if str(m).strip())
    texto = " ".join(texto.split()) or "sem motivo dito"
    return texto if len(texto) <= limite else texto[:limite - 1] + "…"


def material_do_post(item: dict) -> tuple[str, dict]:
    """(tipo, material) for criticar(): the caption, the format and the local copies of the files when they exist
    (semana.aprovar() leaves them in cache/<id>/, the same place baixar_post() uses). A Reel also brings what is
    inside the video (material_do_video): frames and the narration."""
    pasta = PASTA / "cache" / item["id"]
    imagens = [str(pasta / k.rsplit("/", 1)[-1]) for k in list(item.get("arquivos") or []) + ([item["capa"]] if item.get("capa") else [])
               if k.lower().endswith(JPG) and (pasta / k.rsplit("/", 1)[-1]).exists()]
    tipo = {"CARROSSEL": "carrossel", "STORY": "story"}.get(item.get("tipo"), "post")
    material = {"formato": item.get("tipo"), "legenda": item.get("legenda", ""), "data": item.get("data"),
                "titulo": (item.get("origem") or {}).get("titulo", ""), "imagens": imagens}
    if item.get("tipo") == "REELS":
        try:
            material.update(material_do_video(item, material["imagens"]))
        except Exception as exc:  # the Crítico says what it could not see; the gate decides
            material["video"] = f"o vídeo não pôde ser aberto para a crítica ({type(exc).__name__}: {str(exc)[:120]})"
    return tipo, material


# ---- what is inside a Reel (21/10, Matheus: "pode fazer o do Crítico ver o vídeo") --------------------------------
# The Crítico read only the caption and the cover of a Reel, so it could not check his own AR Board rule ("a tela mostra
# o que a narração diz no mesmo momento; nada de letra cortada no último quadro") and blocked the iFood video for
# "fatos não comprovados no material". Now it gets QUADROS frames spread over the video (the last one just before the
# end, where the CTA is) with their second in the name, and the narration with timestamps.
QUADROS = (0.06, 0.25, 0.45, 0.65, 0.85)
FIM_S = 0.6  # the last frame: this many seconds before the end
_OUVIR = None  # set by the tests; else plugins/video/helpers/gemini.py `ouvir`


def _rodar(cmd: list, timeout: int = 120) -> str:
    import subprocess

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]}: {r.stderr.strip()[-200:]}")
    return r.stdout


def _video_local(item: dict, baixar=None) -> Path:
    chave = next(k for k in item["arquivos"] if k.lower().endswith(".mp4"))
    pasta = PASTA / "cache" / item["id"]
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / chave.rsplit("/", 1)[-1]
    if not destino.exists() or destino.stat().st_size == 0:
        if baixar is None:
            import urllib.request

            baixar = lambda chave_, caminho: urllib.request.urlretrieve(Api("", "").url(chave_), caminho)  # noqa: E731
        baixar(chave, str(destino))
    return destino


def _ouvir():
    if _OUVIR is not None:
        return _OUVIR
    caminho = Path(__file__).resolve().parents[2] / "video" / "helpers" / "gemini.py"
    spec = importlib.util.spec_from_file_location("conteudo_video_gemini", caminho)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.ouvir


def material_do_video(item: dict, imagens: list | None = None, baixar=None) -> dict:
    """{"imagens": capa + frames (q<n>_<segundo>s.jpg), "narracao": "[0.6s] …" or a note, "quadros": a line per frame}."""
    video = _video_local(item, baixar)
    pasta = video.parent / "quadros"
    pasta.mkdir(exist_ok=True)
    duracao = float(_rodar(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)]))
    tempos = [round(duracao * f, 1) for f in QUADROS] + [round(max(0.0, duracao - FIM_S), 1)]
    quadros = []
    for n, t in enumerate(tempos, 1):
        destino = pasta / f"q{n}_{t:.1f}s.jpg"
        if not destino.exists():
            _rodar(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t}", "-i", str(video), "-frames:v", "1", "-q:v", "3",
                    "-vf", "scale=720:-2", str(destino)])
        quadros.append(str(destino))
    narracao = str(item.get("roteiro") or "").strip()
    if not narracao:
        audio = pasta.parent / "narracao.mp3"
        try:
            if not audio.exists():
                _rodar(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vn", "-ac", "1", "-b:a", "64k",
                        str(audio)])
            narracao = _ouvir()(str(audio)).strip()
        except Exception as exc:
            narracao = f"(narração não transcrita: {type(exc).__name__}: {str(exc)[:120]})"
    capa = [i for i in (imagens or []) if i not in quadros][:1]
    ordem = (["capa"] if capa else []) + [f"segundo {t:.1f}" for t in tempos]
    return {"imagens": capa + quadros, "duracao_s": round(duracao, 1),
            "quadros": "ordem das imagens: " + "; ".join(f"{n} = {o}" for n, o in enumerate(ordem, 1))
                        # 22/10: the same Reel passed and then failed for a voice 0.4 s ahead of a scene change
                        + ". Os quadros são de instantes fixos: perto de uma troca de cena a fala pode adiantar ou "
                          "atrasar até 1 s; desencontro é a tela errada durante a fala, não num instante de transição.",
            "narracao": narracao}


def portao(item: dict, critico=_PADRAO) -> dict:
    """The Crítico's gate before a post goes out: {"publicar": bool, "motivo", "critica"?}. No especialistas plugin:
    publish as before. Released by Matheus (item["liberado"]): publish without asking again. Anything but a clean
    "aprova" (reprova, exception, odd answer, plugin that does not load) blocks."""
    if item.get("liberado"):
        return {"publicar": True, "motivo": f"liberado por {item['liberado'].get('por', 'Matheus')}"}
    try:
        esp = especialistas() if critico is _PADRAO else critico
    except Exception as exc:
        return {"publicar": False, "motivo": f"o Crítico não carregou ({type(exc).__name__}: {str(exc)[:120]})"}
    if esp is None:
        return {"publicar": True, "motivo": "sem Crítico instalado"}
    try:
        r = esp.criticar(*material_do_post(item))
    except Exception as exc:
        return {"publicar": False, "motivo": f"o Crítico falhou ({type(exc).__name__}: {str(exc)[:120]})"}
    veredito = r.get("veredito") if isinstance(r, dict) else None
    critica = {"veredito": veredito, "motivos": list((r or {}).get("motivos") or [])[:5] if isinstance(r, dict) else []}
    if veredito == "aprova":
        return {"publicar": True, "motivo": "o Crítico aprovou", "critica": critica}
    if veredito == "reprova":
        return {"publicar": False, "motivo": "o Crítico reprovou: " + uma_linha(critica["motivos"]), "critica": critica}
    return {"publicar": False, "motivo": f"resposta do Crítico sem veredito claro ({str(r)[:80]})"}


def _chamar_aviso(avisar, texto: str, botoes: list | None = None) -> None:
    """The job loop's notifier takes buttons; the tests' list.append takes the text alone."""
    if botoes:
        try:
            avisar(texto, botoes)
            return
        except TypeError:
            pass
    avisar(texto)


def liberar(item_id: str, motivo: str, quem: str = "matheus") -> dict:
    """Matheus's override of the Crítico (20/10): a blocked post goes back to pendente, or a pending one is marked to
    go without the gate. Only on his explicit word (button or a message saying so); who, when and why are kept on the
    post and in the journal. Nothing is published here: the job loop does it at the post's hour, on its day."""
    if not str(motivo or "").strip():
        return {"ok": False, "erro": "diga o motivo (o que o Matheus disse)"}
    registro = {"por": str(quem)[:80], "em": time.time(), "motivo": str(motivo)[:200]}
    antes = AUTOR["quem"]
    AUTOR["quem"] = f"{quem}: liberou {item_id}"
    try:
        with _exclusivo():
            d = carregar()
            alvo = next((i for i in d["itens"] if i["id"] == item_id), None)
            if not alvo:
                return {"ok": False, "erro": f"{item_id}: não existe"}
            if alvo["estado"] == "bloqueada":
                registro["bloqueio"] = alvo.get("bloqueio", "")
                _mudar(alvo, "pendente", liberado=registro)
            elif alvo["estado"] == "pendente":
                alvo["liberado"] = registro
                _diario({"item": item_id, "liberado": registro})
            else:
                return {"ok": False, "erro": f"{item_id}: está {alvo['estado']}, nada a liberar"}
            _gravar(d)
    finally:
        AUTOR["quem"] = antes
    return {"ok": True, "id": item_id, "data": alvo["data"], "hora": alvo["hora"]}


# ---- the advance check (22/10, Matheus: "Se o crítico rejeita, automáticamente deveria ser refeito, e não logo antes
# de postar, durante a etapa de criação"). The garantia was blocked twice at its hour that day. Now every pending post
# is judged CONFERIR_HORAS before it goes out, on the exact files and caption (impressao); a reproved one is redone by
# the agent (semana.refazer_item, up to REFAZER_MAX times) and judged again; only what cannot be redone reaches Matheus,
# a day early. At the hour, an approval of the same impressao is the gate: nothing is judged again at the last minute.
CONFERIR_HORAS = 36
REFAZER_MAX = 2


def _quando(item: dict) -> float:
    return dt.datetime.fromisoformat(f"{item['data']}T{item['hora']}:00").replace(tzinfo=_tz()).timestamp()


def _chaves(item: dict) -> list:
    return list(item.get("arquivos") or []) + ([item["capa"]] if item.get("capa") else [])


def _cache_do_item(item: dict, url=None, baixar=None) -> None:
    """The post's files in cache/<id>/, where the Crítico reads them (material_do_post)."""
    import urllib.request
    pasta = PASTA / "cache" / item["id"]
    pasta.mkdir(parents=True, exist_ok=True)
    for chave in _chaves(item):
        destino = pasta / chave.rsplit("/", 1)[-1]
        if not destino.exists() or destino.stat().st_size == 0:
            link = (url or Api("", "").url)(chave)
            (baixar or (lambda l, c: urllib.request.urlretrieve(l, c)))(link, str(destino))


def impressao(item: dict) -> str:
    """sha256 of what goes out: format, caption, file names and their bytes in the cache; "" when a file is missing."""
    import hashlib
    h = hashlib.sha256(json.dumps([item.get("tipo"), item.get("legenda"), _chaves(item)], ensure_ascii=False).encode())
    for chave in _chaves(item):
        caminho = PASTA / "cache" / item["id"] / chave.rsplit("/", 1)[-1]
        if not caminho.exists() or caminho.stat().st_size == 0:
            return ""
        h.update(caminho.read_bytes())
    return h.hexdigest()


def _anotar(item_id: str, evento: dict, **campos) -> bool:
    """Fields of a still pending post (no state change), journaled."""
    with _exclusivo():
        d = carregar()
        alvo = next((i for i in d["itens"] if i["id"] == item_id), None)
        if not alvo or alvo["estado"] != "pendente":
            return False
        alvo.update(campos)
        _gravar(d)
    _diario({"item": item_id, **evento})
    return True


def refeito(item_id: str, arquivos: list, motivo: str) -> dict:
    """The agent's redo of a pending post the advance check reproved: same id, day, hour, format and caption, new
    files (already in S3 and in the cache). The old check goes away, so the next pass judges the new files."""
    with _exclusivo():
        d = carregar()
        alvo = next((i for i in d["itens"] if i["id"] == item_id), None)
        if not alvo or alvo["estado"] != "pendente":
            return {"ok": False, "erro": f"{item_id}: só post pendente é refeito"}
        erro = _validar_item(dict(alvo, arquivos=list(arquivos or [])))
        if erro:
            return {"ok": False, "erro": f"{item_id}: {erro}"}
        antes = alvo["arquivos"]
        alvo["arquivos"] = list(arquivos)
        alvo.pop("conferido", None)
        _gravar(d)
    _diario({"item": item_id, "refeito": True, "de": antes, "para": list(arquivos), "motivo": str(motivo)[:300]})
    return {"ok": True, "id": item_id, "arquivos": list(arquivos)}


def conferir_antes(agora: float | None = None, critico=_PADRAO, refazer=None, avisar=lambda texto: None,
                   url=None, baixar=None) -> dict | None:
    """One pass of the advance check: the next pending post (within CONFERIR_HORAS, not released by Matheus) whose
    exact material was not judged yet goes through the same gate as at the hour. One post per pass: the Crítico and
    the Designer take minutes. refazer(item, critica) -> {"ok"} is the agent's redo (semana.refazer_item)."""
    agora = time.time() if agora is None else agora
    fila = sorted((i for i in carregar()["itens"] if i["estado"] == "pendente" and not i.get("liberado")
                   and agora < _quando(i) <= agora + CONFERIR_HORAS * 3600), key=_quando)
    for item in fila:
        try:
            _cache_do_item(item, url, baixar)
        except Exception as exc:  # no file to judge now: the gate at the hour still runs
            print(f"conteudo: conferir {item['id']}: arquivo não baixou ({exc})", flush=True)
            continue
        marca = impressao(item)
        if not marca or (item.get("conferido") or {}).get("impressao") == marca:
            continue
        gate = portao(item, critico)
        if gate["publicar"]:
            _anotar(item["id"], {"conferido": "aprova"},
                    conferido={"impressao": marca, "em": agora, "veredito": "aprova", "motivo": gate["motivo"]})
            return {"id": item["id"], "veredito": "aprova"}
        if not gate.get("critica"):  # the Crítico failed (timeout, no verdict): not a reproval, try again next pass
            return {"id": item["id"], "veredito": "erro", "motivo": gate["motivo"]}
        critica = gate["critica"]
        feitas = int(item.get("refeitas") or 0)
        if refazer is None:
            erro = "não há quem refaça"
        elif feitas >= REFAZER_MAX:
            erro = f"já refiz {feitas} vezes"
        else:
            try:
                r = refazer(item, critica)
            except Exception as exc:
                r = {"ok": False, "erro": f"{type(exc).__name__}: {str(exc)[:120]}"}
            _anotar(item["id"], {"refazer": bool(r.get("ok")), "tentativa": feitas + 1,
                                 **({} if r.get("ok") else {"erro": str(r.get("erro"))[:200]})}, refeitas=feitas + 1)
            if r.get("ok"):
                return {"id": item["id"], "veredito": "reprova", "refeito": True}
            erro = str(r.get("erro") or "sem motivo")
        _anotar(item["id"], {"conferido": "reprova", "motivo": gate["motivo"][:300]},
                conferido={"impressao": marca, "em": agora, "veredito": "reprova", "motivo": gate["motivo"]})
        botao = f"cs:{LOGIN}:{item['id']}:liberar"
        _chamar_aviso(avisar, f"pendente: o Crítico reprovou {item['id']} ({item['tipo']}, sai {item['data']} às "
                              f"{item['hora']}) e não consegui refazer sozinho ({uma_linha(erro, 160)}): {gate['motivo']}. "
                              f"Se nada mudar até lá, ele fica bloqueado; para publicar mesmo assim, toque no botão ou "
                              f"diga \"libera o post {item['id']}\".",
                      [{"id": botao, "titulo": "🔓 Publicar mesmo assim"}] if len(botao.encode()) <= 64 else None)
        return {"id": item["id"], "veredito": "reprova", "refeito": False, "erro": erro}
    return None


def rodar(api, avisar=lambda texto: None, agora: float | None = None, dormir=time.sleep, critico=_PADRAO) -> dict | None:
    """One pass of the job loop: publishes today's post if due and the Crítico's gate lets it. The reservation
    (pendente → publicando) is saved before talking to Meta, so two passes can never publish the same item."""
    previsto = devido(agora)
    if not previsto:
        return None
    conf = previsto.get("conferido") or {}
    if (not previsto.get("liberado") and conf.get("veredito") == "aprova" and conf.get("impressao")
            and conf["impressao"] == impressao(previsto)):  # the same files and caption the Crítico approved before
        gate = {"publicar": True, "motivo": "o Crítico aprovou na conferência antecipada"}
    else:
        gate = portao(previsto, critico)  # outside the lock: it may call a model
    if not gate["publicar"]:
        with _exclusivo():
            d = carregar()
            alvo = next((i for i in d["itens"] if i["id"] == previsto["id"]), None)
            if not alvo or alvo["estado"] != "pendente":
                return None
            if alvo.get("liberado"):  # released while the Crítico was thinking: next pass publishes it
                return None
            _mudar(alvo, "bloqueada", bloqueio=gate["motivo"], **({"critica": gate["critica"]} if gate.get("critica") else {}))
            _gravar(d)
        botao = f"cs:{LOGIN}:{previsto['id']}:liberar"
        _chamar_aviso(avisar, f"pendente: o post de hoje da @raiz.connect ({previsto['id']}) não saiu: {gate['motivo']}. "
                              f"Ele fica bloqueado na agenda; para publicar mesmo assim, toque no botão ou diga "
                              f"\"libera o post {previsto['id']}\".",
                      [{"id": botao, "titulo": "🔓 Publicar mesmo assim"}] if len(botao.encode()) <= 64 else None)
        return {"id": previsto["id"], "estado": "bloqueada", "motivo": gate["motivo"]}
    with _exclusivo():
        item = devido(agora)
        if not item or item["id"] != previsto["id"]:
            return None
        d = carregar()
        alvo = next(i for i in d["itens"] if i["id"] == item["id"])
        _mudar(alvo, "publicando")
        _gravar(d)
    publicou_chamado = False
    try:
        cid = preparar(item, api, dormir)
        publicou_chamado = True
        pub = _ok(api.post(f"{api.ig}/media_publish", {"creation_id": cid}), "publicar")
        link = (api.get(pub["id"], {"fields": "permalink"}) or {}).get("permalink", "")
        fim, campos = "publicada", {"media_id": pub["id"], "permalink": link, "portao": gate["motivo"]}
    except Exception as exc:
        fim, campos = ("incerta" if publicou_chamado else "falhou"), {"erro": str(exc)[:300]}
    with _exclusivo():
        d = carregar()
        alvo = next(i for i in d["itens"] if i["id"] == item["id"])
        _mudar(alvo, fim, **campos)
        _gravar(d)
    if fim == "falhou":
        avisar(f"pendente: o post de hoje da @raiz.connect ({item['id']}) não saiu: {campos['erro']}. Nada foi "
               "publicado; ele fica parado até você mandar tentar de novo.")
    elif fim == "incerta":
        avisar(f"pendente: o post de hoje da @raiz.connect ({item['id']}) pode ter saído, mas a Meta não confirmou "
               f"({campos['erro']}). Confira o perfil antes de qualquer nova tentativa.")
    return {"id": item["id"], "estado": fim, **campos}


def api_do_cofre(login: str = "matheus"):
    import importlib.util as iu
    spec = iu.spec_from_file_location("cofre_helper_conteudo", "/a0/usr/plugins/cofre/helpers/cofre.py")
    m = iu.module_from_spec(spec)
    spec.loader.exec_module(m)
    s = m.carregar(login)
    token, ig = s.get("META_IG_TOKEN"), s.get("META_IG_USER_ID")
    return Api(token, ig) if token and ig else None


# ------------------------------------------------------------------ reading (for the weekly marketing routine)

METRICAS = ("reach", "saved", "likes", "comments", "shares", "views")


def agenda_proxima(dias: int = 7, agora: float | None = None) -> dict:
    """The next `dias` days of the calendar, one entry per day, with the empty days apart (14/10: the plan asks for
    1 post a day; the weekly routine must see the gaps before they happen). Read only."""
    agora = agora or time.time()
    hoje = dt.datetime.fromtimestamp(agora, _tz()).date()
    por_dia: dict = {}
    for i in carregar()["itens"]:
        if i["estado"] != "cancelada":
            por_dia.setdefault(i["data"], []).append(i)
    linhas, vazios = [], []
    for k in range(max(1, int(dias))):
        dia = (hoje + dt.timedelta(days=k)).isoformat()
        its = por_dia.get(dia, [])
        if not its:
            vazios.append(dia)
        linhas.append({"data": dia, "itens": [{"id": i["id"], "tipo": i["tipo"], "hora": i["hora"],
                                               "estado": i["estado"]} for i in its]})
    return {"dias": linhas, "vazios": vazios}


def desempenho(api, dias: int = 7, agora: float | None = None) -> dict:
    """Reach, saves, likes, comments, shares and views of every post of the last `dias` days, straight from the
    Graph API (posts made outside this calendar count too), plus the follower count. Read only."""
    agora = agora or time.time()
    desde = agora - max(1, int(dias)) * 86400
    r = api.get(f"{api.ig}/media", {"fields": "id,media_type,media_product_type,timestamp,permalink", "limit": "30"})
    if not isinstance(r, dict) or r.get("error"):
        return {"ok": False, "erro": ((r or {}).get("error") or {}).get("message", "sem resposta da Meta")}
    nossos = {i.get("media_id"): i["id"] for i in carregar()["itens"] if i.get("media_id")}
    posts, total = [], {m: 0 for m in METRICAS}
    for m in r.get("data") or []:
        try:
            quando = dt.datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        except (KeyError, ValueError):
            continue
        if quando.timestamp() < desde:
            continue
        ins = api.get(f"{m['id']}/insights", {"metric": ",".join(METRICAS)}) or {}
        valores = {} if ins.get("error") else {x.get("name"): (x.get("values") or [{}])[0].get("value", 0)
                                              for x in ins.get("data") or []}
        linha = {"id": nossos.get(m["id"], ""), "media_id": m["id"],
                 "tipo": m.get("media_product_type") or m.get("media_type", ""),
                 "data": quando.astimezone(_tz()).date().isoformat(), "permalink": m.get("permalink", ""),
                 **{k: int(valores.get(k) or 0) for k in METRICAS}}
        if ins.get("error"):
            linha["erro"] = ins["error"].get("message", "métricas indisponíveis")
        for k in METRICAS:
            total[k] += linha[k]
        posts.append(linha)
    conta = api.get(api.ig, {"fields": "followers_count,media_count"}) or {}
    return {"ok": True, "dias": int(dias), "posts": posts, "total": total, "seguidores": conta.get("followers_count")}


def baixar_post(data: str = "", url=None, baixar=None, agora: float | None = None) -> dict:
    """The files of the day's post, downloaded to /a0/usr/conteudo/cache/<id>/ so the agent can send them to Matheus
    (15/10: asked for today's carousel, the agent looked for local files that only exist in S3 and said "não achei").
    Read-only: nothing is scheduled, changed or published."""
    import urllib.request
    agora = time.time() if agora is None else agora
    data = data or dt.datetime.fromtimestamp(agora, _tz()).date().isoformat()
    item = next((i for i in carregar()["itens"] if i["data"] == data and i["estado"] != "cancelada"), None)
    if not item:
        return {"ok": False, "erro": f"nenhum post marcado para {data}"}
    url = url or Api("", "").url
    baixar = baixar or (lambda link, caminho: urllib.request.urlretrieve(link, caminho))
    pasta = PASTA / "cache" / item["id"]
    pasta.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for chave in item["arquivos"]:
        destino = pasta / chave.rsplit("/", 1)[-1]
        if not destino.exists() or destino.stat().st_size == 0:
            baixar(url(chave), str(destino))
        caminhos.append(str(destino))
    return {"ok": True, "id": item["id"], "data": data, "hora": item["hora"], "tipo": item["tipo"], "estado": item["estado"],
            "legenda": item["legenda"], "arquivos": caminhos}

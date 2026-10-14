"""Daily posts on @raiz.connect through Meta's official API (instagram_content_publish), authorized by Matheus on
13/10 ("1 por dia, nas legendas não use emoticons"). The calendar lives in /a0/usr/conteudo/agenda.json and only
changes through this file: agendar() validates, the job loop publishes what is due, and every state change goes
through _mudar() (TRANSICOES) and lands in the journal. Rules that are code, not text:
- at most one post per day (BRT), never twice the same item;
- captions without emoji, at most 2200 characters and 30 hashtags;
- a post whose publish call was made but not confirmed becomes "incerta" and is never retried by itself."""

import datetime as dt
import fcntl
import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path

PASTA = Path(os.environ.get("CONTEUDO_PASTA", "/a0/usr/conteudo"))
BUCKET = "agentepessoal-backup-964862484412"
PREFIXO = "conteudo/"
GRAPH = "https://graph.facebook.com/v25.0"
PROXY = "http://host.docker.internal:8787"  # host proxy: the only holder of AWS credentials
FUSO = "America/Sao_Paulo"
TIPOS = ("REELS", "CARROSSEL")
MAX_LEGENDA, MAX_HASHTAGS, MAX_CARROSSEL = 2200, 30, 10
ESPERA_PROCESSAR = 600  # seconds Meta may take to process a video before we give up
AUTOR = {"quem": "agente"}  # operator scripts set "operador: <why>"

# any pictograph, dingbat, arrow-ish symbol or emoji joiner: Matheus wants plain text captions
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U0001F900-\U0001F9FF☀-➿⬀-⯿←-⇿️‍⃣]")

TRANSICOES = {
    "pendente": {"publicando", "cancelada"},
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
    if it["tipo"] == "CARROSSEL" and not (2 <= len(arqs) <= MAX_CARROSSEL and all(a.lower().endswith((".jpg", ".jpeg")) for a in arqs)):
        return f"carrossel: de 2 a {MAX_CARROSSEL} imagens .jpg"
    return validar_legenda(it.get("legenda", ""))


def agendar(itens: list, agora: float | None = None) -> dict:
    """Adds posts to the calendar. All or nothing: any invalid item refuses the whole batch."""
    agora = time.time() if agora is None else agora
    hoje = dt.datetime.fromtimestamp(agora, _tz()).date().isoformat()
    with _exclusivo():
        d = carregar()
        ocupadas = {i["data"] for i in d["itens"] if i["estado"] not in ("cancelada", "falhou")}
        ids = {i["id"] for i in d["itens"]}
        novos = []
        for it in itens:
            erro = _validar_item(it)
            if not erro and it["data"] < hoje:
                erro = "data no passado"
            if not erro and (it["data"] in ocupadas or it["data"] in {n["data"] for n in novos}):
                erro = f"já existe post para {it['data']} (um por dia)"
            if not erro and (not it.get("id") or it["id"] in ids or it["id"] in {n["id"] for n in novos}):
                erro = "id vazio ou repetido"
            if erro:
                return {"ok": False, "erro": f"{it.get('id', '?')}: {erro}"}
            novos.append({"id": it["id"], "data": it["data"], "hora": it["hora"], "tipo": it["tipo"],
                          "arquivos": list(it["arquivos"]), "legenda": it["legenda"].strip(), "estado": "pendente",
                          "criado_em": agora})
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
        fixos = {i["data"] for i in d["itens"] if i not in mover and i["estado"] not in ("cancelada", "falhou")}
        novas = {i["id"]: (dt.date.fromisoformat(i["data"]) + dt.timedelta(days=int(dias))).isoformat() for i in mover}
        choque = sorted(set(novas.values()) & fixos)
        if choque:
            return {"ok": False, "erro": f"cairia em dia já ocupado: {', '.join(choque)}"}
        for i in mover:
            antes = i["data"]
            i["data"] = novas[i["id"]]
            _diario({"item": i["id"], "remarcado": True, "de_data": antes, "para_data": i["data"]})
        _gravar(d)
    return {"ok": True, "movidos": {i["id"]: i["data"] for i in mover}}


def devido(agora: float | None = None) -> dict | None:
    """Today's post when its hour has come, unless something was already published or attempted today."""
    agora = time.time() if agora is None else agora
    momento = dt.datetime.fromtimestamp(agora, _tz())
    hoje, hora = momento.date().isoformat(), momento.strftime("%H:%M")
    d = carregar()
    do_dia = [i for i in d["itens"] if i["data"] == hoje]
    if any(i["estado"] in ("publicando", "publicada", "incerta") for i in do_dia):
        return None
    return next((i for i in do_dia if i["estado"] == "pendente" and i["hora"] <= hora), None)


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
        cid = _ok(api.post(f"{ig}/media", {"media_type": "REELS", "video_url": api.url(item["arquivos"][0]),
                                           "caption": item["legenda"], "share_to_feed": "true"}), "criar o Reel")["id"]
    else:
        filhos = [_ok(api.post(f"{ig}/media", {"image_url": api.url(k), "is_carousel_item": "true"}), f"imagem {n + 1}")["id"]
                  for n, k in enumerate(item["arquivos"])]
        for f in filhos:
            _esperar_pronto(api, f, dormir)
        cid = _ok(api.post(f"{ig}/media", {"media_type": "CAROUSEL", "children": ",".join(filhos),
                                           "caption": item["legenda"]}), "criar o carrossel")["id"]
    _esperar_pronto(api, cid, dormir)
    return cid


def rodar(api, avisar=lambda texto: None, agora: float | None = None, dormir=time.sleep) -> dict | None:
    """One pass of the job loop: publishes today's post if due. The reservation (pendente → publicando) is saved
    before talking to Meta, so two passes can never publish the same item."""
    with _exclusivo():
        item = devido(agora)
        if not item:
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
        fim, campos = "publicada", {"media_id": pub["id"], "permalink": link}
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

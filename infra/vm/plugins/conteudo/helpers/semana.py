"""The week of @raiz.connect posts, proposed every Monday instead of an agenda assembled by hand (20/10, approved by
Matheus). The routine reads what did well (conteudo desempenho), the competitors (concorrentes) and the niche's
viral videos (video), then hands 7 ideas to propor(): each one is drawn by the Designer and judged by the Crítico
(plugins/especialistas), and Matheus gets ONE Telegram message with the 7 and three buttons (approve all, choose,
redo). aprovar() writes the approved ones into the same agenda.json the daily job loop publishes from, through
conteudo.agendar(), so publishing is unchanged. Rules that are code:
- without the especialistas plugin a proposal says the review is missing; nothing is ever approved by itself;
- "Aprovar todas" leaves out what the Crítico reproved: those go only when he picks them by number, and that
  override is kept on the post (liberado), so the publish gate does not block what he already decided;
- a week that was redone (new version) refuses the old message's buttons.
State: /a0/usr/conteudo/semanas/<id>.json, written only here, under its own lock; journal: conteudo's diario.jsonl."""

import datetime as dt
import fcntl
import importlib.util
import json
import os
import re
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path

PROPOSTAS = 7
HORA = "11:45"  # the hour every post of the plan went out so far
JANELA_DIAS = 21  # how far ahead to look for 7 free days
PROXY = "http://host.docker.internal:8787"  # the host holds the AWS identity; the container has none
PONTE = Path("/a0/usr/plugins/whatsapp/helpers/ponte.py")
DIAS_SEMANA = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
NOME_TIPO = {"REELS": "Reel", "CARROSSEL": "Carrossel", "IMAGE": "Foto"}
VIDEO, IMAGEM = (".mp4",), (".jpg", ".jpeg", ".png")
SEM_REVISAO = "sem revisão"
REGRAS = ("Fala com o dono do negócio que produz e vende comida, nunca com o consumidor; sem jargão; número sempre "
          "como \"valores de exemplo\"; legenda sem emoji e sem travessão; nunca \"aumente seu lucro\"; oferta: "
          "Preço Certo em 30 Dias.")

_C: dict = {}


def c():
    """conteudo.py next to this file, re-read when it changes (the tests pin their own instance in _C["fixo"])."""
    if "fixo" in _C:
        return _C["fixo"]
    caminho = Path(__file__).resolve().parent / "conteudo.py"
    marca = caminho.stat().st_mtime_ns
    if _C.get("marca") != marca:
        spec = importlib.util.spec_from_file_location("conteudo_helper_semana", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _C.update(marca=marca, m=m)
    return _C["m"]


def _pasta() -> Path:
    return c().PASTA / "semanas"


@contextmanager
def _exclusivo():
    _pasta().mkdir(parents=True, exist_ok=True)
    with open(_pasta() / "semanas.lock", "a") as fh:  # not agenda.lock: aprovar() calls agendar(), which takes that
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _arq(sid: str) -> Path:
    if not re.fullmatch(r"s\d{8}-\d{1,3}", str(sid or "")):
        raise ValueError(f"semana inválida: {sid!r}")
    return _pasta() / f"{sid}.json"


def carregar(sid: str) -> dict | None:
    arq = _arq(sid)
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None


def _gravar(s: dict) -> None:
    arq = _arq(s["id"])
    tmp = arq.with_suffix(f".{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, arq)


def ultima() -> dict | None:
    """The newest week (highest date, then version)."""
    if not _pasta().exists():
        return None
    nomes = sorted((p.stem for p in _pasta().glob("s*.json")),
                   key=lambda n: (n.split("-")[0], int(n.split("-")[1])))
    return carregar(nomes[-1]) if nomes else None


def _hoje(agora: float) -> dt.date:
    return dt.datetime.fromtimestamp(agora, c()._tz()).date()


def dias_livres(agora: float, n: int = PROPOSTAS) -> list[str]:
    """The first n days from tomorrow with no live post in the agenda (a day blocked by the Crítico counts as taken)."""
    ocupados = {i["data"] for i in c().carregar()["itens"] if i["estado"] not in ("cancelada", "falhou")}
    hoje, livres = _hoje(agora), []
    for k in range(1, JANELA_DIAS + 1):
        dia = (hoje + dt.timedelta(days=k)).isoformat()
        if dia not in ocupados:
            livres.append(dia)
        if len(livres) == n:
            break
    return livres


def tipo_dos_arquivos(arquivos: list) -> tuple[str, list, str]:
    """(tipo, files, cover) from what the Designer delivered: one .mp4 is a Reel (a picture next to it is its cover),
    one picture is a feed photo, 2 to 10 pictures a carousel. ("", [], "") when it is none of these."""
    nomes = [str(a) for a in arquivos or [] if str(a).strip()]
    videos = [a for a in nomes if a.lower().endswith(VIDEO)]
    imagens = [a for a in nomes if a.lower().endswith(IMAGEM)]
    if len(videos) + len(imagens) != len(nomes):
        return "", [], ""
    if len(videos) == 1 and len(imagens) <= 1:
        return "REELS", videos, (imagens[0] if imagens else "")
    if not videos and len(imagens) == 1:
        return "IMAGE", imagens, ""
    if not videos and 2 <= len(imagens) <= c().MAX_CARROSSEL:
        return "CARROSSEL", imagens, ""
    return "", [], ""


def _critica(r) -> dict:
    """The Crítico's answer kept as {"veredito": "aprova"|"reprova"|"sem revisão", "motivos", "sugestoes"}."""
    if not isinstance(r, dict) or r.get("veredito") not in ("aprova", "reprova"):
        return {"veredito": SEM_REVISAO, "motivos": ["o Crítico não deu veredito claro"], "sugestoes": []}
    return {"veredito": r["veredito"], "motivos": [str(m) for m in r.get("motivos") or []][:5],
            "sugestoes": [str(m) for m in r.get("sugestoes") or []][:3]}


def _texto(v, limite: int = 600) -> str:
    return " ".join(str(v or "").split())[:limite]


def _desenhar(esp, briefing: dict, p: dict) -> dict:
    """One proposal through the Designer (who always asks the Crítico); without especialistas, the review is missing."""
    if esp is None:
        return {"spec": {}, "arquivos": [str(a) for a in p.get("arquivos") or []], "falta": [],
                "critica": {"veredito": SEM_REVISAO, "motivos": ["o Crítico ainda não está instalado"], "sugestoes": []}}
    try:
        d = esp.desenhar(briefing)
    except Exception as exc:
        return {"spec": {}, "arquivos": [], "falta": [f"o Designer falhou ({type(exc).__name__}: {str(exc)[:120]})"],
                "critica": {"veredito": SEM_REVISAO, "motivos": ["o Designer falhou antes do Crítico"], "sugestoes": []}}
    d = d if isinstance(d, dict) else {}
    critica = d.get("critica")
    if critica is None:  # a Designer that did not ask the Crítico: ask here, never assume
        try:
            critica = esp.criticar("carrossel" if briefing["formato"] == "CARROSSEL" else "post",
                                   {"briefing": briefing, "imagens": d.get("arquivos") or []})
        except Exception as exc:
            critica = {"veredito": SEM_REVISAO, "motivos": [f"o Crítico falhou ({type(exc).__name__})"]}
    return {"spec": d.get("spec") if isinstance(d.get("spec"), dict) else {}, "arquivos": list(d.get("arquivos") or []),
            "falta": [str(x) for x in d.get("falta") or []], "critica": _critica(critica)}


def propor(propostas: list, agora: float | None = None, enviar=None, login: str = "matheus") -> dict:
    """The week: 7 ideas from the routine [{"titulo", "formato" (REELS|CARROSSEL|IMAGE), "ideia", "legenda", "hora"?}]
    → each drawn and judged, saved as a new version, and the one message with buttons sent to Matheus. Nothing goes
    into the agenda here."""
    agora = time.time() if agora is None else agora
    if isinstance(propostas, str):
        try:
            propostas = json.loads(propostas)
        except ValueError:
            return {"ok": False, "erro": "propostas: lista JSON de 7 objetos"}
    propostas = [p for p in propostas or [] if isinstance(p, dict)]
    dias = dias_livres(agora)
    if len(propostas) != PROPOSTAS:
        return {"ok": False, "erro": f"mande exatamente {PROPOSTAS} propostas (vieram {len(propostas)})"}
    if len(dias) < PROPOSTAS:
        return {"ok": False, "erro": f"só há {len(dias)} dias livres nas próximas 3 semanas"}
    try:
        esp, nota = c().especialistas(), ""
    except Exception as exc:  # installed but broken: the proposals say so, and nothing is approved by itself
        esp, nota = None, f"o plugin de especialistas não carregou ({type(exc).__name__})"
    base = "s" + _hoje(agora).strftime("%Y%m%d")
    with _exclusivo():
        versao = 1 + max([int(p.stem.split("-")[1]) for p in _pasta().glob(f"{base}-*.json")] or [0])
    sid = f"{base}-{versao}"
    itens = []
    for n, (p, dia) in enumerate(zip(propostas, dias), start=1):
        formato = str(p.get("formato") or "").upper()
        formato = formato if formato in c().TIPOS else "CARROSSEL"
        hora = str(p.get("hora") or HORA)
        briefing = {"marca": "raiz", "rede": "instagram @raiz.connect", "formato": formato,
                    "titulo": _texto(p.get("titulo"), 120), "ideia": _texto(p.get("ideia"), 1200),
                    "legenda": str(p.get("legenda") or "").strip(), "data": dia, "regras": REGRAS}
        d = _desenhar(esp, briefing, p)
        if nota:
            d["critica"]["motivos"] = [nota] + d["critica"]["motivos"]
        legenda = briefing["legenda"] or str(d["spec"].get("legenda") or "").strip()
        tipo, arquivos, capa = tipo_dos_arquivos(d["arquivos"])
        problema = ""
        if not tipo:
            problema = "o Designer não entregou arquivo publicável (.mp4, ou de 1 a 10 imagens)" + (
                f": {_texto('; '.join(d['falta']), 160)}" if d["falta"] else "")
        else:
            problema = c().validar_legenda(legenda)
        itens.append({"n": n, "id": f"{sid}-{n}", "data": dia, "hora": hora, "titulo": briefing["titulo"],
                      "ideia": briefing["ideia"], "formato_pedido": formato, "tipo": tipo, "arquivos": arquivos,
                      "capa": capa, "legenda": legenda, "spec": d["spec"], "critica": d["critica"],
                      "problema": problema, "estado": "proposta"})
    semana = {"id": sid, "criada_em": agora, "estado": "proposta", "login": login, "propostas": itens}
    with _exclusivo():
        for antiga in _pasta().glob("s*.json"):  # an older week still open is replaced: its buttons stop working
            s = json.loads(antiga.read_text(encoding="utf-8"))
            if s["estado"] in ("proposta", "refazer"):
                s["estado"] = "substituida"
                _gravar(s)
        _gravar(semana)
    c()._diario({"semana": sid, "proposta": True, "dias": [i["data"] for i in itens],
                 "vereditos": [i["critica"]["veredito"] for i in itens]})
    texto, botoes = mensagem(semana)
    erro = (enviar or _enviar_ponte)(login, texto, botoes)
    with _exclusivo():
        s = carregar(sid)
        s["enviada"] = not erro
        if erro:
            s["erro_envio"] = str(erro)[:200]
        _gravar(s)
    return {"ok": True, "semana": sid, "enviada": not erro, **({"erro_envio": str(erro)[:200]} if erro else {}),
            "propostas": [{"n": i["n"], "data": i["data"], "tipo": i["tipo"] or "?", "titulo": i["titulo"],
                           "critico": i["critica"]["veredito"], "problema": i["problema"]} for i in itens]}


def _rotulo_dia(data: str) -> str:
    d = dt.date.fromisoformat(data)
    return f"{DIAS_SEMANA[d.weekday()]} {d.strftime('%d/%m')}"


def _aprovaveis(semana: dict) -> list[dict]:
    """What "Aprovar todas" takes: still proposed, publishable and not reproved by the Crítico."""
    return [p for p in semana["propostas"] if p["estado"] == "proposta" and not p["problema"]
            and p["critica"]["veredito"] != "reprova"]


def mensagem(semana: dict) -> tuple[str, list]:
    """The one Telegram message: the 7 proposals, the Crítico's word on each, and the buttons."""
    ps = semana["propostas"]
    linhas = [f"*Semana de posts da @raiz.connect* ({_rotulo_dia(ps[0]['data'])} a {_rotulo_dia(ps[-1]['data'])})"]
    for p in ps:
        v = p["critica"]["veredito"]
        if p["problema"]:
            critico = f"não dá para agendar: {_texto(p['problema'], 140)}"
        elif v == "aprova":
            critico = "Crítico aprovou"
        elif v == "reprova":
            critico = "*Crítico reprovou*: " + c().uma_linha(p["critica"]["motivos"], 140)
        else:
            critico = "sem revisão do Crítico (" + c().uma_linha(p["critica"]["motivos"], 100) + ")"
        linhas.append(f"{p['n']}. *{_rotulo_dia(p['data'])}* · {NOME_TIPO.get(p['tipo'], '?')} · {p['titulo']}\n"
                      f"   {_texto(p['legenda'], 110)}\n   {critico}")
    k = len(_aprovaveis(semana))
    linhas.append("Para ver a arte de uma, me peça (ex.: \"mostra a 3\"). Para aprovar só algumas, toque em Escolher "
                  "ou responda com os números (ex.: \"aprovar 1, 3 e 5\")."
                  + (" As reprovadas pelo Crítico só entram se você escolher pelo número." if k < len(ps) else ""))
    login, sid = semana.get("login", "matheus"), semana["id"]
    botoes = ([{"id": f"cs:{login}:{sid}:todas", "titulo": "✅ Aprovar todas" if k == len(ps) else f"✅ Aprovar {k} de {len(ps)}"}]
              if k else [])
    botoes += [{"id": f"cs:{login}:{sid}:algumas", "titulo": "☑️ Escolher"},
               {"id": f"cs:{login}:{sid}:refazer", "titulo": "🔁 Refazer"}]
    return "\n".join(linhas), botoes


def _numeros(valor) -> list[int] | None:
    """[1, 3, 5] from a list, "1,3 e 5" or "todas" (None)."""
    if valor is None or (isinstance(valor, str) and valor.strip().lower() in ("", "todas", "todos")):
        return None
    if isinstance(valor, (int, float)):
        valor = [valor]
    if isinstance(valor, str):
        valor = re.findall(r"\d+", valor)
    return sorted({int(x) for x in valor})


def _jpg(origem: Path) -> Path:
    """A .png from the render becomes a .jpg (the Graph API takes JPEG only)."""
    if origem.suffix.lower() != ".png":
        return origem
    from PIL import Image
    destino = origem.with_suffix(".jpg")
    with Image.open(origem) as im:
        im.convert("RGB").save(destino, "JPEG", quality=92)
    return destino


def _subir_pelo_proxy(local: str, chave: str) -> None:
    """Uploads one file to S3 conteudo/ through the host proxy (a 1-hour PUT link). Raises with the reason."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(f"{PROXY}/arquivos/conteudo_subir", data=json.dumps({"chave": chave}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        out = {"error": f"o proxy recusou o envio (http {e.code})"}
    except OSError as e:
        out = {"error": f"proxy fora do ar ({e})"}
    if not out.get("url"):
        raise RuntimeError(out.get("error", "sem link de envio"))
    tipo = "video/mp4" if chave.endswith(".mp4") else "image/jpeg"
    put = urllib.request.Request(out["url"], data=Path(local).read_bytes(), method="PUT", headers={"Content-Type": tipo})
    with urllib.request.urlopen(put, timeout=300) as r:
        r.read()


def _chave(sid: str, pid: str, nome: str) -> str:
    return f"conteudo/semanas/{sid}/{pid}/{re.sub(r'[^A-Za-z0-9._-]', '-', nome)}"


def _para_s3(p: dict, sid: str, subir) -> tuple[list, str]:
    """(file keys, cover key) in S3: a file already under conteudo/ stays; a local one is converted, uploaded and
    kept in cache/<id>/ for the publish gate's Crítico."""
    cache = c().PASTA / "cache" / p["id"]
    def um(a: str) -> str:
        if a.startswith(c().PREFIXO):
            return a
        local = _jpg(Path(a))
        chave = _chave(sid, p["id"], local.name)
        subir(str(local), chave)
        cache.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, cache / chave.rsplit("/", 1)[-1])
        return chave
    return [um(a) for a in p["arquivos"]], (um(p["capa"]) if p.get("capa") else "")


def aprovar(sid: str, numeros=None, quem: str = "matheus", agora: float | None = None, subir=None) -> dict:
    """Matheus's approval: numeros None = "Aprovar todas" (what the Crítico did not reprove); a list = exactly those,
    reproved ones included as his override. Each approved one is uploaded and put in the agenda by
    conteudo.agendar(), one by one, so one bad file does not hold the others."""
    agora = time.time() if agora is None else agora
    escolhidos = _numeros(numeros)
    hoje = _hoje(agora).isoformat()
    with _exclusivo():
        semana = carregar(sid)
        if not semana:
            return {"ok": False, "erro": f"semana {sid} não existe"}
        if semana["estado"] not in ("proposta", "parcial"):
            return {"ok": False, "erro": f"a semana {sid} está {semana['estado']}: use a mensagem mais nova"}
        if escolhidos is None:
            alvo = _aprovaveis(semana)
        else:
            fora = [n for n in escolhidos if not 1 <= n <= len(semana["propostas"])]
            if fora:
                return {"ok": False, "erro": f"número fora da lista: {fora}"}
            alvo = [p for p in semana["propostas"] if p["n"] in escolhidos]
        agendados, recusados = [], []
        conteudo, antes = c(), c().AUTOR["quem"]
        conteudo.AUTOR["quem"] = f"{quem}: aprovou a semana {sid}"
        try:
            for p in alvo:
                if p["estado"] != "proposta":
                    recusados.append({"n": p["n"], "motivo": f"já está {p['estado']}"})
                    continue
                motivo = p["problema"] or ("o dia já passou" if p["data"] < hoje else "")
                if not motivo:
                    try:
                        arquivos, capa = _para_s3(p, sid, subir or _subir_pelo_proxy)
                    except Exception as exc:
                        motivo = f"o arquivo não subiu para o S3 ({str(exc)[:120]})"
                if not motivo:
                    item = {"id": p["id"], "data": p["data"], "hora": p["hora"], "tipo": p["tipo"], "arquivos": arquivos,
                            "legenda": p["legenda"], "origem": {"semana": sid, "n": p["n"], "titulo": p["titulo"]}}
                    if capa:
                        item["capa"] = capa
                    if p["critica"]["veredito"] == "reprova":  # he picked it by number after seeing the reprova
                        item["liberado"] = {"por": quem, "em": agora, "motivo": "aprovou na semana apesar do Crítico",
                                            "critica": p["critica"]["motivos"]}
                    r = conteudo.agendar([item], agora)
                    motivo = "" if r["ok"] else r["erro"]
                if motivo:
                    p.update(estado="erro", erro=motivo)
                    recusados.append({"n": p["n"], "motivo": motivo})
                else:
                    p.update(estado="agendada", aprovada_em=agora, aprovada_por=quem,
                             **({"liberado": True} if p["critica"]["veredito"] == "reprova" else {}))
                    agendados.append(p["n"])
        finally:
            conteudo.AUTOR["quem"] = antes
        abertas = [p for p in semana["propostas"] if p["estado"] == "proposta"]
        semana["estado"] = "parcial" if abertas else "aprovada"
        _gravar(semana)
    conteudo._diario({"semana": sid, "aprovada_por": quem, "agendados": agendados, "recusados": recusados})
    return {"ok": bool(agendados) or not recusados, "semana": sid, "agendados": agendados, "recusados": recusados,
            "texto": texto_aprovacao(semana, agendados, recusados)}


def texto_aprovacao(semana: dict, agendados: list, recusados: list) -> str:
    por_n = {p["n"]: p for p in semana["propostas"]}
    linhas = []
    if agendados:
        linhas.append("✅ Agendados: " + ", ".join(f"{n} ({_rotulo_dia(por_n[n]['data'])})" for n in agendados)
                      + ". Saem às " + por_n[agendados[0]]["hora"] + " de cada dia.")
    for r in recusados:
        linhas.append(f"Não agendei a {r['n']}: {_texto(r['motivo'], 160)}")
    if not linhas:
        linhas.append("Nada para agendar: as que sobraram foram reprovadas pelo Crítico ou não têm arquivo.")
    abertas = [str(p["n"]) for p in semana["propostas"] if p["estado"] == "proposta"]
    if abertas:
        linhas.append("Ainda esperando você: " + ", ".join(abertas) + ".")
    return "\n".join(linhas)


def refazer(sid: str) -> dict:
    with _exclusivo():
        semana = carregar(sid)
        if not semana or semana["estado"] not in ("proposta", "parcial"):
            return {"ok": False, "erro": f"a semana {sid} não está mais aberta"}
        semana["estado"] = "refazer"
        for p in semana["propostas"]:
            if p["estado"] == "proposta":
                p["estado"] = "refazer"
        _gravar(semana)
    c()._diario({"semana": sid, "refazer": True})
    return {"ok": True, "semana": sid}


def ver(sid: str = "") -> dict:
    """A week as the agent shows it (the local art files included, to send when he asks "mostra a 3")."""
    semana = carregar(sid) if sid else ultima()
    if not semana:
        return {"ok": False, "erro": "nenhuma semana proposta ainda"}
    return {"ok": True, "semana": semana["id"], "estado": semana["estado"],
            "propostas": [{k: p.get(k) for k in ("n", "data", "hora", "tipo", "titulo", "legenda", "arquivos", "capa",
                                                 "critica", "problema", "estado", "erro")} for p in semana["propostas"]]}


def botao(login: str, botao_id: str, subir=None) -> dict:
    """A button of the week message or of a blocked post ("cs:<login>:<semana|post>:<acao>"), for the Telegram
    receiver: {"mensagem": text to send back} or {"conversa": text to hand to the agent in his chat}; {} when the
    button is not his."""
    _, dono, alvo, acao = (str(botao_id).split(":") + ["", "", "", ""])[:4]
    if dono != login:
        return {}
    if acao == "liberar":
        r = c().liberar(alvo, "tocou em Publicar mesmo assim", quem=f"{login} (botão)")
        if not r["ok"]:
            return {"mensagem": f"Não liberei: {r['erro']}"}
        return {"mensagem": f"🔓 Liberado. O post {alvo} sai no horário dele ({r['hora']} de {_rotulo_dia(r['data'])}), "
                            "se ainda for o dia dele; senão, fica pendente e eu te aviso."}
    try:
        semana = carregar(alvo)
    except ValueError:
        semana = None
    if not semana or semana["estado"] not in ("proposta", "parcial"):
        return {"mensagem": "Essa semana já foi decidida ou refeita; vale a mensagem mais nova."}
    if acao == "todas":
        return {"mensagem": aprovar(alvo, None, quem=f"{login} (botão)", subir=subir)["texto"]}
    lista = "\n".join(f"{p['n']}. {_rotulo_dia(p['data'])} · {p['titulo']} ({p['critica']['veredito']})"
                      for p in semana["propostas"] if p["estado"] == "proposta")
    if acao == "algumas":
        return {"conversa": (f"☑️ Quero aprovar só algumas propostas da semana {alvo}:\n{lista}\n\nPergunte em uma linha "
                             f"quais números. Quando eu responder, use `conteudo` acao \"aprovar_semana\" com semana "
                             f"\"{alvo}\" e numeros = só os que eu disse. Não aprove nenhum outro.")}
    if acao == "refazer":
        refazer(alvo)
        return {"conversa": (f"🔁 Quero refazer a semana de posts {alvo}:\n{lista}\n\nPergunte em uma linha o que eu "
                             "quero diferente. Quando eu responder, escreva 7 propostas novas com isso e chame "
                             "`conteudo` acao \"propor_semana\" (ela desenha, passa pelo Crítico e me manda de novo).")}
    return {}


def _enviar_ponte(login: str, texto: str, botoes: list) -> str:
    """'' when sent: the Telegram bridge of plugins/whatsapp (up to 3 buttons)."""
    try:
        ponte = sys.modules.get("whatsapp_ponte")
        if ponte is None:
            s = importlib.util.spec_from_file_location("whatsapp_ponte", PONTE)
            ponte = importlib.util.module_from_spec(s)
            s.loader.exec_module(ponte)
        return ponte.enviar(login, texto, botoes=botoes, rotina="🗓️ Semana de posts", reenviar=True)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"

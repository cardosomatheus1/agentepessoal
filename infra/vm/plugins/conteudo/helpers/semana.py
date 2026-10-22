"""The week of @raiz.connect posts, proposed every Monday instead of an agenda assembled by hand (20/10, approved by
Matheus). The routine reads what did well (conteudo desempenho), the competitors (concorrentes) and the niche's
viral videos (video), then hands 4 feed ideas and 7 stories to propor() (22/10: 2 carousels, 2 videos and a story a
day): each feed idea is drawn by the Designer, each story here from the kit's layouts (story.py), all judged by the
Crítico (plugins/especialistas), and Matheus gets ONE Telegram message with the 11 and three buttons (approve all, choose,
redo). aprovar() writes the approved ones into the same agenda.json the daily job loop publishes from, through
conteudo.agendar(), so publishing is unchanged. Rules that are code:
- without the especialistas plugin a proposal says the review is missing; nothing is ever approved by itself;
- "Aprovar todas" leaves out what the Crítico reproved: those go only when he picks them by number, and that
  override is kept on the post (liberado), so the publish gate does not block what he already decided;
- a week that was redone (new version) refuses the old message's buttons.
State: /a0/usr/conteudo/semanas/<id>.json, written only here, under its own lock; journal: conteudo's diario.jsonl.

Videos (22/10, Matheus: "Leve"): the Designer renders a Reel from the moldes as a preview and the narration only; the
week message tells Matheus to listen first (decision #39), and the video itself is made after he approves, in the
background (helpers/video_fila.py, one at a time), and goes into the agenda by itself when ready (concluir_video)."""

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

# Matheus, 22/10: "deve ser 4 por semana, 2 carrosseis e 2 videos e story sim todo dia" -> carousel on Tuesday and
# Friday, video on Wednesday and Sunday (weekday numbers, Monday = 0), and one story a day at 9h.
PLANO_FEED = (("CARROSSEL", 1), ("REELS", 2), ("CARROSSEL", 4), ("REELS", 6))
PROPOSTAS = len(PLANO_FEED)
STORIES = 7
HORA = "11:45"  # the hour every post of the plan went out so far
HORA_STORY = "09:00"
JANELA_DIAS = 21  # how far ahead to look for free days
PROXY = "http://host.docker.internal:8787"  # the host holds the AWS identity; the container has none
PONTE = Path("/a0/usr/plugins/whatsapp/helpers/ponte.py")
DIAS_SEMANA = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
NOME_TIPO = {"REELS": "Reel", "CARROSSEL": "Carrossel", "IMAGE": "Foto", "STORY": "Story"}
VIDEO, IMAGEM = (".mp4",), (".jpg", ".jpeg", ".png")
SEM_REVISAO = "sem revisão"
REGRAS = ("A Raiz Connect é sistema de gestão para food service, com pedidos do iFood e da 99Food entrando sozinhos: "
          "fala também com pizzaria, hamburgueria, lanchonete e restaurante de delivery (Matheus, 22/10). Tela do sistema "
          "sempre no tema escuro e inteira, com o menu; para mostrar o sistema, vídeo com zoom e movimento. "
          "Fala com o dono do negócio que produz e vende comida, nunca com o consumidor; sem jargão; número sempre "
          "como \"valores de exemplo\"; legenda sem emoji e sem travessão; nunca \"aumente seu lucro\"; oferta: "
          "Lucro na Mão em 30 Dias.")

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


def _ocupados(canal: str) -> set:
    """Days with a live item of that slot (feed or story); a day blocked by the Crítico counts as taken."""
    return {i["data"] for i in c().carregar()["itens"] if i["estado"] not in ("cancelada", "falhou") and c().canal(i) == canal}


def dias_do_feed(agora: float) -> list[tuple[str, str]]:
    """[(formato, day)] for the plan's slots of the coming week (tomorrow + 6 days) that are still free: a slot already
    filled (a post moved there by hand) is not proposed again, and nothing spills into the week after."""
    ocupados, hoje, saida = _ocupados("feed"), _hoje(agora), []
    for k in range(1, 8):
        dia = hoje + dt.timedelta(days=k)
        for formato, semana_dia in PLANO_FEED:
            if dia.weekday() == semana_dia and dia.isoformat() not in ocupados:
                saida.append((formato, dia.isoformat()))
    return saida


def dias_livres(agora: float, n: int = STORIES, canal: str = "story", janela: int = 7) -> list[str]:
    """The first n days from tomorrow, within `janela` days, with no live item of that slot."""
    ocupados = _ocupados(canal)
    hoje, livres = _hoje(agora), []
    for k in range(1, janela + 1):
        dia = (hoje + dt.timedelta(days=k)).isoformat()
        if dia not in ocupados:
            livres.append(dia)
        if len(livres) == n:
            break
    return livres


_S: dict = {}


def story():
    """story.py next to this file (the tests may pin their own in _S["fixo"])."""
    if "fixo" in _S:
        return _S["fixo"]
    caminho = Path(__file__).resolve().parent / "story.py"
    marca = caminho.stat().st_mtime_ns
    if _S.get("marca") != marca:
        spec = importlib.util.spec_from_file_location("conteudo_story", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _S.update(marca=marca, m=m)
    return _S["m"]


def _desenhar_story(esp, campos: dict, saida: Path) -> dict:
    """One story: drawn here from the kit's layouts (helpers/story.py) and judged by the Crítico."""
    try:
        story().renderizar(campos, str(saida))
    except Exception as exc:
        return {"arquivos": [], "problema": f"o story não foi desenhado ({type(exc).__name__}: {str(exc)[:140]})",
                "critica": {"veredito": SEM_REVISAO, "motivos": ["não há arte para julgar"], "sugestoes": []}}
    if esp is None:
        critica = {"veredito": SEM_REVISAO, "motivos": ["o Crítico (plugin especialistas) não está instalado"], "sugestoes": []}
    else:
        try:
            critica = _critica(esp.criticar("story", {"formato": "STORY", "legenda": _texto(campos.get("manchete"), 200),
                                                      "texto": _texto(campos.get("texto"), 300), "imagens": [str(saida)]}))
        except Exception as exc:
            critica = {"veredito": SEM_REVISAO, "motivos": [f"o Crítico falhou ({type(exc).__name__})"], "sugestoes": []}
    return {"arquivos": [str(saida)], "problema": "", "critica": critica}


REFAZER_STORY = 2  # 22/10, Matheus: "Se o crítico rejeita, automáticamente deveria ser refeito"
STORY_REGRAS = (
    "Layouts: \"dica\" (manchete, destaque, texto, chamada); \"post-novo\" e \"video-novo\" (chamam para o post do feed "
    "do dia: manchete, destaque, chamada); \"bastidor\" (tela = caminho de uma tela real em "
    "/a0/usr/plugins/conteudo/story/telas/, pergunta \"Responde aqui no direct: ...\"); \"oferta\" (Lucro na Mão em 30 "
    "Dias: manchete, destaque, itens, chamada; preco e preco_nota só se já estavam). Esquema da semana: seg dica; ter e "
    "sex post-novo; qua e dom video-novo; qui bastidor; sáb oferta. Manchete até 90 letras, sem emoji, sem travessão, "
    "R$ só com \"valores de exemplo\"; garantia sempre com \"a gente não cobra a próxima mensalidade\".")


def _tarefa_story(campos: dict, critica: dict) -> str:
    return ("O Crítico reprovou o story abaixo. Refaça os campos resolvendo cada motivo, mantendo o layout do dia (troque "
            "só se o motivo for o layout) e devolva só o JSON dos campos.\n\n## Motivos do Crítico\n"
            + "\n".join(f"- {m}" for m in critica.get("motivos") or [])
            + f"\n\n## Campos atuais\n{json.dumps(campos, ensure_ascii=False)[:3000]}\n\n{STORY_REGRAS}")


def _refazer_story(esp, campos: dict, critica: dict, saida: Path) -> tuple[dict, dict] | None:
    """The Designer rewrites the story's fields with the Crítico's reasons; drawn and judged again. None when he
    gave nothing usable (no answer, not JSON, or fields the story's own rules refuse)."""
    r = esp.chamar("designer", _tarefa_story(campos, critica), {"story": campos, "imagens": []})
    achado = re.search(r"\{.*\}", (r or {}).get("texto") or "", re.S) if not (r or {}).get("erro") else None
    try:
        novo = json.loads(achado.group(0)) if achado else None
    except ValueError:
        novo = None
    if not isinstance(novo, dict):
        return None
    novo = {k: v for k, v in novo.items() if k in story().CAMPOS}
    if story().validar(novo):
        return None
    saida.parent.mkdir(parents=True, exist_ok=True)
    return novo, _desenhar_story(esp, novo, saida)


def refazer_item(item: dict, critica: dict, subir=None) -> dict:
    """The agent redoes a post of the agenda that the advance check reproved (conteudo.conferir_antes): a story from
    its fields, a feed carousel from the Designer's ficha; the new files go to S3 and replace the old ones on the same
    post (conteudo.refeito). {"ok": False, "erro"} when it cannot: made outside the weekly routine (no ficha), a Reel
    (a new narration needs Matheus's ok first, decision #39), or the new version is still reproved."""
    origem = item.get("origem") or {}
    if not origem.get("semana"):
        return {"ok": False, "erro": "foi feito fora da rotina da semana e o agente não tem a ficha para refazer"}
    if item["tipo"] == "REELS":
        return {"ok": False, "erro": "Reel: refazer muda a narração, que precisa do seu ok antes (decisão #39)"}
    sid, n = origem["semana"], origem.get("n")
    semana = carregar(sid) or {}
    p = next((x for x in semana.get("propostas", []) if x["n"] == n), None)
    if not p:
        return {"ok": False, "erro": f"a proposta {n} da semana {sid} não existe mais"}
    esp = c().especialistas()
    if esp is None:
        return {"ok": False, "erro": "o plugin de especialistas não está instalado"}
    k = 1 + int(p.get("refeita") or 0)
    if item["tipo"] == "STORY" and (p.get("spec") or {}).get("story"):
        feito = _refazer_story(esp, p["spec"]["story"], critica, _pasta() / sid / f"story-{n}-a{k}.jpg")
        if not feito:
            return {"ok": False, "erro": "o Designer não devolveu campos válidos para o story"}
        campos, d = feito
        spec_novo, arquivos, nova = {"story": campos}, d["arquivos"], d["critica"]
    elif (p.get("spec") or {}).get("motor") == "molde" and item["tipo"] == "CARROSSEL":
        briefing = {"marca": "raiz", "rede": "instagram @raiz.connect", "formato": p.get("formato_pedido") or item["tipo"],
                    "titulo": p.get("titulo", ""), "ideia": p.get("ideia", ""), "legenda": item.get("legenda", ""),
                    "data": item["data"], "regras": REGRAS}
        vistas = [str(c().PASTA / "cache" / item["id"] / a.rsplit("/", 1)[-1]) for a in item["arquivos"]]
        d = esp.revisar(briefing, p["spec"], critica, vistas)
        tipo, arquivos, _ = tipo_dos_arquivos(d.get("arquivos"))
        if tipo != item["tipo"]:
            return {"ok": False, "erro": "o Designer não entregou um carrossel novo"
                                         + (f" ({_texto('; '.join(d.get('falta') or []), 160)})" if d.get("falta") else "")}
        spec_novo, nova = d.get("spec") or p["spec"], _critica(d.get("critica"))
    else:
        return {"ok": False, "erro": "não há ficha do Designer para refazer este post"}
    if nova["veredito"] != "aprova":
        return {"ok": False, "erro": "a versão refeita também foi reprovada: " + c().uma_linha(nova["motivos"], 160)}
    cache = c().PASTA / "cache" / item["id"]
    cache.mkdir(parents=True, exist_ok=True)
    chaves = []
    try:
        for a in arquivos:
            local = _jpg(Path(a))
            chave = _chave(sid, item["id"], f"a{k}-{local.name}")
            (subir or _subir_pelo_proxy)(str(local), chave)
            shutil.copyfile(local, cache / chave.rsplit("/", 1)[-1])
            chaves.append(chave)
    except Exception as exc:
        return {"ok": False, "erro": f"o arquivo refeito não subiu para o S3 ({str(exc)[:120]})"}
    r = c().refeito(item["id"], chaves, "refeito pelo Designer: " + c().uma_linha(critica.get("motivos") or [], 200))
    if not r["ok"]:
        return r
    with _exclusivo():
        s = carregar(sid)
        alvo = next(x for x in s["propostas"] if x["n"] == n)
        alvo.update(spec=spec_novo, refeita=k, arquivos=chaves, critica=nova)
        _gravar(s)
    return {"ok": True, "arquivos": chaves}


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
            "falta": [str(x) for x in d.get("falta") or []], "critica": _critica(critica),
            **{k: d[k] for k in ("video_pendente", "previa", "folha", "narracao") if d.get(k)}}


def propor(propostas: list, agora: float | None = None, enviar=None, login: str = "matheus", stories=None) -> dict:
    """The week: 4 feed ideas from the routine [{"titulo", "formato" (2 CARROSSEL and 2 REELS), "ideia", "legenda"}]
    and 7 stories [{"layout", "manchete", ...: helpers/story.py}] → each drawn and judged, saved as a new version,
    and the one message with buttons sent to Matheus. Nothing goes into the agenda here."""
    agora = time.time() if agora is None else agora
    try:
        if isinstance(propostas, str):
            propostas = json.loads(propostas)
        if isinstance(stories, str):
            stories = json.loads(stories)
    except ValueError:
        return {"ok": False, "erro": "propostas e stories: listas JSON"}
    propostas = [p for p in propostas or [] if isinstance(p, dict)]
    stories = [x for x in stories or [] if isinstance(x, dict)]
    vagas = dias_do_feed(agora)
    dias_story = dias_livres(agora, STORIES, "story")
    pedidos = sorted(str(p.get("formato") or "").upper() for p in propostas)
    if pedidos != sorted(f for f, _ in vagas):
        livres = ", ".join(f"{_rotulo_dia(d)} {NOME_TIPO[f]}" for f, d in vagas) or "nenhuma"
        return {"ok": False, "erro": f"a semana tem {len(vagas)} vaga(s) no feed ({livres}): mande exatamente essas "
                                     f"(vieram {len(propostas)}: {', '.join(pedidos) or 'nenhuma'})"}
    if len(stories) != len(dias_story):
        livres = ", ".join(_rotulo_dia(d) for d in dias_story) or "nenhum"
        return {"ok": False, "erro": f"a semana tem {len(dias_story)} dia(s) sem story ({livres}): mande um story para "
                                     f"cada (vieram {len(stories)})"}
    if not vagas and not dias_story:
        return {"ok": False, "erro": "a semana que vem já está toda agendada"}
    try:
        esp, nota = c().especialistas(), ""
    except Exception as exc:  # installed but broken: the proposals say so, and nothing is approved by itself
        esp, nota = None, f"o plugin de especialistas não carregou ({type(exc).__name__})"
    base = "s" + _hoje(agora).strftime("%Y%m%d")
    with _exclusivo():
        versao = 1 + max([int(p.stem.split("-")[1]) for p in _pasta().glob(f"{base}-*.json")] or [0])
    sid = f"{base}-{versao}"
    fila = {f: [p for p in propostas if str(p.get("formato") or "").upper() == f] for f in ("CARROSSEL", "REELS")}
    itens = []
    for n, (formato, dia) in enumerate(vagas, start=1):
        p = fila[formato].pop(0)
        briefing = {"marca": "raiz", "rede": "instagram @raiz.connect", "formato": formato,
                    "titulo": _texto(p.get("titulo"), 120), "ideia": _texto(p.get("ideia"), 1200),
                    "legenda": str(p.get("legenda") or "").strip(), "data": dia, "regras": REGRAS}
        d = _desenhar(esp, briefing, p)
        if nota:
            d["critica"]["motivos"] = [nota] + d["critica"]["motivos"]
        legenda = briefing["legenda"] or str(d["spec"].get("legenda") or "").strip()
        pendente = formato == "REELS" and d.get("video_pendente")
        tipo, arquivos, capa = ("REELS", [], "") if pendente else tipo_dos_arquivos(d["arquivos"])
        problema = ""
        if not tipo:
            problema = "o Designer não entregou arquivo publicável (.mp4, ou de 1 a 10 imagens)" + (
                f": {_texto('; '.join(d['falta']), 160)}" if d["falta"] else "")
        else:
            problema = c().validar_legenda(legenda)
        itens.append({"n": n, "id": f"{sid}-{n}", "data": dia, "hora": str(p.get("hora") or HORA), "titulo": briefing["titulo"],
                      "ideia": briefing["ideia"], "formato_pedido": formato, "tipo": tipo, "arquivos": arquivos,
                      "capa": capa, "legenda": legenda, "spec": d["spec"], "critica": d["critica"],
                      "problema": problema, "estado": "proposta",
                      **({"video": {"estado": "aguardando_aprovacao", "molde": d["spec"].get("molde"),
                                    "formato": str(d["spec"].get("formato") or "reel"), "ficha": d["spec"].get("ficha")},
                          "previa": d.get("previa", []), "folha": d.get("folha", ""), "narracao": d.get("narracao", "")}
                         if pendente else {})})
    for n, (campos, dia) in enumerate(zip(stories, dias_story), start=len(vagas) + 1):
        d = _desenhar_story(esp, campos, _pasta() / sid / f"story-{n}.jpg")
        for k in range(REFAZER_STORY if esp is not None else 0):  # reproved: redone here, before Matheus sees it
            if d["critica"]["veredito"] != "reprova":
                break
            feito = _refazer_story(esp, campos, d["critica"], _pasta() / sid / f"story-{n}-r{k + 1}.jpg")
            if not feito:
                break
            campos, d = feito
        titulo = f"{campos.get('layout', '?')}: {_texto(campos.get('manchete') or 'oferta Lucro na Mão', 100)}"
        itens.append({"n": n, "id": f"{sid}-{n}", "data": dia, "hora": HORA_STORY, "titulo": titulo, "ideia": "",
                      "formato_pedido": "STORY", "tipo": "STORY" if d["arquivos"] else "", "arquivos": d["arquivos"],
                      "capa": "", "legenda": _texto(campos.get("manchete"), 200), "spec": {"story": campos},
                      "critica": d["critica"], "problema": d["problema"], "estado": "proposta"})
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
    """The one Telegram message: the proposals, the Crítico's word on each, and the buttons."""
    ps = semana["propostas"]
    datas = sorted(p["data"] for p in ps)
    linhas = [f"*Semana de posts da @raiz.connect* ({_rotulo_dia(datas[0])} a {_rotulo_dia(datas[-1])}): "
              f"{sum(p['formato_pedido'] != 'STORY' for p in ps)} no feed e {sum(p['formato_pedido'] == 'STORY' for p in ps)} stories"]
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
        if p["formato_pedido"] == "STORY":
            linhas.append(f"{p['n']}. *{_rotulo_dia(p['data'])}* · Story {p['hora']} · {p['titulo']}\n   {critico}")
        else:
            linhas.append(f"{p['n']}. *{_rotulo_dia(p['data'])}* · {NOME_TIPO.get(p['tipo'], '?')} · {p['titulo']}\n"
                          f"   {_texto(p['legenda'], 110)}\n   {critico}"
                          + (f"\n   🎧 Ouça a narração antes (me peça \"mostra a {p['n']}\"): o vídeo só é feito depois que "
                             "você aprovar" if p.get("video") else ""))
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
        agendados, recusados, gerando = [], [], []
        conteudo, antes = c(), c().AUTOR["quem"]
        conteudo.AUTOR["quem"] = f"{quem}: aprovou a semana {sid}"
        try:
            for p in alvo:
                if p["estado"] != "proposta":
                    recusados.append({"n": p["n"], "motivo": f"já está {p['estado']}"})
                    continue
                motivo = p["problema"] or ("o dia já passou" if p["data"] < hoje else "")
                if not motivo and (p.get("video") or {}).get("estado") == "aguardando_aprovacao":
                    p["video"]["estado"] = "na_fila"  # decision #39: the video is made only now, after his approval
                    p.update(estado="gerando_video", aprovada_em=agora, aprovada_por=quem,
                             **({"liberado": True} if p["critica"]["veredito"] == "reprova" else {}))
                    gerando.append(p["n"])
                    continue
                if not motivo:
                    motivo = _agendar_item(conteudo, p, sid, quem, agora, subir)
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
    for n in gerando:
        iniciar_video(sid, n)
    conteudo._diario({"semana": sid, "aprovada_por": quem, "agendados": agendados, "recusados": recusados,
                      **({"gerando_video": gerando} if gerando else {})})
    return {"ok": bool(agendados or gerando) or not recusados, "semana": sid, "agendados": agendados,
            "recusados": recusados, "gerando_video": gerando,
            "texto": texto_aprovacao(semana, agendados, recusados, gerando)}


def _agendar_item(conteudo, p: dict, sid: str, quem: str, agora: float, subir=None) -> str:
    """One approved proposal uploaded and put in the agenda; '' when it went, else why not."""
    try:
        arquivos, capa = _para_s3(p, sid, subir or _subir_pelo_proxy)
    except Exception as exc:
        return f"o arquivo não subiu para o S3 ({str(exc)[:120]})"
    item = {"id": p["id"], "data": p["data"], "hora": p["hora"], "tipo": p["tipo"], "arquivos": arquivos,
            "legenda": p["legenda"], "origem": {"semana": sid, "n": p["n"], "titulo": p["titulo"]}}
    if capa:
        item["capa"] = capa
    if p["critica"]["veredito"] == "reprova":  # he picked it by number after seeing the reprova
        item["liberado"] = {"por": quem, "em": agora, "motivo": "aprovou na semana apesar do Crítico",
                            "critica": p["critica"]["motivos"]}
    r = conteudo.agendar([item], agora)
    return "" if r["ok"] else r["erro"]


def iniciar_video(sid: str, n: int, popen=None) -> None:
    """The approved Reel rendered in the background by helpers/video_fila.py (it waits for the one before)."""
    import subprocess
    pasta = _pasta() / sid
    pasta.mkdir(parents=True, exist_ok=True)
    with open(pasta / f"video-{n}.log", "a") as log:
        (popen or subprocess.Popen)([sys.executable, str(Path(__file__).resolve().parent / "video_fila.py"), sid, str(n)],
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def concluir_video(sid: str, n: int, video: str = "", erro: str = "", agora: float | None = None, subir=None,
                   enviar=None) -> dict:
    """The background render finished: the video goes into the agenda (it was approved already) and Matheus is told
    in one line; a failure is kept on the proposal and told too."""
    agora = time.time() if agora is None else agora
    with _exclusivo():
        semana = carregar(sid)
        p = next((x for x in (semana or {}).get("propostas", []) if x["n"] == int(n)), None)
        if not p or p.get("estado") != "gerando_video":
            return {"ok": False, "erro": f"a {n} da semana {sid} não está esperando vídeo"}
        motivo = erro or ("" if video and Path(video).is_file() else "o vídeo não foi gerado")
        if not motivo and p["data"] < _hoje(agora).isoformat():
            motivo = "o dia do post já passou"
        if not motivo:
            p["arquivos"] = [video]
            conteudo, antes = c(), c().AUTOR["quem"]
            conteudo.AUTOR["quem"] = f"{p.get('aprovada_por', 'matheus')}: aprovou a semana {sid} (vídeo pronto)"
            try:
                motivo = _agendar_item(conteudo, p, sid, p.get("aprovada_por", "matheus"), agora, subir)
            finally:
                conteudo.AUTOR["quem"] = antes
        if motivo:
            p.update(estado="erro", erro=motivo)
            p["video"]["estado"] = "erro"
        else:
            p.update(estado="agendada")
            p["video"]["estado"] = "pronto"
        _gravar(semana)
    c()._diario({"semana": sid, "video": n, "agendado": not motivo, **({"erro": motivo} if motivo else {})})
    texto = (f"🎬 O vídeo da {n} ({p['titulo']}) ficou pronto e está agendado para {_rotulo_dia(p['data'])} às {p['hora']}."
             if not motivo else f"⚠️ O vídeo da {n} ({p['titulo']}) não entrou na agenda: {_texto(motivo, 200)}")
    (enviar or _enviar_ponte)(semana.get("login", "matheus"), texto, [])
    return {"ok": not motivo, "semana": sid, "n": int(n), **({"erro": motivo} if motivo else {})}


def texto_aprovacao(semana: dict, agendados: list, recusados: list, gerando: list = ()) -> str:
    por_n = {p["n"]: p for p in semana["propostas"]}
    linhas = []
    if gerando:
        linhas.append("🎬 Gerando o vídeo de " + ", ".join(str(n) for n in gerando) + " (cerca de 1 hora cada, um por "
                      "vez). Cada um entra na agenda sozinho quando ficar pronto, e eu te aviso.")
    if agendados:
        linhas.append("✅ Agendados: " + ", ".join(f"{n} ({_rotulo_dia(por_n[n]['data'])})" for n in agendados)
                      + ". Saem às " + por_n[agendados[0]]["hora"] + " de cada dia.")
    for r in recusados:
        linhas.append(f"Não agendei a {r['n']}: {_texto(r['motivo'], 160)}")
    if not linhas and not gerando:
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
                                                 "critica", "problema", "estado", "erro", "narracao", "folha")
                           if k not in ("narracao", "folha") or p.get(k)} for p in semana["propostas"]]}


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
                             "quero diferente. Quando eu responder, escreva de novo as 4 propostas do feed e os 7 stories com isso e chame "
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

"""The week of @raiz.connect posts, created every Monday instead of an agenda assembled by hand (20/10). The routine
reads what did well (conteudo desempenho), the competitors (concorrentes) and the niche's viral videos (video), then
hands 4 feed ideas and 7 stories to propor() (22/10: 2 carousels, 2 videos and a story a day): each feed idea is drawn
by the Designer, each story here from the kit's layouts (story.py), all judged by the Crítico (plugins/especialistas).

04/11, Matheus: "Mas eu já falei que eu não quero um agente para ficar esperando eu falar. Ele tem que criar, se já tem
um crítico para ver o que passa e o que não passa, ele tem que decidir se posta, se não posta, as decisões que tem que
ser tomadas, etc., sem depender de mim." So the Crítico is the gate and nobody waits for him:
- what the Crítico approved goes into the agenda right away (_decidir -> aprovar(), as "gestor: o Crítico aprovou");
- what he reproved is redone by the agent, one attempt per pass of the job loop (passo_autonomo), up to REFAZER_AUTO
  times; still reproved, the agent decides by itself: one NEW idea for the same slot (through the Crítico again), and if
  that fails too the day stays without that post. A story that calls a post that will not go out becomes a "dica";
- Matheus gets only notices of what was decided (no buttons). The old buttons (aprovar, escolher, refazer, "Publicar
  mesmo assim") still work if he taps one from an old message, and his explicit word still overrides (aprovar by number);
- without the especialistas plugin (or a Crítico that gives no clear verdict) nothing is ever scheduled by itself.
aprovar() writes into the same agenda.json the daily job loop publishes from, through conteudo.agendar(), so
publishing is unchanged. State: /a0/usr/conteudo/semanas/<id>.json, written only here, under its own lock; journal:
conteudo's diario.jsonl.

Videos (22/10): the Designer renders a Reel from the moldes as a preview and the narration only; the Crítico judges
that preview, and once it is approved the video itself is made in the background (helpers/video_fila.py, one at a
time) and goes into the agenda by itself when ready (concluir_video). Decision #39 (his ear on the narration first)
was replaced by the 04/11 decision."""

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
REFAZER_AUTO = 2  # 04/11: redo attempts of a reproved proposal before the agent decides (new idea, then no post)
FOLGA_AUTO_MIN = 90  # a proposal is (re)done only if it goes out later than this: Designer + Crítico take minutes
QUEM_AUTO = "gestor: o Crítico aprovou"
ROTINA_AVISO = "🧭 Gestor de conteúdo"
REGRAS = ("A Raiz Connect é sistema de gestão para food service, com pedidos do iFood e da 99Food entrando sozinhos: "
          "fala também com pizzaria, hamburgueria, lanchonete e restaurante de delivery (Matheus, 22/10). Tela do sistema "
          "sempre no tema escuro e inteira, com o menu; para mostrar o sistema, vídeo com zoom e movimento. "
          "Fala com o dono do negócio que produz e vende comida, nunca com o consumidor; sem jargão; número sempre "
          "como \"valores de exemplo\"; legenda sem emoji e sem travessão; nunca \"aumente seu lucro\"; oferta: "
          "Lucro na Mão em 30 Dias.")
# 05/11, Matheus: "é bom pelo menos 1 por semana com tom de humor". Formato que viraliza (POV da @trinta.app com As
# Branquelas): a dor séria do dono dita como piada de identificação, com referência da cultura pop.
HUMOR = ("POST DE HUMOR (Matheus, 05/11): a dor séria do dono de comida (não saber o custo do prato, estoque sumindo, "
         "fim do mês sem saber o lucro) dita como piada de identificação, com uma referência da cultura pop que todo "
         "brasileiro reconhece em 1 segundo (novela, filme, Chaves, Nazaré fazendo conta, Seu Madruga, Faustão "
         "\"errou\", BBB). Formato POV: o celular com o caderno no chute e o meme por cima, a legenda \"POV: eu "
         "tentando ...\" e a virada para a tela da Raiz com \"a Raiz já sabe\". O meme vai DENTRO do vídeo (Matheus, "
         "05/11: \"Falei p ter o meme\"); julgue o vídeo pelos quadros. Humor leve, nunca debochando do cliente. As "
         "outras regras valem igual.")
SEMANAS_COM_HUMOR = 2  # with 2 or more feed slots free, at least one proposal must have "tom": "humor"

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
_G: dict = {}


def gestor():
    """gestor.py next to this file, sharing this file's conteudo instance (the tests may pin theirs in _G["fixo"])."""
    if "fixo" in _G:
        return _G["fixo"]
    caminho = Path(__file__).resolve().parent / "gestor.py"
    marca = caminho.stat().st_mtime_ns
    if _G.get("marca") != marca:
        spec = importlib.util.spec_from_file_location("conteudo_gestor_semana", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _G.update(marca=marca, m=m)
    _G["m"]._C["fixo"] = c()
    return _G["m"]


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


CHAMA = {"video-novo": ("REELS",), "post-novo": ("CARROSSEL", "IMAGE")}  # the story layouts that send to the day's post


def _post_do_dia(campos: dict, dia: str, itens: list) -> tuple[dict | None, str]:
    """(the feed post a "video-novo"/"post-novo" story calls, why it cannot call it). 26/10: three versions of the week
    had the 9h story say "Veja o vídeo de hoje" for Reels whose render had failed, one about stock on a day whose Reel
    was about iFood, and a "post de hoje" on a day with no post; the Crítico, seeing the story alone, approved them."""
    tipos = CHAMA.get(campos.get("layout"))
    if not tipos:
        return None, ""
    nome = " ou ".join(NOME_TIPO[t] for t in tipos)
    alvo = next((i for i in itens if i["data"] == dia and i["formato_pedido"] in tipos), None)
    if alvo is None:
        na_agenda = next((i for i in c().carregar()["itens"] if i["data"] == dia and i["tipo"] in tipos
                          and i["estado"] not in ("cancelada", "falhou")), None)
        if na_agenda:
            return {"tipo": na_agenda["tipo"], "titulo": _texto(na_agenda.get("legenda"), 120),
                    "legenda": _texto(na_agenda.get("legenda"), 300)}, ""
        return None, f"chama o post do dia, mas {_rotulo_dia(dia)} não tem {nome} no feed"
    if alvo["problema"] or alvo["critica"]["veredito"] == "reprova":
        return None, (f"chama o {NOME_TIPO[alvo['formato_pedido']]} de {_rotulo_dia(dia)}, que não ficou pronto ("
                      + _texto(alvo["problema"] or c().uma_linha(alvo["critica"]["motivos"], 120), 140) + ")")
    return {"tipo": alvo["formato_pedido"], "titulo": alvo["titulo"], "legenda": _texto(alvo["legenda"], 300),
            "imagem": _imagem_do_post(alvo)}, ""


def _imagem_do_post(alvo: dict) -> str:
    """A picture of the post for the story's cover: the Reel's cover or first screen, the carousel's first slide."""
    tela = ((((alvo.get("spec") or {}).get("ficha") or {}).get("telas") or [{}])[0] or {}).get("imagem") or ""
    for a in [alvo.get("capa") or ""] + [x for x in alvo.get("arquivos") or [] if str(x).lower().endswith(IMAGEM)] + [tela]:
        a = str(a).removeprefix("file://")
        if a and Path(a).is_file():
            return a
    return ""


def _desenhar_story(esp, campos: dict, saida: Path, post: dict | None = None) -> dict:
    """One story: drawn here from the kit's layouts (helpers/story.py) and judged by the Crítico; a story that calls
    the day's post goes to the Crítico with that post, so it can see whether both talk about the same thing."""
    try:
        story().renderizar(campos, str(saida))
    except Exception as exc:
        return {"arquivos": [], "problema": f"o story não foi desenhado ({type(exc).__name__}: {str(exc)[:140]})",
                "critica": {"veredito": SEM_REVISAO, "motivos": ["não há arte para julgar"], "sugestoes": []}}
    if esp is None:
        critica = {"veredito": SEM_REVISAO, "motivos": ["o Crítico (plugin especialistas) não está instalado"], "sugestoes": []}
    else:
        try:
            material = {"formato": "STORY", "layout": campos.get("layout"), "legenda": _texto(campos.get("manchete"), 200),
                        "texto": _texto(campos.get("texto"), 300), "chamada": _texto(campos.get("chamada"), 120),
                        "imagens": [str(saida)]}
            if post:
                material["post_do_dia"] = {k: post[k] for k in ("tipo", "titulo", "legenda")}
            critica = _critica(esp.criticar("story", material))
        except Exception as exc:
            critica = {"veredito": SEM_REVISAO, "motivos": [f"o Crítico falhou ({type(exc).__name__})"], "sugestoes": []}
    return {"arquivos": [str(saida)], "problema": "", "critica": critica}


REFAZER_STORY = 2  # 22/10, Matheus: "Se o crítico rejeita, automáticamente deveria ser refeito"
STORY_REGRAS = (
    "Layouts: \"dica\" (manchete, destaque, texto, chamada); \"post-novo\" e \"video-novo\" (chamam para o post do feed "
    "do dia: manchete, destaque, chamada); \"bastidor\" (tela = caminho de uma tela real em "
    "/a0/usr/plugins/conteudo/story/telas/, pergunta \"Responde aqui no direct: ...\"); \"oferta\" (Lucro na Mão em 30 "
    "Dias: manchete, destaque, itens, chamada; preco e preco_nota só se já estavam). Esquema da semana: seg dica; ter e "
    "sex post-novo; qua e dom video-novo; qui bastidor; sáb oferta. Nunca \"salve\" (story não se salva). "
    "Manchete até 90 letras, sem emoji, sem travessão, "
    "R$ só com \"valores de exemplo\"; garantia sempre com \"a gente não cobra a próxima mensalidade\".")


def _tarefa_story(campos: dict, critica: dict, post: dict | None = None) -> str:
    chama = (f"\n\n## O post do dia que este story chama\n{post['tipo']}: {post['titulo']} ({post['legenda']}). A manchete "
             "fala do mesmo assunto." if post else "")
    return ("O Crítico reprovou o story abaixo. Refaça os campos resolvendo cada motivo, mantendo o layout do dia (troque "
            "só se o motivo for o layout) e devolva só o JSON dos campos.\n\n## Motivos do Crítico\n"
            + "\n".join(f"- {m}" for m in critica.get("motivos") or [])
            + f"\n\n## Campos atuais\n{json.dumps(campos, ensure_ascii=False)[:3000]}{chama}\n\n{STORY_REGRAS}")


def _refazer_story(esp, campos: dict, critica: dict, saida: Path, post: dict | None = None) -> tuple[dict, dict] | None:
    """The Designer rewrites the story's fields with the Crítico's reasons; drawn and judged again. None when he
    gave nothing usable (no answer, not JSON, or fields the story's own rules refuse)."""
    r = esp.chamar("designer", _tarefa_story(campos, critica, post), {"story": campos, "imagens": []})
    achado = re.search(r"\{.*\}", (r or {}).get("texto") or "", re.S) if not (r or {}).get("erro") else None
    try:
        novo = json.loads(achado.group(0)) if achado else None
    except ValueError:
        novo = None
    if not isinstance(novo, dict):
        return None
    novo = {k: v for k, v in novo.items() if k in story().CAMPOS}
    telas = story().PASTA / "telas"  # only the system's own screens or the picture he already had: no other file
    if novo.get("imagem") not in (None, campos.get("imagem")) or (
            novo.get("tela") and Path(str(novo["tela"])).resolve().parent != telas.resolve()):
        return None
    if story().validar(novo):
        return None
    if post and post.get("imagem") and not novo.get("imagem") and campos.get("imagem") == post["imagem"]:
        novo["imagem"] = post["imagem"]
    saida.parent.mkdir(parents=True, exist_ok=True)
    return novo, _desenhar_story(esp, novo, saida, post)


def refazer_item(item: dict, critica: dict, subir=None) -> dict:
    """The agent redoes a post of the agenda that the advance check reproved (conteudo.conferir_antes), from what the
    post carries: its proposal in the weekly routine (origem.semana) or its own ficha (24/10, conteudo.validar_ficha).
    A story from its fields, a carousel or photo from the Designer's molde ficha (or from the brief, drawn anew); the
    new files go to S3 and replace the old ones on the same post (conteudo.refeito). {"ok": False, "erro"} when it
    cannot: no ficha, a Reel (a new narration needs Matheus's ok first, decision #39), or the new version is still
    reproved."""
    origem, ficha = item.get("origem") or {}, item.get("ficha")
    if c().validar_ficha(ficha):
        ficha = None
    if not origem.get("semana") and not ficha:
        return {"ok": False, "erro": "não tem ficha (o que o post é e de onde vieram os arquivos), então não sei refazer"}
    if item["tipo"] == "REELS":
        return {"ok": False, "erro": "Reel já agendado não é refeito aqui (o vídeo sai do zero, cerca de 1 hora): o gestor "
                                     "cancela e cria outro" + (f"; a origem está em {_texto(ficha['fonte'], 120)}" if ficha else "")}
    if origem.get("semana"):
        sid, n = origem["semana"], origem.get("n")
        p = next((x for x in (carregar(sid) or {}).get("propostas", []) if x["n"] == n), None)
        if not p:
            return {"ok": False, "erro": f"a proposta {n} da semana {sid} não existe mais"}
        spec, k = p.get("spec") or {}, 1 + int(p.get("refeita") or 0)
        titulo, ideia, formato = p.get("titulo", ""), p.get("ideia", ""), p.get("formato_pedido") or item["tipo"]
        local, chave = _pasta() / sid, (lambda nome: _chave(sid, item["id"], nome))
    else:
        spec = {"story": ficha["story"]} if ficha.get("story") else dict(ficha.get("spec") or {})
        k = 1 + int(item.get("refeitas") or 0)
        titulo, ideia, formato = ficha.get("titulo", ""), ficha["brief"], item["tipo"]
        local = c().PASTA / "refeitos" / item["id"]
        chave = lambda nome: _chave("refeitos", item["id"], nome)  # noqa: E731  (the proxy uploads only under semanas/)
    esp = c().especialistas()
    if esp is None:
        return {"ok": False, "erro": "o plugin de especialistas não está instalado"}
    briefing = {"marca": "raiz", "rede": "instagram @raiz.connect", "formato": formato, "titulo": titulo, "ideia": ideia,
                "legenda": item.get("legenda", ""), "data": item["data"], "regras": REGRAS}
    if item["tipo"] == "STORY" and (spec.get("story") or ficha):
        # a story with only the brief: the Designer writes its fields from it (the kit draws them)
        atuais = spec.get("story") or {"sobre": ideia, "titulo": titulo}
        feito = _refazer_story(esp, atuais, critica, local / f"story-{item['id']}-a{k}.jpg")
        if not feito:
            return {"ok": False, "erro": "o Designer não devolveu campos válidos para o story"}
        campos, d = feito
        spec_novo, arquivos, nova = {"story": campos}, d["arquivos"], d["critica"]
    elif item["tipo"] in ("CARROSSEL", "IMAGE") and (spec.get("motor") == "molde" or (ficha and not spec)):
        if spec.get("motor") == "molde":
            vistas = [str(c().PASTA / "cache" / item["id"] / a.rsplit("/", 1)[-1]) for a in item["arquivos"]]
            d = esp.revisar(briefing, spec, critica, vistas)
        else:  # only the brief: the Designer draws it anew, told what the Crítico reproved
            d = esp.desenhar(dict(briefing, ideia=ideia + "\n\nA versão anterior foi reprovada pelo Crítico: "
                                  + "; ".join(str(m) for m in critica.get("motivos") or [])))
        tipo, arquivos, _ = tipo_dos_arquivos(d.get("arquivos"))
        if tipo != item["tipo"]:
            return {"ok": False, "erro": f"o Designer não entregou um {NOME_TIPO[item['tipo']].lower()} novo"
                                         + (f" ({_texto('; '.join(d.get('falta') or []), 160)})" if d.get("falta") else "")}
        spec_novo, nova = d.get("spec") or spec, _critica(d.get("critica"))
    else:
        return {"ok": False, "erro": "não há ficha do Designer para refazer este post"}
    if nova["veredito"] != "aprova":
        return {"ok": False, "erro": "a versão refeita também foi reprovada: " + c().uma_linha(nova["motivos"], 160)}
    cache = c().PASTA / "cache" / item["id"]
    cache.mkdir(parents=True, exist_ok=True)
    chaves = []
    try:
        for a in arquivos:
            arq_local = _jpg(Path(a))
            ch = chave(f"a{k}-{arq_local.name}")
            (subir or _subir_pelo_proxy)(str(arq_local), ch)
            shutil.copyfile(arq_local, cache / ch.rsplit("/", 1)[-1])
            chaves.append(ch)
    except Exception as exc:
        return {"ok": False, "erro": f"o arquivo refeito não subiu para o S3 ({str(exc)[:120]})"}
    motivo = "refeito pelo Designer: " + c().uma_linha(critica.get("motivos") or [], 200)
    if origem.get("semana"):
        r = c().refeito(item["id"], chaves, motivo)
        if not r["ok"]:
            return r
        with _exclusivo():
            s = carregar(sid)
            alvo = next(x for x in s["propostas"] if x["n"] == n)
            alvo.update(spec=spec_novo, refeita=k, arquivos=chaves, critica=nova)
            _gravar(s)
    else:
        nova_ficha = {key: v for key, v in ficha.items() if key not in ("story", "spec")}
        nova_ficha.update({"story": spec_novo["story"]} if spec_novo.get("story") else {"spec": spec_novo} if spec_novo else {})
        r = c().refeito(item["id"], chaves, motivo, ficha=nova_ficha)
        if not r["ok"]:
            return r
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


def _desenhar(esp, briefing: dict, p: dict, desenho=None) -> dict:
    """One proposal through the Designer (who always asks the Crítico); without especialistas, the review is missing.
    desenho() -> the Designer's raw answer, when the caller already knows which call (a revision, a new idea)."""
    if esp is None:
        return {"spec": {}, "arquivos": [str(a) for a in p.get("arquivos") or []], "falta": [],
                "critica": {"veredito": SEM_REVISAO, "motivos": ["o Crítico ainda não está instalado"], "sugestoes": []}}
    try:  # a ready ficha (spec) is rendered and judged as it is, without the Designer
        d = desenho() if desenho else (esp.julgar_ficha(briefing, p["spec"]) if isinstance(p.get("spec"), dict)
                                       and p["spec"] else esp.desenhar(briefing))
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


def _briefing(formato: str, dia: str, p: dict) -> dict:
    return {"marca": "raiz", "rede": "instagram @raiz.connect", "formato": formato,
            "titulo": _texto(p.get("titulo"), 120), "ideia": _texto(p.get("ideia"), 1200),
            "legenda": str(p.get("legenda") or "").strip(), "data": dia,
            "regras": REGRAS + (" " + HUMOR if _humor(p) else ""), **({"tom": "humor"} if _humor(p) else {})}


def _humor(p: dict) -> bool:
    return str(p.get("tom") or "").strip().lower() == "humor"


def _meme():
    if "meme" not in _C:
        spec = importlib.util.spec_from_file_location("conteudo_meme", Path(__file__).resolve().parent / "meme.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _C["meme"] = m
    return _C["meme"]


def _pov(esp, briefing: dict, pov: dict, saida: Path) -> dict:
    """The humor Reel made here (meme.py: the meme inside the video, with sound) and judged by the Crítico by its
    frames. A POV that cannot be made (no meme found, a rule broken) comes back reproved with the reason."""
    try:
        m = _meme().montar(pov, saida, chrome=story()._chrome())  # the same Chrome that draws the stories
    except Exception as exc:
        motivo = str(exc) if isinstance(exc, ValueError) else f"o vídeo de meme não saiu ({type(exc).__name__}: {str(exc)[:120]})"
        return {"spec": {"pov": pov}, "arquivos": [], "falta": [motivo],
                "critica": {"veredito": "reprova", "motivos": [motivo], "sugestoes": []}}
    critica = esp.criticar("post", {"briefing": dict(briefing, meme=m["meme"]), "imagens": m["quadros"],
                                    "quadros": ["2 s: o caderno no chute com o meme", "5 s: a virada para a Raiz",
                                                "10 s: a tela da Raiz (a capa)"]})
    return {"spec": {"pov": pov, "meme": m["meme"]}, "arquivos": [m["video"], m["capa"]], "critica": critica}


def _item_feed(esp, nota: str, sid: str, n: int, formato: str, dia: str, p: dict, desenho=None) -> dict:
    """One feed proposal of the week, drawn by the Designer and judged by the Crítico (the humor Reel: made here)."""
    briefing = _briefing(formato, dia, p)
    if desenho is None and esp is not None and _humor(p) and isinstance(p.get("pov"), dict):
        desenho = lambda: _pov(esp, briefing, p["pov"], _pasta() / sid / f"pov-{n}")  # noqa: E731
    d = _desenhar(esp, briefing, p, desenho)
    if nota:
        d["critica"]["motivos"] = [nota] + d["critica"]["motivos"]
    if not briefing["titulo"]:  # a new idea from the Designer: its own title
        briefing["titulo"] = _texto(d["spec"].get("titulo") or (d["spec"].get("ficha") or {}).get("titulo")
                                    or "ideia nova do Designer", 120)
    legenda = briefing["legenda"] or str(d["spec"].get("legenda") or "").strip()
    pendente = formato == "REELS" and d.get("video_pendente")
    tipo, arquivos, capa = ("REELS", [], "") if pendente else tipo_dos_arquivos(d["arquivos"])
    problema = ""
    if not tipo:
        problema = "o Designer não entregou arquivo publicável (.mp4, ou de 1 a 10 imagens)" + (
            f": {_texto('; '.join(d['falta']), 160)}" if d["falta"] else "")
    else:
        problema = c().validar_legenda(legenda)
    return {"n": n, "id": f"{sid}-{n}", "data": dia, "hora": str(p.get("hora") or HORA), "titulo": briefing["titulo"],
          "ideia": briefing["ideia"], "formato_pedido": formato, "tipo": tipo, "arquivos": arquivos,
          **({"tom": "humor"} if _humor(p) else {}), **({"pov": p["pov"]} if isinstance(p.get("pov"), dict) else {}),
          "capa": capa, "legenda": legenda, "spec": d["spec"], "critica": d["critica"],
          "problema": problema, "estado": "proposta",
          **({"video": {"estado": "aguardando_aprovacao", "molde": d["spec"].get("molde"),
                        "formato": str(d["spec"].get("formato") or "reel"), "ficha": d["spec"].get("ficha")},
              "previa": d.get("previa", []), "folha": d.get("folha", ""), "narracao": d.get("narracao", "")}
             if pendente else {})}


def _item_story(esp, sid: str, n: int, campos: dict, dia: str, itens: list, sufixo: str = "") -> dict:
    """One story of the week, drawn from the kit, judged (with the day's post it calls) and redone when reproved."""
    post, sem_post = _post_do_dia(campos, dia, itens)
    if post and post.get("imagem") and not campos.get("imagem"):  # the post's own picture, not a text-only card
        campos = dict(campos, imagem=post["imagem"])
    d = _desenhar_story(esp, campos, _pasta() / sid / f"story-{n}{sufixo}.jpg", post)
    for k in range(REFAZER_STORY if esp is not None and not sem_post else 0):  # reproved: redone before he sees it
        if d["critica"]["veredito"] != "reprova":
            break
        feito = _refazer_story(esp, campos, d["critica"], _pasta() / sid / f"story-{n}{sufixo}-r{k + 1}.jpg", post)
        if not feito:
            break
        campos, d = feito
    if sem_post and d["arquivos"]:  # rewriting the story cannot make the post exist: reproved, says why
        d["critica"] = {"veredito": "reprova", "motivos": [sem_post] + [m for m in d["critica"]["motivos"]][:4],
                        "sugestoes": d["critica"].get("sugestoes") or []}
    return _proposta_story(sid, n, campos, dia, d)


def _proposta_story(sid: str, n: int, campos: dict, dia: str, d: dict) -> dict:
    titulo = f"{campos.get('layout', '?')}: {_texto(campos.get('manchete') or 'oferta Lucro na Mão', 100)}"
    return {"n": n, "id": f"{sid}-{n}", "data": dia, "hora": HORA_STORY, "titulo": titulo, "ideia": "",
          "formato_pedido": "STORY", "tipo": "STORY" if d["arquivos"] else "", "arquivos": d["arquivos"],
          "capa": "", "legenda": _texto(campos.get("manchete"), 200), "spec": {"story": campos},
          "critica": d["critica"], "problema": d["problema"], "estado": "proposta"}


def propor(propostas: list, agora: float | None = None, enviar=None, login: str = "matheus", stories=None,
           subir=None) -> dict:
    """The week: 4 feed ideas from the routine [{"titulo", "formato" (2 CARROSSEL and 2 REELS), "ideia", "legenda"}]
    and 7 stories [{"layout", "manchete", ...: helpers/story.py}] → each drawn and judged, saved as a new version;
    what the Crítico approved goes into the agenda now, the rest is redone by passo_autonomo, and Matheus gets one
    notice of what happened (no buttons: 04/11, he does not want to be waited on)."""
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
    for p in propostas:
        if _humor(p):
            erro = ("o post de humor é um Reel (formato REELS)" if str(p.get("formato") or "").upper() != "REELS"
                    else _meme().validar(p.get("pov")))
            if erro:
                return {"ok": False, "erro": f"post de humor \"{_texto(p.get('titulo'), 60)}\": {erro}"}
    if len(vagas) >= SEMANAS_COM_HUMOR and not any(_humor(p) for p in propostas):
        return {"ok": False, "erro": "a semana precisa de pelo menos 1 post de humor (Matheus, 05/11): marque uma das "
                                     "propostas com \"tom\": \"humor\" (POV com meme da cultura pop, ex.: Nazaré "
                                     "fazendo conta do custo da pizza; o meme ele põe no CapCut)"}
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
        itens.append(_item_feed(esp, nota, sid, n, formato, dia, fila[formato].pop(0)))
    for n, (campos, dia) in enumerate(zip(stories, dias_story), start=len(vagas) + 1):
        itens.append(_item_story(esp, sid, n, campos, dia, itens))
    semana = {"id": sid, "criada_em": agora, "estado": "proposta", "login": login, "propostas": itens, "autonomo": True}
    with _exclusivo():
        for antiga in _pasta().glob("s*.json"):  # an older week still open is replaced: its buttons stop working
            s = json.loads(antiga.read_text(encoding="utf-8"))
            if s["estado"] in ("proposta", "refazer"):
                s["estado"] = "substituida"
                _gravar(s)
        _gravar(semana)
    c()._diario({"semana": sid, "proposta": True, "dias": [i["data"] for i in itens],
                 "vereditos": [i["critica"]["veredito"] for i in itens]})
    decidido = _decidir(sid, agora, subir)
    semana = carregar(sid)
    texto, botoes = mensagem(semana)
    erro = (enviar or _enviar_ponte)(login, texto, botoes)
    with _exclusivo():
        s = carregar(sid)
        s["enviada"] = not erro
        if erro:
            s["erro_envio"] = str(erro)[:200]
        _gravar(s)
    por_n = {p["n"]: p for p in semana["propostas"]}
    return {"ok": True, "semana": sid, "enviada": not erro, **({"erro_envio": str(erro)[:200]} if erro else {}),
            **decidido,
            "propostas": [{"n": i["n"], "data": i["data"], "tipo": i["tipo"] or "?", "titulo": i["titulo"],
                           "critico": i["critica"]["veredito"], "problema": i["problema"],
                           "estado": por_n[i["n"]]["estado"]} for i in itens]}


# ------------------------------------------------------------------ autonomy (04/11): the Crítico decides, not Matheus

def assumir(sid: str, agora: float | None = None, subir=None) -> dict:
    """A week created before 04/11 (it waited for Matheus's buttons) handed to the autonomous flow, by the operator:
    what the Crítico approved goes into the agenda, what is already past or too close is dropped silently (its day is
    gone), and the reproved rest is redone by passo_autonomo from the next pass on."""
    if not str(c().AUTOR["quem"]).startswith("operador:"):
        return {"ok": False, "erro": "só o operador entrega uma semana antiga ao fluxo autônomo (AUTOR['quem'] = 'operador: ...')"}
    agora = time.time() if agora is None else agora
    with _exclusivo():
        s = carregar(sid)
        if not s or s["estado"] not in ("proposta", "parcial"):
            return {"ok": False, "erro": f"a semana {sid} não está aberta"}
        s["autonomo"] = True
        s["criada_em"] = max(float(s.get("criada_em") or 0), agora - 86400)  # inside passo_autonomo's window
        _gravar(s)
    c()._diario({"semana": sid, "autonoma": True, "motivo": "decisão do Matheus de 04/11: o Crítico decide"})
    r = _decidir(sid, agora, subir)
    return {"ok": True, "semana": sid, **r,
            "abertas": [p["n"] for p in carregar(sid)["propostas"] if p["estado"] == "proposta"]}


def _aprovada(p: dict) -> bool:
    """Only a clean "aprova" with a publishable file goes by itself ("sem revisão" never does: fail closed)."""
    return p["estado"] == "proposta" and not p["problema"] and p["critica"]["veredito"] == "aprova"


def _sai_em(p: dict) -> float:
    return c()._quando({"data": p["data"], "hora": p["hora"]})


def _decidir(sid: str, agora: float, subir=None) -> dict:
    """What the Crítico approved goes into the agenda now (aprovar, as the Gestor); an open proposal that goes out
    too soon to be redone is dropped (its day stays free for the Gestor). The rest waits for passo_autonomo."""
    semana = carregar(sid)
    if not semana or semana["estado"] not in ("proposta", "parcial"):
        return {"agendados": [], "gerando_video": [], "descartados": [], "passados": []}
    passados = [p["n"] for p in semana["propostas"] if p["estado"] == "proposta" and _sai_em(p) < agora]
    for n in passados:  # its hour is gone: nothing to decide, nothing to tell
        _descartar(sid, n, "o horário dele passou antes da decisão")
    semana = carregar(sid)
    sim = [p["n"] for p in semana["propostas"] if _aprovada(p)]
    r = aprovar(sid, sim, quem=QUEM_AUTO, agora=agora, subir=subir) if sim else {"agendados": [], "gerando_video": []}
    sem_tempo = [p["n"] for p in carregar(sid)["propostas"]
                 if p["estado"] == "proposta" and _sai_em(p) < agora + FOLGA_AUTO_MIN * 60]
    for n in sem_tempo:
        _descartar(sid, n, "não dá tempo de refazer antes da hora dele")
    return {"agendados": r.get("agendados", []), "gerando_video": r.get("gerando_video", []), "descartados": sem_tempo,
            "passados": passados}


def _descartar(sid: str, n: int, motivo: str) -> None:
    with _exclusivo():
        s = carregar(sid)
        p = next(x for x in s["propostas"] if x["n"] == n)
        if p["estado"] != "proposta":
            return
        p.update(estado="descartada", decisao=motivo)
        s["estado"] = "parcial" if any(x["estado"] == "proposta" for x in s["propostas"]) else "decidida"
        _gravar(s)
    c()._diario({"semana": sid, "descartada": n, "data": p["data"], "motivo": motivo[:200], "quem": QUEM_AUTO})


def _salvar_proposta(sid: str, nova: dict) -> bool:
    """A redone proposal replaces the open one with the same n; False when it was decided meanwhile."""
    with _exclusivo():
        s = carregar(sid)
        velha = next((x for x in s["propostas"] if x["n"] == nova["n"]), None)
        if not velha or velha["estado"] != "proposta":
            return False
        s["propostas"][s["propostas"].index(velha)] = nova
        _gravar(s)
    return True


def _motivos(p: dict) -> list:
    return ([p["problema"]] if p.get("problema") else []) + list(p["critica"].get("motivos") or [])


def _vistas(p: dict) -> list:
    """The local pictures of a proposal (its slides, or a Reel's preview), for the Designer's revision."""
    return [str(a) for a in list(p.get("arquivos") or []) + list(p.get("previa") or [])
            if str(a).lower().endswith(IMAGEM) and Path(str(a)).is_file()][:8]


def _refazer_feed(esp, sid: str, p: dict, nova: bool) -> dict:
    """One more version of a reproved feed proposal: the Designer revises it with the Crítico's reasons (a molde ficha),
    or draws it again told what was wrong; nova=True asks for a different idea for the same slot."""
    briefing = _briefing(p["formato_pedido"], p["data"], p)
    motivos = "; ".join(_motivos(p))[:900]
    spec = p.get("spec") or {}
    if isinstance(p.get("pov"), dict) and not nova:  # the humor Reel again, with the next meme of the same search
        pov = dict(p["pov"], meme=dict(p["pov"]["meme"], indice=int(p["pov"]["meme"].get("indice") or 0) + 1))
        return _item_feed(esp, "", sid, p["n"], p["formato_pedido"], p["data"], dict(p, pov=pov, hora=p["hora"]))
    if nova:
        ideia = (f"Ideia NOVA para a vaga de {NOME_TIPO[p['formato_pedido']]} de {_rotulo_dia(p['data'])}: um assunto "
                 f"diferente de \"{p['titulo']}\", que o Crítico reprovou ({motivos}). Plano: gestão (pedido do iFood e da "
                 "99 entrando sozinho, estoque, comanda, financeiro) ou custo e preço, para o dono do negócio de comida. "
                 "Ponha na ficha \"titulo\" e \"legenda\" (sem emoji nem travessão).")
        base = dict(p, titulo="", ideia=ideia, legenda="", spec={})
        return _item_feed(esp, "", sid, p["n"], p["formato_pedido"], p["data"], dict(base, hora=p["hora"]),
                          desenho=lambda: esp.desenhar(dict(_briefing(p["formato_pedido"], p["data"], base))))
    if spec.get("motor") == "molde":
        critica = {"veredito": "reprova", "motivos": _motivos(p), "sugestoes": p["critica"].get("sugestoes") or []}
        desenho = lambda: esp.revisar(briefing, spec, critica, _vistas(p))  # noqa: E731
    else:
        desenho = lambda: esp.desenhar(dict(briefing, ideia=briefing["ideia"]  # noqa: E731
                                            + "\n\nA versão anterior foi reprovada pelo Crítico: " + motivos))
    return _item_feed(esp, "", sid, p["n"], p["formato_pedido"], p["data"], dict(p, hora=p["hora"]), desenho=desenho)


DICA = ("O post do dia não vai sair: troque o layout para \"dica\" (uma dica curta e útil para o dono do negócio de "
        "comida, com manchete, destaque, texto e chamada) e não chame post nenhum.")


def _refazer_story_semana(esp, sid: str, p: dict, itens: list, nova: bool) -> dict | None:
    """One more version of a reproved story. A story that calls a post that will not go out (or nova=True for one
    that calls a post) becomes a "dica"; nova=True otherwise asks for a different story with the same layout.
    None when the Designer gave nothing usable."""
    campos = dict(p["spec"].get("story") or {})
    k = 1 + int((p.get("auto") or {}).get("tentativas") or 0)
    saida = _pasta() / sid / f"story-{p['n']}-auto{k}{'-nova' if nova else ''}.jpg"
    post, sem_post = _post_do_dia(campos, p["data"], itens)
    chama = campos.get("layout") in CHAMA
    if chama and (sem_post or nova):
        motivos = [DICA] + ([sem_post] if sem_post else _motivos(p))
        post = None
    elif nova:
        motivos = [f"Escreva um story NOVO para {_rotulo_dia(p['data'])}, com outro assunto: o anterior foi reprovado "
                   f"várias vezes ({'; '.join(_motivos(p))[:400]})."]
    else:
        motivos = _motivos(p)
    feito = _refazer_story(esp, campos, {"motivos": motivos}, saida, post)
    if not feito:
        return None
    novo, d = feito
    if chama and post is None and novo.get("layout") in CHAMA:  # still calls a post that will not go out
        d["critica"] = {"veredito": "reprova", "motivos": ["continua chamando um post que não vai sair"], "sugestoes": []}
    return _proposta_story(sid, p["n"], novo, p["data"], d)


def _feed_aberto(semana: dict, dia: str) -> bool:
    return any(x["estado"] == "proposta" and x["formato_pedido"] != "STORY" and x["data"] == dia for x in semana["propostas"])


def _rotulo(p: dict) -> str:
    nome = NOME_TIPO.get(p["formato_pedido"], p["formato_pedido"]).lower()
    return f"o {nome} de {_rotulo_dia(p['data'])} ({_texto(p['titulo'], 70)})"


def passo_autonomo(agora: float | None = None, avisar=None, subir=None) -> dict | None:
    """One step of the autonomous week (the job loop calls it every pass, one Designer round at most): the first open
    proposal of the recent weeks (feed before stories: a story that calls a post waits for its post) is redone; if the
    new version is approved it goes into the agenda; after REFAZER_AUTO failed redos one new idea is tried; after that the
    day stays without it. Each decision is told to Matheus in one line, without buttons. None when there is nothing
    to do. avisar(texto) sends the notice."""
    agora = time.time() if agora is None else agora
    if not _pasta().exists():
        return None
    try:
        esp = c().especialistas()
    except Exception:
        return None
    if esp is None:  # without the Crítico nothing is ever decided by itself
        return None
    with open(_pasta() / "autonomo.lock", "a") as trava:  # never two steps at once (the job loop, an operator run)
        try:
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return None
        try:
            return _passo_autonomo(esp, agora, avisar, subir)
        finally:
            fcntl.flock(trava, fcntl.LOCK_UN)


def _passo_autonomo(esp, agora: float, avisar, subir) -> dict | None:
    nomes = sorted((x.stem for x in _pasta().glob("s*.json")), key=lambda n: (n.split("-")[0], int(n.split("-")[1])))
    for sid in nomes:
        semana = carregar(sid)
        if (not semana.get("autonomo") or semana["estado"] not in ("proposta", "parcial")
                or float(semana.get("criada_em") or 0) < agora - 14 * 86400):
            continue  # weeks from before 04/11 waited for Matheus: only assumir() hands one over
        r = _decidir(sid, agora, subir)  # approved ones (e.g. created by the Gestor) and the ones out of time
        semana = carregar(sid)
        fora = [next(x for x in semana["propostas"] if x["n"] == n) for n in r["descartados"]]
        if fora:
            _avisar(avisar, "🧭 Conteúdo: ficou de fora, porque o Crítico não aprovou e não dava mais tempo de refazer: "
                            + "; ".join(_rotulo(p) for p in fora) + ".")
        abertas = sorted((x for x in semana["propostas"] if x["estado"] == "proposta"),
                         key=lambda x: (x["formato_pedido"] == "STORY", _sai_em(x)))
        for p in abertas:
            if p["formato_pedido"] == "STORY" and (p["spec"].get("story") or {}).get("layout") in CHAMA \
                    and _feed_aberto(semana, p["data"]):
                continue  # its post is still being decided
            return _um_passo(esp, sid, semana, p, agora, avisar, subir)
    return None


def _um_passo(esp, sid: str, semana: dict, p: dict, agora: float, avisar, subir) -> dict:
    auto = dict(p.get("auto") or {})
    tentativas, nova = int(auto.get("tentativas") or 0), False
    if tentativas >= REFAZER_AUTO:
        if auto.get("nova_ideia"):
            _descartar(sid, p["n"], f"o Crítico reprovou {tentativas + 2} versões")
            _avisar(avisar, f"🧭 Conteúdo: o Crítico reprovou todas as versões de {_rotulo(p)} "
                            f"({c().uma_linha(_motivos(p), 140)}). Decidi deixar o dia sem ele; o gestor pode cobrir.")
            return {"semana": sid, "n": p["n"], "decisao": "sem post"}
        nova = True
    try:
        if p["formato_pedido"] == "STORY":
            novo = _refazer_story_semana(esp, sid, p, semana["propostas"], nova)
        else:
            novo = _refazer_feed(esp, sid, p, nova)
    except Exception as exc:
        novo, erro = None, f"{type(exc).__name__}: {str(exc)[:160]}"
    else:
        erro = "" if novo else "o Designer não devolveu nada utilizável"
    if novo is None:
        novo = dict(p, problema=erro or p.get("problema") or "sem versão nova")
    auto = {"tentativas": tentativas + (0 if nova else 1), "nova_ideia": bool(auto.get("nova_ideia") or nova),
            "ultima": agora}
    novo = dict(novo, auto=auto, estado="proposta", refeita=int(p.get("refeita") or 0) + 1)
    if not _salvar_proposta(sid, novo):
        return {"semana": sid, "n": p["n"], "decisao": "decidida enquanto refazia"}
    c()._diario({"semana": sid, "refeita_auto": p["n"], "nova_ideia": nova, "tentativa": auto["tentativas"],
                 "veredito": novo["critica"]["veredito"], "quem": QUEM_AUTO,
                 **({"problema": _texto(novo["problema"], 160)} if novo.get("problema") else {})})
    if not _aprovada(novo):
        return {"semana": sid, "n": p["n"], "decisao": "nova ideia reprovada" if nova else "refeita, ainda reprovada"}
    r = aprovar(sid, [p["n"]], quem=QUEM_AUTO, agora=agora, subir=subir)
    final = next(x for x in carregar(sid)["propostas"] if x["n"] == p["n"])
    if final["estado"] in ("agendada", "gerando_video"):
        como = "troquei por uma ideia nova" if nova else "refiz"
        quando = ("o vídeo está sendo feito e entra na agenda sozinho" if final["estado"] == "gerando_video"
                  else f"agendado para {_rotulo_dia(final['data'])} às {final['hora']}")
        _avisar(avisar, f"🧭 Conteúdo: {como} {_rotulo(final if nova else p)} e o Crítico aprovou: {quando}.")
        return {"semana": sid, "n": p["n"], "decisao": "ideia nova agendada" if nova else "refeita e agendada"}
    return {"semana": sid, "n": p["n"], "decisao": "aprovada, não agendou", "erro": (r.get("recusados") or [{}])[0].get("motivo")}


def _avisar(avisar, texto: str) -> None:
    if avisar is None:
        _enviar_ponte("matheus", texto, [])
        return
    try:
        avisar(texto)
    except Exception as exc:
        print(f"conteudo: aviso não saiu: {exc}", flush=True)


def em_refacao(data: str, canal_: str, agora: float | None = None) -> str:
    """The open proposal of an autonomous week the agent is still redoing for that day and slot ("" when none): the
    Gestor does not create another one on top of it."""
    agora = time.time() if agora is None else agora
    if not _pasta().exists():
        return ""
    for arq in sorted(_pasta().glob("s*.json")):
        try:
            s = json.loads(arq.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not s.get("autonomo") or s.get("estado") not in ("proposta", "parcial"):
            continue
        for p in s.get("propostas") or []:
            if (p.get("estado") == "proposta" and p.get("data") == data
                    and ("story" if p.get("formato_pedido") == "STORY" else "feed") == canal_):
                return f"{s['id']}-{p['n']}"
    return ""


def criar(data: str, formato: str, dados: dict, agora: float | None = None, subir=None, quem: str = "gestor") -> dict:
    """The Gestor fills a hole (04/11): one new feed post {"titulo", "ideia", "legenda"} or story {"story": fields} for
    `data`, appended to the newest week, drawn and judged like the week's; approved goes into the agenda now, reproved
    is redone by passo_autonomo like any other. Refused when the slot is taken or too close."""
    agora = time.time() if agora is None else agora
    formato = str(formato or "").upper()
    if formato not in ("CARROSSEL", "REELS", "IMAGE", "STORY"):
        return {"ok": False, "erro": "formato: CARROSSEL, REELS, IMAGE ou STORY"}
    try:
        dt.date.fromisoformat(str(data))
    except ValueError:
        return {"ok": False, "erro": "data (AAAA-MM-DD) inválida"}
    canal_ = "story" if formato == "STORY" else "feed"
    hora = HORA_STORY if formato == "STORY" else HORA
    if c()._quando({"data": data, "hora": hora}) < agora + FOLGA_AUTO_MIN * 60:
        return {"ok": False, "erro": f"{data} {hora} já passou ou está perto demais para criar"}
    if data in _ocupados(canal_):
        return {"ok": False, "erro": f"{data} já tem {canal_}"}
    if em_refacao(data, canal_, agora):
        return {"ok": False, "erro": f"{data}: o agente ainda está refazendo {em_refacao(data, canal_, agora)} para esse dia"}
    if formato == "STORY" and (not isinstance(dados.get("story"), dict) or story().validar(dados["story"])):
        return {"ok": False, "erro": "story: campos do kit (" + (story().validar(dados.get("story"))
                                                                 if isinstance(dados.get("story"), dict) else "objeto") + ")"}
    if formato != "STORY" and not (str(dados.get("titulo") or "").strip() and str(dados.get("ideia") or "").strip()):
        return {"ok": False, "erro": "post: titulo e ideia"}
    esp = c().especialistas()
    if esp is None:
        return {"ok": False, "erro": "sem o Crítico (plugin especialistas) nada é criado"}
    with _exclusivo():
        semana = ultima()
        if not semana:
            base = "s" + _hoje(agora).strftime("%Y%m%d")
            semana = {"id": f"{base}-1", "criada_em": agora, "estado": "parcial", "login": "matheus", "propostas": []}
            _gravar(semana)
        sid, n = semana["id"], 1 + max([p["n"] for p in semana["propostas"]] or [0])
    if formato == "STORY":
        p = _item_story(esp, sid, n, dados["story"], data, carregar(sid)["propostas"], sufixo="-gestor")
    else:
        p = _item_feed(esp, "", sid, n, formato, data, {k: dados.get(k) for k in ("titulo", "ideia", "legenda")})
    p["criada_por"] = quem
    with _exclusivo():
        s = carregar(sid)
        if any(x["n"] == n for x in s["propostas"]):
            return {"ok": False, "erro": "outra criação usou o mesmo número; tente de novo"}
        s["propostas"].append(p)
        s["estado"], s["autonomo"] = "parcial", True
        s["criada_em"] = max(float(s.get("criada_em") or 0), agora)  # passo_autonomo looks at recent weeks
        _gravar(s)
    c()._diario({"semana": sid, "criada": n, "data": data, "formato": formato, "veredito": p["critica"]["veredito"],
                 "quem": quem})
    agendado = False
    if _aprovada(p):
        r = aprovar(sid, [n], quem=QUEM_AUTO, agora=agora, subir=subir)
        agendado = bool(r.get("agendados") or r.get("gerando_video"))
    return {"ok": True, "semana": sid, "n": n, "veredito": p["critica"]["veredito"], "agendado": agendado,
            "problema": p["problema"]}


def refazer_propostas(sid: str, feed=None, stories=None, enviar=None, agora: float | None = None, subir=None) -> dict:
    """Redoes only some proposals of a week still open (27/10, Matheus: "Pode fazer" for the reproved Reel and carousel),
    in the same days and slots, keeping the others as he saw them. `feed` = {n: {"titulo", "ideia", "legenda"}},
    `stories` = {n: story fields}. A story that calls a redone feed post is judged again with the new post (its fields
    unchanged when not given). Then the same week's message goes again, with its buttons."""
    try:
        feed = json.loads(feed) if isinstance(feed, str) else (feed or {})
        stories = json.loads(stories) if isinstance(stories, str) else (stories or {})
        feed = {int(k): v for k, v in feed.items() if isinstance(v, dict)}
        stories = {int(k): v for k, v in stories.items() if isinstance(v, dict)}
    except (ValueError, TypeError, AttributeError):
        return {"ok": False, "erro": "feed e stories: objetos {número: campos}"}
    semana = carregar(sid) if re.fullmatch(r"s\d{8}-\d{1,3}", str(sid or "")) else None
    if not semana or semana["estado"] not in ("proposta", "parcial"):
        return {"ok": False, "erro": f"a semana {sid} não está aberta"}
    itens = semana["propostas"]
    por_n = {p["n"]: p for p in itens}
    for n, novo in [*feed.items(), *stories.items()]:
        p = por_n.get(n)
        if not p or p["estado"] != "proposta":
            return {"ok": False, "erro": f"a {n} não é uma proposta aberta desta semana"}
        if (n in feed) == (p["formato_pedido"] == "STORY"):
            return {"ok": False, "erro": f"a {n} é {NOME_TIPO[p['formato_pedido']]}: mande-a em {'stories' if n in feed else 'feed'}"}
    if not feed and not stories:
        return {"ok": False, "erro": "diga quais refazer"}
    esp = c().especialistas()
    rodada = 1 + max([int(p.get("refeita") or 0) for p in itens] or [0])
    capas_velhas = {_imagem_do_post(por_n[n]) for n in feed} - {""}
    for n, novo in feed.items():
        velho = por_n[n]
        item = _item_feed(esp, "", sid, n, velho["formato_pedido"], velho["data"], dict(novo, hora=velho["hora"]))
        itens[itens.index(velho)] = por_n[n] = dict(item, refeita=rodada)
    dias = {por_n[n]["data"] for n in feed}
    for p in list(itens):
        if p["formato_pedido"] == "STORY" and p["estado"] == "proposta" and (
                p["n"] in stories or (p["data"] in dias and p["spec"]["story"].get("layout") in CHAMA)):
            campos = stories.get(p["n"]) or {k: v for k, v in p["spec"]["story"].items()  # the old post's cover goes
                                             if not (k == "imagem" and v in capas_velhas)}
            item = _item_story(esp, sid, p["n"], campos, p["data"], itens, sufixo=f"-v{rodada}")
            itens[itens.index(p)] = por_n[p["n"]] = dict(item, refeita=rodada)
    with _exclusivo():
        atual = carregar(sid)
        if atual["estado"] not in ("proposta", "parcial"):
            return {"ok": False, "erro": f"a semana {sid} foi decidida enquanto eu refazia"}
        abertas = {p["n"] for p in atual["propostas"] if p["estado"] == "proposta"}  # one he decided meanwhile stays
        mudou = {p["n"]: p for p in itens if p.get("refeita") == rodada and p["n"] in abertas}
        perdidos = {por_n[n]["data"] for n in feed if n not in mudou}  # its story was judged with a post that lost
        mudou = {n: p for n, p in mudou.items() if n in feed or n in stories or p["data"] not in perdidos}
        atual["propostas"] = [mudou.get(p["n"], p) for p in atual["propostas"]]
        _gravar(atual)
    c()._diario({"semana": sid, "refeitas": sorted(mudou), "vereditos": [mudou[n]["critica"]["veredito"] for n in sorted(mudou)]})
    if not mudou:
        return {"ok": False, "erro": "você decidiu essas propostas enquanto eu refazia; nada mudou"}
    _decidir(sid, time.time() if agora is None else agora, subir)  # 04/11: what the Crítico approves now goes in
    atual = carregar(sid)
    texto, botoes = mensagem(atual)
    erro = (enviar or _enviar_ponte)(atual.get("login", "matheus"), "Refiz " + ", ".join(map(str, sorted(mudou)))
                                     + ".\n\n" + texto, botoes)
    return {"ok": True, "semana": sid, "enviada": not erro, **({"erro_envio": str(erro)[:200]} if erro else {}),
            "refeitas": [{"n": p["n"], "data": p["data"], "titulo": p["titulo"], "critico": p["critica"]["veredito"],
                          "problema": p["problema"]} for p in mudou.values()]}


def _rotulo_dia(data: str) -> str:
    d = dt.date.fromisoformat(data)
    return f"{DIAS_SEMANA[d.weekday()]} {d.strftime('%d/%m')}"


def _aprovaveis(semana: dict) -> list[dict]:
    """What "Aprovar todas" takes: still proposed, publishable and not reproved by the Crítico."""
    return [p for p in semana["propostas"] if p["estado"] == "proposta" and not p["problema"]
            and p["critica"]["veredito"] != "reprova"]


ESTADO_AVISO = {"agendada": "agendado", "gerando_video": "aprovado, o vídeo está sendo feito e entra na agenda sozinho",
                "descartada": "fora", "erro": "não entrou"}


def mensagem(semana: dict) -> tuple[str, list]:
    """The notice of the week (04/11: a result, never a question): what went into the agenda, what the agent is
    redoing by itself and what was left out. No buttons."""
    ps = semana["propostas"]
    datas = sorted(p["data"] for p in ps)
    linhas = [f"*Semana de posts da @raiz.connect* ({_rotulo_dia(datas[0])} a {_rotulo_dia(datas[-1])}): "
              f"{sum(p['formato_pedido'] != 'STORY' for p in ps)} no feed e {sum(p['formato_pedido'] == 'STORY' for p in ps)} "
              "stories. O Crítico decide; o que ele reprovou eu refaço sozinho."]
    for p in ps:
        v = p["critica"]["veredito"]
        if p["estado"] in ESTADO_AVISO:
            situacao = ESTADO_AVISO[p["estado"]] + (f" ({_texto(p.get('decisao') or p.get('erro'), 120)})"
                                                    if p.get("decisao") or p.get("erro") else "")
        elif v == "reprova" or p["problema"]:
            situacao = "refazendo (Crítico: " + c().uma_linha(_motivos(p), 120) + ")"
        else:
            situacao = "sem revisão do Crítico, não sai (" + c().uma_linha(p["critica"]["motivos"], 100) + ")"
        tipo = "Story " + p["hora"] if p["formato_pedido"] == "STORY" else NOME_TIPO.get(p["tipo"] or p["formato_pedido"], "?")
        linhas.append(f"{p['n']}. *{_rotulo_dia(p['data'])}* · {tipo} · {p['titulo']}: {situacao}")
    return "\n".join(linhas), []


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
        linhas.append("Ainda abertas (o agente refaz sozinho as reprovadas): " + ", ".join(abertas) + ".")
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
    if re.fullmatch(r"g[0-9a-f]{8}", alvo) and re.fullmatch(r"o\d", acao):  # an option of a Gestor question (gestor.py)
        return gestor().resposta(alvo, int(acao[1:]))
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

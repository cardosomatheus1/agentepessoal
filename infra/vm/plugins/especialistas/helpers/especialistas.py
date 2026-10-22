"""Especialistas (20/10): roles with their own personality and rules (Crítico, Designer) that the main agent calls for
one task, sharing the same Segundo Cérebro; Matheus never talks to them directly (GLOSSARY.md).

- `criticar(tipo, material)`: the Crítico judges a post, carrossel, oferta, landing or mensagem against the Cérebro da
  Raiz (plugins/cerebro/helpers/raiz.py) and Matheus's AR Board criteria (calibracao/<agente>/criterios.md). Fixed
  rules (emoji, dash characters, R$ without "valores de exemplo") are checked here, not by the model. Anything that
  is not a clean verdict is "reprova" (fail closed).
- `desenhar(briefing)`: the Designer turns a briefing into a render spec for the existing engine (infra/reels: the
  Raiz carrossel base and the moldes motor) and renders it when that engine is reachable; every output goes through
  `criticar` before it is returned.

One model call per role call, same endpoint as cerebro/helpers/captura.py."""

import base64
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

URL = "http://host.docker.internal:8787/openai/v1/responses"
MODELO = "openai.gpt-6-luna"
TEMPO = 120
# 22/10: on "low" the Designer miscounted lines and promised in the title what the text did not deliver (4 real runs,
# all reproved); it thinks harder and waits longer. The Crítico keeps its setting.
# "high" went past the host proxy's 240 s on the big correction prompts and the calls died silently: "medium".
ESFORCO = {"designer": "medium"}
TEMPO_PAPEL = {"designer": 230}
RAIZ = Path(__file__).resolve().parents[1]
# next to this plugin (repository, live install); a staging copy alone in /tmp uses the installed ones
PLUGINS = RAIZ.parent if (RAIZ.parent / "cerebro").exists() else Path("/a0/usr/plugins")
TIPOS = ("post", "carrossel", "story", "reel", "oferta", "landing", "mensagem")  # story e reel: 22/10
MAX_IMAGENS = 8
LADO_MAX = 1600
MAX_MATERIAL = 12_000
MAX_CRITERIOS = 3_000
EXT_IMAGEM = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
# which AR Board agent's criteria judge each kind of piece
CRITERIOS_POR_TIPO = {"post": ("conteudo", "moldes"), "carrossel": ("conteudo", "moldes"), "story": ("conteudo", "moldes"),
                      "reel": ("conteudo", "moldes"),
                      "oferta": ("conteudo",),
                      "landing": ("conteudo",), "mensagem": ("prospeccao",)}
MOTORES = ("carrossel_raiz", "video_kit_raiz", "molde")

EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")
TRACO = re.compile("[—–]")
REAIS = re.compile(r"R\$\s?\d")
EXEMPLO = re.compile(r"exemplo|valores ilustrativos|R\$ ?197\b|R\$ ?1\.697\b", re.I)


def _primeiro(*caminhos) -> Path | None:
    for c in caminhos:
        if c and Path(c).exists():
            return Path(c)
    return None


def _acima(n: int) -> Path | None:
    try:
        return RAIZ.parents[n]
    except IndexError:
        return None


def pasta_reels() -> Path | None:
    """The render engine: infra/reels in the repository (base/ for the Raiz carrossel, moldes/motor/ for moldes)."""
    acima = _acima(2)
    return _primeiro(os.environ.get("ESPECIALISTAS_REELS"), acima / "reels" if acima else None, "/a0/usr/reels")


def pasta_moldes() -> Path | None:
    """The moldes (templates + motor): infra/reels/moldes here, /a0/usr/moldes on the VM (implantar.py --moldes)."""
    reels = pasta_reels()
    return _primeiro(os.environ.get("ESPECIALISTAS_MOLDES"), reels / "moldes" if reels else None, "/a0/usr/moldes")


def pasta_calibracao() -> Path | None:
    acima = _acima(3)
    return _primeiro(os.environ.get("ESPECIALISTAS_CALIBRACAO"), acima / "calibracao" if acima else None,
                     "/a0/usr/calibracao")


# --- the roles -------------------------------------------------------------------------------------------------------

PAPEIS = {
    "critico": """Você é o Crítico da Raiz Connect: a pessoa chata e útil que lê tudo antes de ir a público. Direta,
sem elogio de cortesia, sem rodeio. Você protege o Matheus de publicar coisa mole, genérica ou errada.

O que você faz:
- Sabatina a ideia: qual é a promessa, para quem, por que alguém pararia de rolar a tela para isso. Ideia mole reprova.
- Confere contra o Cérebro da Raiz (oferta, cliente ideal, marca, concorrentes) e contra os critérios do Matheus no
  AR Board. Regra dele citada e quebrada é reprovação, e você diz qual regra.
- Revisa post, carrossel, oferta, landing e mensagem: clareza em 3 segundos, uma ideia por peça, chamada concreta,
  número com "valores de exemplo", linguagem de dono de restaurante, sem jargão, sem promessa que o produto não cumpre.
- Quando a decisão é cara (preço, garantia, oferta, algo que vai para muita gente), diz o risco e o que mudaria.
- Bloqueia o genérico: frase que serve para qualquer empresa ("transforme seu negócio", "solução completa",
  "potencialize"), emoji, travessão, clichê de marketing, imagem que não mostra o que o texto fala.

O que você não faz:
- Não reescreve a peça inteira nem cria uma nova: aponta o problema e a correção mínima.
- Não aprova por educação nem por falta de tempo; na dúvida, reprova e diz o que falta.
- Não inventa fato, número, cliente ou depoimento, e não aceita os que vieram sem origem.
- Não decide pelo Matheus o que é dele (preço, garantia, publicar ou não): aponta e devolve.
- Não fala com o Matheus nem com cliente; responde só ao agente, em JSON.

Responda SÓ com um objeto JSON, sem texto fora dele:
{"veredito": "aprova" | "reprova", "motivos": ["por que, curto, citando a regra"], "sugestoes": ["correção concreta"]}""",

    "designer": """Você é o Designer da Raiz Connect: transforma um briefing numa peça concreta, pronta para o motor de
render, com a qualidade do kit de marca da Raiz. Você pensa em conceito visual antes de pensar em texto.

O que você faz:
- Escolhe um conceito visual próprio para a peça (conversa no celular, caderno, etiqueta, recibo, tela do produto,
  tipografia gigante, foto real...) e o formato que serve à ideia; duas peças seguidas não repetem o conceito.
- Segue o fixo do kit: logo, Manrope + Instrument Serif (uma palavra em serif por slide), família de cores night,
  creme, verdes e lima só para o que sobra, números com "valores de exemplo", sem promessa, sem jargão, sem emoji,
  sem travessão, manchete com no máximo 12 palavras, voz Carolina no vídeo.
- Usa material real: tela real do produto, foto real ou gerada marcada "imagem ilustrativa"; nunca comida desenhada
  em código.
- Preenche a ficha inteira, com textos que cabem (respeita os limites de letras).
- Antes de responder, confere a própria ficha (o Crítico reprovou por isto em 22/10): o título promete exatamente o
  que os itens ou as falas entregam (se diz "3 sinais", são 3 sinais claros); cada fala mostra, na mesma cena, a tela
  que prova o que ela diz; a quantidade de itens e falas está dentro do mínimo e do máximo do molde.

O que você não faz:
- Não foge do kit na Raiz: no motor "molde" a marca raiz já aplica o fixo do kit (logo, Manrope, Instrument Serif,
  night e lima); a liberdade é o conceito (o molde), nunca a identidade.
- Não inventa dado do negócio (preço, custo, depoimento, número de cliente): sem origem, deixa de fora e avisa.
- Não publica, não agenda e não fala com o Matheus; entrega a ficha ao agente.
- Não aprova a própria peça: o Crítico julga depois de você.

Responda SÓ com um objeto JSON, sem texto fora dele.""",
}


# --- model call ------------------------------------------------------------------------------------------------------

def _texto_material(material) -> tuple[str, list[str]]:
    """The piece as text plus the image paths it carries (dict key "imagens", or paths named in the text)."""
    imagens: list[str] = []
    if isinstance(material, dict):
        bruto = material.get("imagens") or []
        imagens = [bruto] if isinstance(bruto, str) else [str(x) for x in bruto]
        resto = {k: v for k, v in material.items() if k != "imagens"}
        texto = json.dumps(resto, ensure_ascii=False, indent=1)
    else:
        texto = str(material or "")
        imagens = [p for p in re.findall(r"(/[^\s,;\"']+\.(?:jpe?g|png|webp))", texto, re.I)]
    if len(texto) > MAX_MATERIAL:
        texto = texto[:MAX_MATERIAL] + "\n…(truncado)"
    return texto, list(dict.fromkeys(imagens))


def _imagem(caminho: str) -> str | None:
    """A data URL for the endpoint's input_image (JPEG via PIL like consultar_sol; raw bytes if PIL is missing)."""
    p = Path(caminho)
    if not p.is_file() or p.suffix.lower() not in EXT_IMAGEM:
        return None
    try:
        from PIL import Image

        img = Image.open(p).convert("RGB")
        img.thumbnail((LADO_MAX, LADO_MAX))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        try:
            return f"data:{EXT_IMAGEM[p.suffix.lower()]};base64," + base64.b64encode(p.read_bytes()).decode()
        except OSError:
            return None


def _enviar(body: dict, login: str, tempo: int = TEMPO) -> dict:
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                                             "X-A0-Dono": login or "matheus"})
    with urllib.request.urlopen(req, timeout=tempo) as r:
        return json.loads(r.read())


def chamar(papel: str, tarefa: str, material, login: str = "matheus") -> dict:
    """One model call as `papel`: the SOUL as instructions, the task and the material as input (images included).
    Returns {"texto", "erro", "imagens", "sem_imagem"}; never raises."""
    if papel not in PAPEIS:
        return {"texto": "", "erro": f"papel desconhecido: {papel}", "imagens": [], "sem_imagem": []}
    texto, caminhos = _texto_material(material)
    content = [{"type": "input_text", "text": f"{tarefa}\n\n## Material\n{texto}".strip()}]
    enviadas, sem = [], []
    for c in caminhos:
        url = _imagem(c) if len(enviadas) < MAX_IMAGENS else None
        if url:
            content.append({"type": "input_image", "image_url": url, "detail": "high"})
            enviadas.append(c)
        else:
            sem.append(c)
    if sem:
        content[0]["text"] += "\n\nArquivos citados que você NÃO está vendo: " + ", ".join(Path(s).name for s in sem)
    body = {"model": MODELO, "reasoning": {"effort": ESFORCO.get(papel, "low")}, "instructions": PAPEIS[papel],
            "input": [{"role": "user", "content": content}]}
    try:
        data = _enviar(body, login, TEMPO_PAPEL.get(papel, TEMPO))
    except Exception as exc:
        return {"texto": "", "erro": f"{type(exc).__name__}: {str(exc)[:200]}", "imagens": enviadas, "sem_imagem": sem}
    saida = "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                    for c in item.get("content", []) if c.get("type") == "output_text")
    return {"texto": saida, "erro": "", "imagens": enviadas, "sem_imagem": sem}


def _json(saida: str):
    achado = re.search(r"\{.*\}", saida or "", re.S)
    if not achado:
        return None
    try:
        d = json.loads(achado.group(0))
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def _lista_textos(v) -> list[str] | None:
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        return None
    return [x.strip() for x in v if x.strip()]


def interpretar_critica(saida: str) -> dict:
    """The Crítico's answer, strictly: a JSON object with veredito aprova|reprova and lists of texts. Anything else is
    "reprova" with motivo "resposta ilegível" (fail closed)."""
    ilegivel = {"veredito": "reprova", "motivos": ["resposta ilegível"], "sugestoes": []}
    d = _json(saida)
    if d is None:
        return ilegivel
    veredito = d.get("veredito")
    motivos, sugestoes = _lista_textos(d.get("motivos")), _lista_textos(d.get("sugestoes"))
    if not isinstance(veredito, str) or veredito.strip().lower() not in ("aprova", "reprova") \
            or motivos is None or sugestoes is None:
        return ilegivel
    veredito = veredito.strip().lower()
    if veredito == "reprova" and not motivos:
        motivos = ["reprovado sem motivo dado"]
    return {"veredito": veredito, "motivos": motivos, "sugestoes": sugestoes}


# --- what the Crítico reads ------------------------------------------------------------------------------------------

def _carregar(nome: str, caminho: Path):
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def contexto_raiz(limite: int = 6000) -> tuple[str, str]:
    """(text, note) from the Cérebro da Raiz (cerebro/helpers/raiz.py `contexto`); empty text plus a clear note when
    it is not installed or fails, so the caller can still judge by the fixed rules."""
    cerebro = PLUGINS / "cerebro" / "helpers"
    try:
        # the cerebro tool's own loader when it is already in memory (same module, same pasta.RAIZ)
        mods = sys.modules.get("cerebro_modulos")
        if mods is None or Path(getattr(mods, "RAIZ", "")).resolve() != cerebro.parent.resolve():
            mods = _carregar("especialistas_cerebro_modulos", cerebro / "modulos.py") \
                if (cerebro / "modulos.py").exists() else None
        if mods is not None and "raiz" in getattr(mods, "CAMINHOS", {}):
            raiz = mods.m("raiz")
        elif (cerebro / "raiz.py").exists():
            raiz = _carregar("cerebro_raiz", cerebro / "raiz.py")
        else:
            return "", "Cérebro da Raiz indisponível (cerebro/helpers/raiz.py não está instalado)"
        texto = str(raiz.contexto(limite=limite) or "").strip()
    except Exception as exc:
        return "", f"Cérebro da Raiz indisponível ({type(exc).__name__}: {str(exc)[:120]})"
    return (texto, "") if texto else ("", "Cérebro da Raiz vazio")


def decisoes_raiz(limite: int = 9000) -> str:
    """Matheus's decisions and preferences for the Raiz (posts, videos, prospecção) from the Segundo Cérebro: they come
    after the AR Board criteria were written and win over them (21/10: the Crítico blocked the iFood video citing a
    week-1 criterion that his later "nexo" decision had replaced). "" when the Pasta is not there."""
    cerebro = PLUGINS / "cerebro" / "helpers"
    try:
        mods = sys.modules.get("cerebro_modulos")
        if mods is None or "briefing" not in getattr(mods, "CAMINHOS", {}):
            mods = _carregar("especialistas_cerebro_modulos", cerebro / "modulos.py")
        return str(mods.m("briefing").para_revisor(mods, "raiz", limite=limite) or "")
    except Exception:
        return ""


def criterios(tipo: str) -> str:
    """Matheus's AR Board criteria for this kind of piece, when they exist (calibracao/<agente>/criterios.md)."""
    pasta = pasta_calibracao()
    if pasta is None:
        return ""
    partes = []
    for agente in CRITERIOS_POR_TIPO.get(tipo, ()):
        arq = pasta / agente / "criterios.md"
        try:
            texto = arq.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if texto:
            partes.append(f"### {agente}\n" + (texto[:MAX_CRITERIOS] + "\n…(truncado)" if len(texto) > MAX_CRITERIOS
                                               else texto))
    return "\n\n".join(partes)


def regras_fixas(tipo: str, material) -> list[str]:
    """Rules checked by code, not by the model: they reprove whatever the model says."""
    texto, _ = _texto_material(material)
    motivos = []
    if EMOJI.search(texto):
        motivos.append("tem emoji (regra fixa: sem emoji em nada público)")
    if TRACO.search(texto):
        motivos.append("tem travessão (regra fixa do AR Board: sem — nem –)")
    if tipo in ("post", "carrossel", "story", "reel") and REAIS.search(texto) and not EXEMPLO.search(texto):
        motivos.append('número em R$ sem "valores de exemplo"')
    return motivos


def criticar(tipo: str, material, *, login: str = "matheus") -> dict:
    """The Crítico's verdict on a piece: {"veredito": "aprova"|"reprova", "motivos": [...], "sugestoes": [...]} plus
    "avisos" (what it judged without). `material`: text, or a dict (fields of the piece; "imagens": paths)."""
    tipo = str(tipo or "").strip().lower()
    if tipo not in TIPOS:
        return {"veredito": "reprova", "motivos": [f"tipo desconhecido: {tipo or '(vazio)'} (use {', '.join(TIPOS)})"],
                "sugestoes": [], "avisos": []}
    if not material or (isinstance(material, str) and not material.strip()):
        return {"veredito": "reprova", "motivos": ["nada para julgar (material vazio)"], "sugestoes": [], "avisos": []}
    ctx, nota = contexto_raiz()
    crit = criterios(tipo)
    avisos = [nota] if nota else []
    if not crit:
        avisos.append(f"sem critérios do AR Board para {tipo}")
    tarefa = (f"Julgue esta peça do tipo **{tipo}** antes de ela ir a público.\n\n"
              f"## Cérebro da Raiz\n{ctx or '(indisponível: ' + nota + '; julgue pelas regras fixas e diga se faltou contexto)'}"
              f"\n\n## Critérios do Matheus (AR Board)\n{crit or '(nenhum registrado para este tipo)'}")
    dec = decisoes_raiz()
    if dec:
        tarefa += f"\n\n## Decisões do Matheus\n{dec}"
    if isinstance(material, dict) and material.get("narracao"):
        tarefa += ("\n\n## Vídeo\nAs imagens são quadros do vídeo (a ordem e o segundo de cada uma estão em \"quadros\") e "
                   "\"narracao\" é a fala com os tempos. Confira: a tela mostra o que a narração diz naquele momento; nenhum "
                   "texto cortado, sobretudo no último quadro (a chamada); o que a legenda afirma aparece no vídeo. Julgue "
                   "pelo que vê e ouve aqui, não exija prova que não caberia num vídeo.")
    r = chamar("critico", tarefa, material, login=login)
    if r["erro"]:
        veredito = {"veredito": "reprova", "motivos": [f"o crítico não respondeu ({r['erro']})"], "sugestoes": []}
    else:
        veredito = interpretar_critica(r["texto"])
    fixas = regras_fixas(tipo, material)
    if fixas:
        veredito = {"veredito": "reprova", "motivos": fixas + [m for m in veredito["motivos"] if m not in fixas],
                    "sugestoes": veredito["sugestoes"]}
    if r.get("sem_imagem"):
        avisos.append("imagens não vistas: " + ", ".join(Path(s).name for s in r["sem_imagem"]))
    veredito["avisos"] = avisos
    return veredito


# --- the Designer ----------------------------------------------------------------------------------------------------

KIT = """Motor de render: sempre "motor": "molde" (é o único que roda aqui; o carrossel e o vídeo "do kit" feitos à mão
são só da sessão de operador, nunca escolha).
- "molde": o que o agente renderiza sozinho, para a Raiz e para outras marcas (22/10). Para a Raiz, "_marca": "raiz"
  na ficha aplica o fixo do kit; o conceito muda de peça para peça (duas seguidas não usam o mesmo molde). Campos:
  "molde" (id do catálogo), "formato" (carrossel|reel|story, um dos formatos do molde), "ficha" (os campos do esquema
  do molde, com "_marca" e "_origem" para dado real; Reel narrado leva "falas", lidas pela voz Carolina).
  Tela do sistema: só as telas reais, escuras e inteiras de /a0/usr/plugins/conteudo/story/telas/ (no molde
  lanca-app/demonstracao, a câmera dá zoom no "destaque" da tela); toda peça com tela diz "valores de exemplo" (campo
  nota do molde, ou no texto do slide/legenda), e cada fala mostra a tela que prova o que ela diz.
  Termo técnico (CMV, ficha técnica, DRE) vem explicado em palavras simples na primeira vez.
Sempre: "marca" ("raiz" ou a pasta da outra marca), "formato" (carrossel|reel|story), "conceito"."""


def catalogo_moldes() -> dict:
    moldes = pasta_moldes()
    arq = moldes / "catalogo.json" if moldes else None
    try:
        return {m["id"]: m for m in json.loads(arq.read_text(encoding="utf-8"))["moldes"]} if arq else {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _validar_ficha(molde: str, ficha: dict) -> list[str]:
    """The moldes motor's own validator (moldes/motor/validar.py) against the molde's esquema.json."""
    moldes = pasta_moldes()
    pasta = moldes / molde if moldes else None
    if not pasta or not (pasta / "esquema.json").exists():
        return [f"molde {molde} não existe no motor"]
    try:
        validar = _carregar("especialistas_validar_molde", moldes / "motor" / "validar.py").validar
        return list(validar(json.loads((pasta / "esquema.json").read_text(encoding="utf-8")), ficha))
    except Exception as exc:
        return [f"não consegui validar a ficha ({type(exc).__name__})"]


def _pode_renderizar() -> str:
    """Empty when the moldes motor can run here (render.py plus Playwright or patchright); otherwise what is missing."""
    moldes = pasta_moldes()
    if moldes is None or not (moldes / "motor" / "render.py").exists():
        return "o motor de render (moldes) não está nesta máquina"
    if importlib.util.find_spec("playwright") is None and importlib.util.find_spec("patchright") is None:
        return "falta o Playwright/Chromium para renderizar"
    return ""


VOZ_CREDENCIAIS = "http://host.docker.internal:8788/voz"  # credenciais_meta.py on the host: only Nova Sonic and Polly


def ambiente_render(pasta: Path) -> dict:
    """The environment render.py runs with: the narration's short-lived credentials come from the host
    (credential_process, profile "voz" in a config file of its own) and the voice cache stays under /a0/usr."""
    config = pasta / "aws-voz.config"
    config.write_text("[profile voz]\nregion = us-east-1\ncredential_process = python3 -c \"import urllib.request; "
                      f"print(urllib.request.urlopen('{VOZ_CREDENCIAIS}', timeout=20).read().decode())\"\n",
                      encoding="utf-8")
    return {**os.environ, "AWS_CONFIG_FILE": str(config), "AWS_PROFILE": "voz", "AWS_REGION": "us-east-1",
            "AWS_SDK_LOAD_CONFIG": "1", "MOLDES_CACHE": os.environ.get("MOLDES_CACHE", "/a0/usr/conteudo/cache-moldes")}


def _pasta_saida() -> Path:
    base = Path(os.environ.get("ESPECIALISTAS_SAIDA", "/a0/usr/workdir/especialistas"))
    try:
        destino = base / time.strftime("%Y%m%d-%H%M%S")
        destino.mkdir(parents=True, exist_ok=True)
        return destino
    except OSError:
        return Path(tempfile.mkdtemp(prefix="especialistas_"))


def renderizar_molde(molde: str, formato: str, ficha: dict, previa: bool = False, saida: Path | None = None,
                     timeout: int = 900, processos: int = 0) -> tuple[list[str], str]:
    """Runs moldes/motor/render.py; returns (files, problem). Exit 2 = ficha refused, 3 = the check found problems.
    previa: the check, the contact sheet and the narration only (narracao.m4a), never the video (decision #39)."""
    moldes = pasta_moldes()
    saida = saida or _pasta_saida()
    saida.mkdir(parents=True, exist_ok=True)
    arq_ficha = saida / "ficha.json"
    arq_ficha.write_text(json.dumps(ficha, ensure_ascii=False, indent=1), encoding="utf-8")
    cmd = [sys.executable, str(moldes / "motor" / "render.py"), molde, str(arq_ficha),
           "--formato", formato, "--saida", str(saida)] + (["--previa"] if previa else []) + (
              ["--processos", str(processos)] if processos else [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(moldes),
                           env=ambiente_render(saida))
    except Exception as exc:
        return [], f"o render não rodou ({type(exc).__name__})"
    arquivos = sorted((str(p) for p in saida.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".mp4", ".m4a")
                       and (previa or p.name != "prev.jpg")),  # the contact sheet is not a slide
                      key=lambda a: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", a)])  # slide2 before slide10
    if r.returncode == 2:
        return [], "o molde recusou a ficha: " + (r.stderr or r.stdout).strip()[-300:]
    if r.returncode == 3:
        return arquivos, "a conferência do render achou problemas: " + (r.stdout or "").strip()[-300:]
    if r.returncode != 0:
        return [], f"o render falhou (código {r.returncode}): " + (r.stderr or "").strip()[-300:]
    return arquivos, ""


# Jargon the Crítico reproved three times in a row on 22/10: a term goes with its plain explanation (the brief's rule)
PERTO = 120
JARGAO = {"CMV": re.compile(r"custo d[aoe]s? (mercadoria|ingrediente|insumo|produto|que (você )?vend)|o quanto (do que|da venda)"
                            r"|quanto do faturamento|custo da comida", re.I)}


def _jargao(texto: str) -> list[str]:
    """The explanation must come with the first time the term appears (22/10: explained only on the last slide, the
    Crítico still reproved), within PERTO letters of it."""
    erros = []
    for termo, explica in JARGAO.items():
        primeira = re.search(rf"\b{termo}\b", texto)
        if primeira and not explica.search(texto[max(0, primeira.start() - PERTO):primeira.end() + PERTO]):
            erros.append(f"ficha: {termo} aparece sem explicação em palavras simples logo na primeira vez (ex.: "
                         f"\"{termo}, o custo dos ingredientes do que você vendeu\")")
    return erros


def _conferir_spec(spec: dict) -> list[str]:
    """Deterministic checks on the Designer's spec; each problem goes to "falta"."""
    problemas = []
    motor, marca = spec.get("motor"), str(spec.get("marca") or "raiz").strip().lower()
    if motor not in MOTORES:
        return [f"motor desconhecido: {motor!r} (use {', '.join(MOTORES)})"]
    if motor == "carrossel_raiz":
        slides = spec.get("slides")
        if not isinstance(slides, list) or not 2 <= len(slides) <= 10:
            problemas.append("carrossel precisa de 2 a 10 slides")
        else:
            for i, s in enumerate(slides, 1):
                manchete = str((s or {}).get("manchete") or "") if isinstance(s, dict) else ""
                if not manchete.strip():
                    problemas.append(f"slide {i} sem manchete")
                elif len(manchete.split()) > 12:
                    problemas.append(f"slide {i}: manchete com {len(manchete.split())} palavras (máx. 12)")
    if motor == "molde":
        if not isinstance(spec.get("ficha"), dict):
            problemas.append("molde sem ficha")
        else:
            if marca == "raiz" and str(spec["ficha"].get("_marca") or "raiz") != "raiz":
                problemas.append("peça da Raiz com outra marca na ficha (_marca): o kit só vale com a marca raiz")
            if marca == "raiz":
                problemas += _jargao(json.dumps(spec["ficha"], ensure_ascii=False))
            pedido = spec.get("_formato_pedido")
            if pedido and str(spec.get("formato") or "").lower() != pedido:
                problemas.append(f"ficha: formato {spec.get('formato')!r}, mas a vaga da semana é {pedido!r}: use um molde "
                                 f"que faça {pedido}")
            problemas += [f"ficha: {e}" for e in _validar_ficha(str(spec.get("molde") or ""), spec["ficha"])]
    return problemas


CORRECOES = 3
REVISOES = 2


FORMATO_DO_BRIEFING = {"CARROSSEL": "carrossel", "REELS": "reel", "STORY": "story"}


def _spec(r: dict, pedido: str = "") -> dict:
    """The Designer's JSON; a ficha with a "molde" is the moldes motor even when "motor" was left out (22/10). The
    format the week asked for travels with the spec: a Reel delivered for a carousel slot is a ficha error."""
    spec = (_json(r["texto"]) if not r["erro"] else None) or {}
    if not isinstance(spec, dict):
        return {}
    if spec.get("molde") and not spec.get("motor"):
        spec["motor"] = "molde"
    if spec and pedido:
        spec["_formato_pedido"] = pedido
    return spec


def _chamada_da_marca() -> str:
    """The Raiz's final scene shows the brand's call to action; the last line of a narrated video says the same."""
    try:
        chamada = json.loads((pasta_moldes() / "marcas" / "raiz" / "marca.json").read_text(encoding="utf-8")).get("chamada")
    except Exception:
        return ""
    return (f"A cena final da Raiz mostra a chamada \"{chamada}\" (a oferta Lucro na Mão em 30 Dias: em 30 dias o dono vê "
            "quanto sobra em cada produto). A última fala de um vídeo narrado liga a ideia da peça a essa oferta e diz a "
            "chamada; a legenda termina com o mesmo passo concreto (toque no link da bio), nunca \"saiba mais\" ou "
            "\"conheça\".\n\n") if chamada else ""


# what each screen shows (22/10: a line said "99Food" over the kitchen screen, which shows iFood and table orders only)
TELAS = {
    "cozinha-kds.jpg": "cozinha (KDS): pedido da mesa ao lado de dois pedidos com o selo iFood, com o tempo de cada um; não mostra 99Food",
    "mapa-de-mesas.jpg": "mapa de mesas do salão: cada mesa livre ou ocupada, com tempo e valor da conta",
    "cmv-real.jpg": "CMV do mês (quanto do faturamento virou custo), a meta e quanto escapou entre a ficha técnica e o estoque",
    "visao-executiva.jpg": "visão executiva: quanto sobrou no mês, receita, CMV, despesas, ponto de empate, caixa e contas vencidas",
    "dashboard-restaurante.jpg": "dashboard do restaurante: faturamento do dia, ticket médio, pedidos, itens mais vendidos, formas de pagamento",
    "dre.jpg": "DRE gerencial: receita, custos, despesas e resultado do período",
    "curva-abc-custos.jpg": "curva ABC de custos: onde se concentra o gasto, por conta",
    "engenharia-de-cardapio.jpg": "engenharia de cardápio: cada prato por quanto vende e quanto sobra (campeão, oportunidade, revisar)",
}


def telas_do_sistema() -> str:
    """The real screens of the system the Designer may use (dark, whole, with the menu: decision #85), by path."""
    pasta = PLUGINS / "conteudo" / "story" / "telas"
    nomes = sorted(p.name for p in pasta.glob("*.jpg")) if pasta.exists() else []
    if not nomes:
        return ""
    return ("## Telas reais do sistema (1440x900, tema escuro, inteiras com o menu; uma empresa de exemplo, valores de "
            "exemplo). A fala só afirma o que a tela mostra:\n"
            + "\n".join(f"- /a0/usr/plugins/conteudo/story/telas/{n}" + (f": {TELAS[n]}" if n in TELAS else "") for n in nomes)
            + "\nPara mostrar o sistema use o molde lanca-app com \"aparelho\": \"computador\" (a câmera dá zoom no "
              "\"destaque\" de cada tela, em % da tela); demonstracao é moldura de celular. Campo \"real\" pede "
              "\"_origem\" com \"sistema\" (tela) ou \"dono\".\n\n")


def _tarefa_correcao(spec: dict, falta: list) -> str:
    """The second try: the template's schema, an example ficha (the Raiz's when there is one) and what failed."""
    pasta = pasta_moldes() / str(spec.get("molde") or "") if pasta_moldes() else None
    esquema = exemplo = ""
    if pasta and (pasta / "esquema.json").exists():
        esquema = (pasta / "esquema.json").read_text(encoding="utf-8")[:6000]
        exemplos = sorted((pasta / "exemplos").glob("*.json"))
        raiz = [e for e in exemplos if '"_marca": "raiz"' in e.read_text(encoding="utf-8")]
        if raiz or exemplos:
            exemplo = (raiz or exemplos)[0].read_text(encoding="utf-8")[:4000]
    return (f"A ficha abaixo não passou nas regras do molde {spec.get('molde')}. Corrija TODOS os erros, respeitando "
            f"os limites de letras do esquema (deixe cada texto uns 10% abaixo do máximo: contar letras é fácil de errar), e devolva a ficha inteira (mesmo formato, com \"motor\": \"molde\"). "
            f"Se este molde não serve para a ideia, troque por outro do catálogo.\n\n## Erros\n"
            + "\n".join(f"- {f}" for f in falta)
            + f"\n\n## Sua ficha\n{json.dumps(spec, ensure_ascii=False)[:6000]}\n\n## Esquema do molde\n{esquema}\n\n"
            + (f"## Exemplo de ficha que passa\n{exemplo}\n\n" if exemplo else "") + telas_do_sistema()
            + "Responda só com o JSON.")


def desenhar(briefing, *, login: str = "matheus") -> dict:
    """A briefing (text or dict) turned into {"spec", "arquivos", "critica", "falta", "render"}: the spec for the
    engine, the rendered files when the engine runs here, the Crítico's verdict (always) and what is still missing."""
    if not briefing or (isinstance(briefing, str) and not briefing.strip()):
        spec, arquivos, falta, render = {}, [], ["briefing vazio"], ""
        return {"spec": spec, "arquivos": arquivos, "falta": falta, "render": render,
                "critica": {"veredito": "reprova", "motivos": ["nada para julgar (briefing vazio)"], "sugestoes": [],
                            "avisos": []}}
    ctx, nota = contexto_raiz(limite=4000)
    catalogo = catalogo_moldes()
    pedido = FORMATO_DO_BRIEFING.get(str(briefing.get("formato") or "").upper(), "") if isinstance(briefing, dict) else ""
    if pedido:  # 22/10: shown the whole catalog it kept answering a carousel slot with a video template
        catalogo = {i: m for i, m in catalogo.items() if pedido in m.get("formatos", [])}
    linhas_cat = "\n".join(f"- {i} ({', '.join(m.get('formatos', []))}): {m.get('situacao', '')} Ficha: "
                           f"{json.dumps(m.get('ficha', {}), ensure_ascii=False)}" for i, m in catalogo.items())
    tarefa = (f"Transforme o briefing numa ficha para o motor de render.\n\n{KIT}\n\n"
              f"## Cérebro da Raiz\n{ctx or '(indisponível: ' + nota + ')'}\n\n"
              + (f"## Catálogo de moldes\n{linhas_cat}\n\n" if linhas_cat else "")
              + telas_do_sistema() + _chamada_da_marca()
              + (f"A vaga é de {pedido}: use só um molde da lista acima, com \"formato\": \"{pedido}\".\n" if pedido else "")
              + "Responda só com o JSON da ficha, com \"motor\".")
    material = {"briefing": briefing} if isinstance(briefing, str) else briefing
    r = chamar("designer", tarefa, material, login=login)
    out = _volta(briefing, material, _spec(r, pedido), r, login)
    # 22/10: the Designer redoes the piece once with the Crítico's reasons before it goes to Matheus
    for _ in range(REVISOES):
        spec = out["spec"]
        if out["critica"]["veredito"] != "reprova" or spec.get("motor") != "molde":
            break
        vistas = (out.get("previa") or [a for a in out["arquivos"] if Path(a).suffix.lower() in EXT_IMAGEM])[:MAX_IMAGENS]
        r = chamar("designer", _tarefa_revisao(spec, out["critica"]), {**material, "imagens": vistas}, login=login)
        novo = _spec(r, pedido)
        if not novo:
            out["falta"] = out["falta"] + [f"o designer não respondeu à revisão ({r['erro'] or 'resposta ilegível'})"]
            break
        anteriores = out.get("revisoes", []) + [out["critica"]["motivos"]]
        out = _volta(briefing, material, novo, r, login)
        out["revisoes"] = anteriores
    return out


def _volta(briefing, material: dict, spec: dict, r: dict, login: str) -> dict:
    """One round: check the ficha (with up to CORRECOES fixes against the template's schema), render it, judge it."""
    falta, arquivos, render = [], [], ""
    previa, narracao, folha = [], "", ""
    if r["erro"]:
        falta.append(f"o designer não respondeu ({r['erro']})")
    elif not spec:
        falta.append("o designer não devolveu uma ficha legível")
    else:
        falta += _conferir_spec(spec)
        # 22/10, real runs: fichas over the template's limits, "_origem" missing, telas without a file, a video
        # shorter than the template allows (refused only when rendering). The Designer gets the template's exact
        # schema, an example and the errors; CORRECOES tries in all, for the ficha and the render together.
        tentativas = CORRECOES
        while True:
            while tentativas and spec.get("motor") == "molde" and any(f.startswith("ficha:") for f in falta):
                tentativas -= 1
                r2 = chamar("designer", _tarefa_correcao(spec, falta), material, login=login)
                novo = _spec(r2, spec.get("_formato_pedido", ""))
                if not novo:
                    falta.append(f"o designer não respondeu à correção ({r2['erro'] or 'resposta ilegível'})")
                    tentativas = 0
                    break
                spec, falta = novo, _conferir_spec(novo)
            arquivos, render, previa, narracao, folha, falta = _renderizar(spec, falta)
            recusa = [f for f in falta if f.startswith("o molde recusou a ficha")]
            if not (recusa and tentativas):
                break
            tentativas -= 1
            r2 = chamar("designer", _tarefa_correcao(spec, recusa), material, login=login)
            novo = _spec(r2, spec.get("_formato_pedido", ""))
            if not novo:
                falta.append(f"o designer não respondeu à correção ({r2['erro'] or 'resposta ilegível'})")
                break
            spec, falta = novo, _conferir_spec(novo)
    formato = str(spec.get("formato") or "").lower()
    imagens = _quadros_para_o_critico(previa, folha) if previa else [a for a in arquivos if Path(a).suffix.lower() in EXT_IMAGEM]
    julgar = {"briefing": briefing, "ficha": spec or r["texto"] or "(vazia)", "problemas": falta, "imagens": imagens}
    if previa:  # 22/10: he read the zoomed frames as a cropped screen and asked for frames he was not sent
        julgar["como_ver_a_previa"] = (
            "É a prévia de um vídeo narrado: a primeira imagem é a folha com um quadro de cada cena, as outras são cenas "
            "inteiras, sempre a do fim entre elas. Em cada tela do sistema, a tela entra inteira (tema escuro, com o menu) "
            "e depois a câmera aproxima o destaque, como o Matheus pediu (decisão #85: vídeo com zoom e movimento); o "
            "quadro do zoom não é recorte. A narração são as \"falas\" da ficha, uma por cena, na ordem das cenas. Esta "
            "revisão é a etapa ANTES do Matheus: depois dela ele ouve o áudio e só então o vídeo é feito (decisão #39); "
            "não reprove por falta da aprovação dele.")
    tipo = ("carrossel" if formato == "carrossel" or spec.get("motor") == "carrossel_raiz"
            else "reel" if formato == "reel" else "post")
    critica = criticar(tipo, julgar, login=login)
    if not spec and critica["veredito"] == "aprova":  # nothing to approve: fail closed
        critica = {**critica, "veredito": "reprova", "motivos": ["sem ficha do designer"] + critica["motivos"]}
    out = {"spec": spec, "arquivos": arquivos, "critica": critica, "falta": falta, "render": render}
    if previa:
        out.update(previa=previa, folha=folha, narracao=narracao, video_pendente=not falta)
    return out


def _quadros_para_o_critico(previa: list, folha: str) -> list:
    """What fits in the Crítico's MAX_IMAGENS: the contact sheet (every scene), then frames spread over the video
    with the last one always in."""
    vagas = MAX_IMAGENS - (1 if folha else 0)
    if len(previa) <= vagas:
        escolhidos = list(previa)
    else:
        passo = (len(previa) - 1) / (vagas - 1)
        escolhidos = [previa[round(i * passo)] for i in range(vagas)]
    return ([folha] if folha else []) + escolhidos


def _renderizar(spec: dict, falta: list) -> tuple:
    """(arquivos, render, previa, narracao, folha, falta) for the spec's motor; nothing renders while falta has items."""
    falta, arquivos, render = list(falta), [], ""
    previa, narracao, folha = [], "", ""
    motor = spec.get("motor")
    if motor == "carrossel_raiz":
        render = (f"no repositório (sessão de operador): criar infra/reels/{spec.get('pasta') or 'c_<nome>'}/index.html "
                  "sobre base/raiz-carrossel.css/js com o conceito desta ficha, depois "
                  f"python3 base/carrossel.py {spec.get('pasta') or 'c_<nome>'} e base/validar_carrossel.py")
        falta.append("render do carrossel da Raiz: cada peça tem HTML próprio (conceito livre do kit); "
                     "o plugin entrega a ficha, não os slides")
    elif motor == "video_kit_raiz":
        render = "no repositório erp-saas: projeto marketing/<nome>/ do kit de motion (skill motion-graphics)"
        falta.append("render do vídeo da Raiz: o kit de motion mora no repositório erp-saas, fora do alcance do agente")
    elif motor == "molde" and not falta:
        sem = _pode_renderizar()
        formato = str(spec.get("formato") or "carrossel")
        render = f"moldes/motor/render.py {spec.get('molde')} <ficha.json> --formato {formato}"
        if sem:
            falta.append(sem)
        elif formato == "carrossel":
            arquivos, problema = renderizar_molde(str(spec["molde"]), formato, spec["ficha"])
            if problema:
                falta.append(problema)
        else:  # a video: only the preview and the narration now; the video after Matheus approves (decision #39)
            feitos, problema = renderizar_molde(str(spec["molde"]), formato, spec["ficha"], previa=True)
            previa = [a for a in feitos if Path(a).suffix.lower() in EXT_IMAGEM and Path(a).name != "prev.jpg"]
            narracao = next((a for a in feitos if a.endswith(".m4a")), "")
            folha = next((a for a in feitos if Path(a).name == "prev.jpg"), "")
            if problema:
                falta.append(problema)
            elif not previa:
                falta.append("a prévia do vídeo não saiu")
    return arquivos, render, previa, narracao, folha, falta


def _tarefa_revisao(spec: dict, critica: dict) -> str:
    """The Crítico reproved: the same piece redone with his reasons (concept or template may change)."""
    return ("O Crítico reprovou a peça abaixo. Refaça a ficha resolvendo cada motivo (pode trocar o conceito ou o molde "
            "se o problema for esse) e devolva a ficha inteira em JSON, com \"motor\".\n\n## Motivos do Crítico\n"
            + "\n".join(f"- {m}" for m in critica.get("motivos") or [])
            + ("\n\n## Sugestões dele\n" + "\n".join(f"- {m}" for m in critica.get("sugestoes") or [])
               if critica.get("sugestoes") else "")
            + f"\n\n## Sua ficha\n{json.dumps(spec, ensure_ascii=False)[:6000]}\n\n{KIT}\n\n" + telas_do_sistema()
            + "Responda só com o JSON.")

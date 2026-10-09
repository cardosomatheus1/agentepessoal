"""Research the web in one call: many searches, pages and video captions read at the same time.

A washer-dryer question by voice note took 207 model calls and ~18 minutes: the agent searched,
opened and read one page per step. Here one tool call runs the searches together, reads the best
pages and YouTube captions together, has the model pull the relevant facts from each source in
parallel, and returns one synthesis with numbered sources. Depth 2 runs a second round on the gaps.
"""

import asyncio
import html as htmllib
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from helpers.tool import Response, Tool

MODELO_URL = "http://host.docker.internal:8787/openai/v1/responses"
MODELO = "openai.gpt-6-luna"
SEARX = "http://localhost:55510/search"
# From an AWS address Google, Startpage, Mojeek and Qwant refuse and Brave rate-limits; Yandex and Bing News answer.
MOTORES = "yandex,bing,bing news,brave,duckduckgo,wikipedia"
YTDLP = ["/opt/venv-a0/bin/python", "-m", "yt_dlp", "--js-runtimes", "node", "--remote-components", "ejs:github"]
PASTA = Path("/a0/usr/workdir/pesquisas")
PERFIL = "/a0/tmp/browser/sessions/shared/Default"  # the agent's browser, logged in to YouTube
MAX_PAGINAS = 14
MAX_VIDEOS = 4
MAX_TEXTO = 14000           # characters of each source given to the model
PARALELO_MODELO = 8
NAVEGADOR = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/124.0 Safari/537.36")
EVITAR = ("wikipedia.org/api", "facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com", "pinterest.")


# ------------------------------------------------------------------ model

def _modelo(texto: str, esforco: str = "low", timeout: int = 180) -> str:
    corpo = {"model": MODELO, "reasoning": {"effort": esforco},
             "input": [{"role": "user", "content": [{"type": "input_text", "text": texto}]}]}
    req = urllib.request.Request(MODELO_URL, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        dados = json.loads(r.read())
    return "".join(c.get("text", "") for item in dados.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []) if c.get("type") == "output_text").strip()


async def _modelo_async(texto: str, esforco: str = "low", sem: asyncio.Semaphore | None = None) -> str:
    if sem is None:
        return await asyncio.to_thread(_modelo, texto, esforco)
    async with sem:
        return await asyncio.to_thread(_modelo, texto, esforco)


# ------------------------------------------------------------------ search and read

async def _buscar(sessao: aiohttp.ClientSession, consulta: str, motores: str = MOTORES) -> list[dict]:
    try:
        async with sessao.post(SEARX, data={"q": consulta, "format": "json", "engines": motores},
                               timeout=aiohttp.ClientTimeout(total=20)) as r:
            dados = await r.json(content_type=None)
        return [{"url": x.get("url", ""), "titulo": x.get("title", ""), "trecho": x.get("content", "")}
                for x in (dados.get("results") or [])[:8] if x.get("url")]
    except Exception:
        return []


def _texto_html(html: str) -> str:
    sopa = BeautifulSoup(html, "lxml")
    for tag in sopa(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"]):
        tag.decompose()
    texto = sopa.get_text("\n")
    linhas = [l.strip() for l in texto.splitlines()]
    return "\n".join(l for l in linhas if len(l) > 2)


async def _ler_pagina(sessao: aiohttp.ClientSession, url: str) -> str:
    try:
        async with sessao.get(url, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=True,
                              headers={"User-Agent": NAVEGADOR, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6"}) as r:
            if r.status >= 400 or "html" not in (r.headers.get("Content-Type") or "html"):
                return ""
            bruto = await r.text(errors="ignore")
        return await asyncio.to_thread(_texto_html, bruto[:3_000_000])
    except Exception:
        return ""


def _vtt_texto(vtt: str) -> str:
    vistos, saida = set(), []
    for linha in vtt.splitlines():
        linha = re.sub(r"<[^>]+>", "", linha).strip()
        if not linha or "-->" in linha or linha.startswith(("WEBVTT", "Kind:", "Language:")) or linha.isdigit():
            continue
        if linha not in vistos:
            vistos.add(linha)
            saida.append(htmllib.unescape(linha))
    return " ".join(saida)


def legendas(url: str, pasta: Path) -> str:
    """Captions of a video (YouTube's own or automatic), without downloading the video."""
    pasta.mkdir(parents=True, exist_ok=True)
    for f in pasta.glob("leg*"):
        f.unlink()
    r = subprocess.run([*YTDLP, "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "pt-orig,pt,pt-BR,en-orig,en",
                        "--cookies-from-browser", f"chromium:{PERFIL}",  # YouTube asks AWS addresses to sign in
                        "--sub-format", "vtt", "-o", str(pasta / "leg.%(ext)s"), "--quiet", "--no-warnings",
                        "--print", "%(title)s", "--no-simulate", url],
                       capture_output=True, text=True, timeout=90)
    arquivos = sorted(pasta.glob("leg*.vtt"), key=lambda p: (".pt" not in p.name, "-orig" not in p.name, p.name))
    if not arquivos:
        return ""
    titulo = (r.stdout or "").strip().splitlines()[0] if (r.stdout or "").strip() else ""
    return (f"Título do vídeo: {titulo}\n" if titulo else "") + _vtt_texto(arquivos[0].read_text(errors="ignore"))


def _e_video(url: str) -> bool:
    return bool(re.search(r"(youtube\.com/watch|youtu\.be/|youtube\.com/shorts/)", url))


# ------------------------------------------------------------------ one round

PROMPT_NOTA = """Você está ajudando numa pesquisa. Pergunta: {pergunta}

Abaixo está o conteúdo de UMA fonte ({tipo}: {url}). Extraia só o que ajuda a responder a pergunta: fatos, números
(medidas, preços, notas, datas), opiniões de quem usou (o que elogiam, do que reclamam), comparações e ressalvas.
Atribua opiniões a quem as dá ("o revisor diz…", "compradores reclamam…"). Não invente nada que não esteja no texto.
Se a fonte não ajuda em nada, responda só: NADA.
Responda em português, em tópicos curtos, no máximo ~250 palavras.

--- conteúdo da fonte ---
{texto}"""

PROMPT_SINTESE = """Pergunta do usuário: {pergunta}

Abaixo estão notas extraídas de {n} fontes numeradas. Escreva a resposta em português:
- comece pela conclusão prática (o que recomendar e por quê);
- depois os pontos que sustentam, com a fonte entre colchetes [n] em cada afirmação importante;
- diga onde as fontes concordam, onde divergem e o que ficou sem confirmação;
- números (medidas, preços, notas) só como aparecem nas fontes, com a fonte;
- seja completo mas direto (sem enrolação), no máximo ~600 palavras.
{extra}
--- notas ---
{notas}"""


async def _rodada(pergunta: str, buscas: list[str], videos: bool, vistos: set[str], pasta: Path,
                  sem: asyncio.Semaphore) -> list[dict]:
    async with aiohttp.ClientSession() as sessao:
        pedidos = [_buscar(sessao, b) for b in buscas]
        if videos:  # reviews on YouTube, from its own search
            pedidos += [_buscar(sessao, b, "youtube") for b in buscas[:2]]
        resultados = await asyncio.gather(*pedidos)
        paginas, filmes = [], []
        # round-robin over the searches so every query contributes its best results
        for i in range(8):
            for lista in resultados:
                if i >= len(lista):
                    continue
                url = lista[i]["url"]
                chave = url.split("#")[0].rstrip("/")
                if chave in vistos or any(e in url for e in EVITAR) or url.lower().endswith(".pdf"):
                    continue
                if _e_video(url):
                    if videos and len(filmes) < MAX_VIDEOS:
                        vistos.add(chave)
                        filmes.append(lista[i])
                elif len(paginas) < MAX_PAGINAS:
                    vistos.add(chave)
                    paginas.append(lista[i])
        textos = await asyncio.gather(*[_ler_pagina(sessao, p["url"]) for p in paginas])
    fontes = []
    for p, t in zip(paginas, textos):
        t = t or p.get("trecho", "")
        if len(t) > 200:
            fontes.append({"url": p["url"], "titulo": p["titulo"], "tipo": "página", "texto": t[:MAX_TEXTO]})
    caps = await asyncio.gather(*[asyncio.to_thread(legendas, f["url"], pasta / f"video{i}") for i, f in enumerate(filmes)],
                                return_exceptions=True)
    for f, c in zip(filmes, caps):
        if isinstance(c, str) and len(c) > 200:
            fontes.append({"url": f["url"], "titulo": f["titulo"], "tipo": "vídeo (legendas)", "texto": c[:MAX_TEXTO]})
    notas = await asyncio.gather(*[
        _modelo_async(PROMPT_NOTA.format(pergunta=pergunta, tipo=f["tipo"], url=f["url"], texto=f["texto"]), "low", sem)
        for f in fontes], return_exceptions=True)
    uteis = []
    for f, n in zip(fontes, notas):
        if isinstance(n, str) and n.strip() and n.strip().upper() != "NADA":
            uteis.append({**f, "nota": n.strip()})
    return uteis


def _buscas_iniciais(pergunta: str) -> list[str]:
    texto = _modelo(
        "Gere de 5 a 8 buscas na web (em português e, se ajudar, em inglês) que juntas cobrem bem esta pergunta: "
        "especificações oficiais, rankings/comparativos, avaliações de usuários, reclamações (ex.: Reclame Aqui), "
        "reviews em vídeo no YouTube. Uma busca por linha, sem numeração.\n\nPergunta: " + pergunta, "low", 90)
    return [l.strip(" -•\t") for l in texto.splitlines() if l.strip(" -•\t")][:8]


async def pesquisar(pergunta: str, buscas: list[str], profundidade: int, videos: bool) -> str:
    inicio = time.time()
    pasta = PASTA / time.strftime("%Y%m%d-%H%M%S")
    pasta.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(PARALELO_MODELO)
    if not buscas:
        buscas = await asyncio.to_thread(_buscas_iniciais, pergunta)
    vistos: set[str] = set()
    fontes = await _rodada(pergunta, buscas, videos, vistos, pasta, sem)
    todas_buscas = list(buscas)
    if profundidade >= 2 and fontes:
        resumo = "\n".join(f"- {f['nota'][:400]}" for f in fontes)
        texto = await _modelo_async(
            "Pergunta: " + pergunta + "\n\nO que já foi achado:\n" + resumo[:12000] +
            "\n\nQuais lacunas faltam para responder bem (dados não confirmados, opiniões de usuários, modelos "
            "não comparados)? Gere até 5 buscas novas na web para cobri-las, uma por linha, sem numeração.", "low")
        novas = [l.strip(" -•\t") for l in texto.splitlines() if l.strip(" -•\t")][:5]
        todas_buscas += novas
        fontes += await _rodada(pergunta, novas, videos, vistos, pasta, sem)
    if not fontes:
        return "Não achei fontes úteis com essas buscas. Tente buscas mais específicas (modelo, marca, termos em inglês)."
    notas = "\n\n".join(f"[{i}] {f['titulo'] or f['url']} ({f['tipo']}) — {f['url']}\n{f['nota']}" for i, f in enumerate(fontes, 1))
    sintese = await _modelo_async(PROMPT_SINTESE.format(pergunta=pergunta, n=len(fontes), notas=notas, extra=""), "medium")
    lista = "\n".join(f"[{i}] {f['titulo'] or ''} — {f['url']}" for i, f in enumerate(fontes, 1))
    (pasta / "notas.md").write_text(f"# {pergunta}\n\nBuscas: {todas_buscas}\n\n{notas}\n", encoding="utf-8")
    (pasta / "sintese.md").write_text(sintese + "\n\n" + lista, encoding="utf-8")
    segundos = int(time.time() - inicio)
    videos_lidos = sum(1 for f in fontes if f["tipo"].startswith("vídeo"))
    return (f"Pesquisa feita em {segundos} s: {len(todas_buscas)} buscas, {len(fontes)} fontes úteis "
            f"({videos_lidos} vídeos pelas legendas).\n\n{sintese}\n\nFontes:\n{lista}\n\n"
            f"Notas completas de cada fonte: {pasta / 'notas.md'}")


class Pesquisar(Tool):
    async def execute(self, pergunta: str = "", buscas=None, profundidade=1, videos=True, **kwargs) -> Response:
        pergunta = str(pergunta or "").strip()
        if not pergunta:
            return Response(message="Informe `pergunta`: o que a pesquisa precisa responder.", break_loop=False)
        if isinstance(buscas, str):
            buscas = [b.strip() for b in re.split(r"[\n;]", buscas) if b.strip()]
        buscas = [str(b) for b in (buscas or [])][:10]
        try:
            profundidade = max(1, min(2, int(profundidade or 1)))
        except (TypeError, ValueError):
            profundidade = 1
        videos = str(videos).lower() not in ("false", "0", "nao", "não", "no")
        try:
            texto = await pesquisar(pergunta, buscas, profundidade, videos)
        except Exception as exc:
            texto = f"A pesquisa falhou: {str(exc)[:400]}. Faça buscas com search_engine."
        return Response(message=texto, break_loop=False)

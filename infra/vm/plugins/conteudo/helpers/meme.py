"""The humor Reel of the week: a POV with a pop-culture meme (05/11, Matheus: "é bom pelo menos 1 por semana com tom
de humor"; "Falei p ter o meme": the meme goes INSIDE the video, not as a note for him).

The format is the one he showed (@trinta.app, with As Branquelas): a phone on a table, a short caption on top
("POV: eu tentando descobrir quanto custa a minha pizza"), the "before" (a notebook with guessed numbers and the meme
over it), then the screen slides to the "after" (the Raiz card with the real numbers) and the caption turns
("a Raiz já sabe"). 11.5 s, 1080x1920, with a sound made here (clock, swoosh, coins, register): no third-party music.

The meme is a short clip from Tenor (search page -> the first results' media ids -> the mp4 of the one chosen). The
page is drawn by the same Chrome that draws the stories; ffmpeg lays the meme over it and adds the sound.

    pov = {"cena": "caderno" | "whatsapp" | "notificacoes" | "ninguem" (CENAS), "legenda_antes",
           "antes": caderno {"titulo", "linhas"} | whatsapp {"contato", "mensagens": [["ele"|"eu", texto], ...]} |
                    notificacoes {"itens": [[app, texto], ...], "hora", "data"} | ninguem {"topo", "linha"},
           "legenda_depois",
           "depois": {"rotulo", "titulo", "linhas": [[rótulo, valor], ...], "cartoes": [[rótulo, valor], ...],
                      "destaque": {"rotulo", "valor", "nota"}},
           "meme": {"busca": "nazare confusa", "indice": 0}}
"""

import json
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LARGURA, ALTURA, FPS, DURACAO, TROCA = 1080, 1920, 24, 11.5, 5.2
# 05/11, Matheus: "precisa ser outro contexto totalmente diferente, n adianta mostrar msm coisa com outro meme": each
# scene is a different situation, and the week never repeats last week's scene (semana.py).
# cena -> (x, y, width, max height) of the meme in the "before"
CENAS = {"caderno": (220, 1120, 640, 440),        # the notebook with guessed numbers; the meme under the writing
         "whatsapp": (220, 1200, 640, 420),       # the chat that hurts (supplier, customer, partner)
         "notificacoes": (220, 1290, 640, 400),   # the lock screen at 23h full of notifications
         "ninguem": (60, 620, 960, 900)}          # "Ninguém: / Dono de pizzaria às 23h:" with the meme in full
MEME_LARGURA, MEME_X, MEME_Y = CENAS["caderno"][2], CENAS["caderno"][0], CENAS["caderno"][1]
LEGENDA_MAX, LINHA_MAX, VALOR_MAX = 90, 40, 24
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿←-⇿️‍⃣]")
TRACO = re.compile("[—–]")
TENOR = "https://tenor.com/pt-BR/search/{}-gifs"
AGENTE = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def validar(pov) -> str:
    """'' when the POV can be made, else why not."""
    if not isinstance(pov, dict):
        return "pov: objeto"
    a, d, m = pov.get("antes"), pov.get("depois"), pov.get("meme")
    if not isinstance(a, dict) or not isinstance(d, dict) or not isinstance(m, dict):
        return "pov precisa de antes, depois e meme (objetos)"
    if not str(m.get("busca") or "").strip():
        return "meme.busca vazio (ex.: \"nazare confusa\")"
    cena = pov.get("cena") or "caderno"
    if cena not in CENAS:
        return f"cena deve ser uma de: {', '.join(CENAS)}"
    for k in ("legenda_antes", "legenda_depois") if cena != "ninguem" else ("legenda_depois",):
        if not str(pov.get(k) or "").strip() or len(str(pov[k])) > LEGENDA_MAX:
            return f"{k}: de 1 a {LEGENDA_MAX} letras"
    linhas = []
    if cena == "caderno":
        linhas = a.get("linhas")
        if not isinstance(linhas, list) or not 2 <= len(linhas) <= 8 or any(len(str(x)) > LINHA_MAX for x in linhas):
            return f"antes.linhas: de 2 a 8 linhas de até {LINHA_MAX} letras"
    elif cena == "whatsapp":
        ms = a.get("mensagens")
        if not str(a.get("contato") or "").strip() or len(str(a["contato"])) > 30:
            return "antes.contato: quem manda a mensagem (até 30 letras)"
        if not isinstance(ms, list) or not 2 <= len(ms) <= 6 or any(
                not (isinstance(x, list) and 2 <= len(x) <= 3 and x[0] in ("ele", "eu") and 0 < len(str(x[1])) <= 90) for x in ms):
            return "antes.mensagens: de 2 a 6 [\"ele\" ou \"eu\", texto até 90 letras]"
        linhas = [str(a["contato"])] + [str(x[1]) for x in ms]
    elif cena == "notificacoes":
        its = a.get("itens")
        if not isinstance(its, list) or not 3 <= len(its) <= 6 or any(
                not (isinstance(x, list) and len(x) == 2 and 0 < len(str(x[0])) <= 20 and 0 < len(str(x[1])) <= 70) for x in its):
            return "antes.itens: de 3 a 6 [app até 20 letras, texto até 70]"
        linhas = [str(x) for it in its for x in it]
    else:
        if not str(a.get("topo") or "").strip() or not str(a.get("linha") or "").strip() \
                or len(str(a["topo"])) > 40 or len(str(a["linha"])) > 60:
            return "antes.topo (ex.: \"Ninguém:\") até 40 letras e antes.linha (ex.: \"Dono de pizzaria às 23h:\") até 60"
        linhas = [str(a["topo"]), str(a["linha"])]
    pares = [p for k in ("linhas", "cartoes") for p in d.get(k) or []]
    if any(not (isinstance(p, list) and len(p) == 2) for p in pares):
        return "depois.linhas e depois.cartoes: pares [rótulo, valor]"
    if len(d.get("linhas") or []) > 7 or len(d.get("cartoes") or []) > 2:
        return "depois: até 7 linhas e 2 cartões"
    if not str(d.get("titulo") or "").strip():
        return "depois.titulo vazio"
    textos = [str(pov.get("legenda_antes") or ""), str(pov.get("legenda_depois")), str(a.get("titulo") or ""),
              str(d.get("rotulo") or ""), str(d.get("titulo"))] + [str(x) for x in linhas] + \
             [str(x) for p in pares for x in p] + [str(v) for v in (d.get("destaque") or {}).values()]
    if any(len(str(v)) > VALOR_MAX for p in pares for v in p[1:]):
        return f"valor com mais de {VALOR_MAX} letras"
    tudo = " ".join(textos)
    if EMOJI.search(tudo):
        return "tem emoji (regra: sem emoji em nada público)"
    if TRACO.search(tudo):
        return "tem travessão (regra do AR Board)"
    return ""


def _baixar(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed hosts: tenor.com, media.tenor.com)
        return r.read()


def opcoes_do_meme(busca: str, baixar=_baixar) -> list[str]:
    """The mp4 links of the first Tenor results for `busca`, in the page's order."""
    termo = re.sub(r"[^a-z0-9]+", "-", str(busca).lower()).strip("-")
    pagina = baixar(TENOR.format(termo)).decode("utf-8", "replace")
    ids = []
    for i in re.findall(r"media\d?\.tenor\.com/([A-Za-z0-9_-]{11})AAAA", pagina):
        if i not in ids:
            ids.append(i)
    return [f"https://media.tenor.com/{i}AAAPo/meme.mp4" for i in ids]


def buscar_meme(busca: str, destino: Path, indice: int = 0, baixar=_baixar) -> str:
    """Downloads the `indice`-th result as `destino` (.mp4). Raises ValueError when there is none."""
    opcoes = opcoes_do_meme(busca, baixar)
    if not opcoes:
        raise ValueError(f"o Tenor não achou meme para \"{busca}\"")
    url = opcoes[min(max(int(indice or 0), 0), len(opcoes) - 1)]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(baixar(url))
    if destino.stat().st_size < 10_000:
        raise ValueError(f"o meme veio vazio ({url})")
    return url


def som(destino: Path) -> Path:
    """The soundtrack, made here: a light beat and chords (tense, then bright), clock ticks while she counts, a swoosh
    at the turn, coins while the number shows up and a register "ding". No third-party music."""
    import numpy as np
    import wave
    sr, n = 44100, int(44100 * DURACAO)
    out = np.zeros(n)
    rng = np.random.default_rng(1)

    def add(sig, t, g=1.0):
        i = int(t * sr)
        j = min(n, i + len(sig))
        if i < n:
            out[i:j] += g * sig[:j - i]

    def env(m, a=0.002, d=0.1):
        t = np.arange(m) / sr
        return np.minimum(1, t / a) * np.exp(-t / d)

    b = 60 / 96
    for k, t in enumerate(np.arange(0, DURACAO, b)):
        m = int(.25 * sr)
        tt = np.arange(m) / sr
        if k % 4 == 0:
            add(np.sin(2 * np.pi * np.cumsum(110 * np.exp(-tt * 18) + 45) / sr) * np.exp(-tt * 9), t, .55)
        if k % 4 == 2:
            m2 = int(.18 * sr)
            add((rng.normal(0, 1, m2) * .6 + np.sin(2 * np.pi * 190 * np.arange(m2) / sr)) * env(m2, .001, .05), t, .22)
        m3 = int(.05 * sr)
        add(rng.normal(0, 1, m3) * env(m3, .0005, .012), t + b / 2, .10)
    for freqs, t0, t1 in (([220, 261.6, 329.6], 0, TROCA), ([196, 246.9, 293.7], TROCA, 8.4),
                          ([174.6, 220, 261.6, 349.2], 8.4, DURACAO)):
        m = int((t1 - t0) * sr)
        tt = np.arange(m) / sr
        s = sum(np.sin(2 * np.pi * f * tt) + .3 * np.sin(4 * np.pi * f * tt) for f in freqs)
        add(s * np.minimum(1, tt / .4) * np.minimum(1, (t1 - t0 - tt) / .4) / len(freqs), t0, .10)
    for i, t in enumerate(np.arange(.3, TROCA - .2, .5)):
        m = int(.03 * sr)
        add(np.sin(2 * np.pi * (2400 if i % 2 else 1800) * np.arange(m) / sr) * env(m, .0003, .006), t, .35)
    m = int(.6 * sr)
    tt = np.arange(m) / sr
    add(np.sin(2 * np.pi * np.cumsum(300 + 120 * np.sin(2 * np.pi * 7 * tt) * np.exp(-tt * 3)) / sr) * env(m, .005, .25), .45, .25)
    m = int(.55 * sr)
    w = rng.normal(0, 1, m) * np.sin(np.pi * np.arange(m) / sr / .55) ** 2
    add(np.convolve(w, np.ones(30) / 30, "same") * 1.2 + w * .25, TROCA - .15, .45)
    for i, t in enumerate(TROCA + .6 + np.cumsum(np.linspace(.14, .05, 14))):
        m = int(.09 * sr)
        x = np.arange(m) / sr
        f = 1300 + i * 70
        add((np.sin(2 * np.pi * f * x) + .5 * np.sin(3 * np.pi * f * x)) * env(m, .001, .03), t, .22)
    m = int(1.4 * sr)
    x = np.arange(m) / sr
    add((np.sin(2 * np.pi * 1568 * x) + .6 * np.sin(2 * np.pi * 2093 * x) + .3 * np.sin(2 * np.pi * 3136 * x))
        * env(m, .001, .45), TROCA + 1.85, .45)
    fo = int(.6 * sr)
    out[-fo:] *= np.linspace(1, 0, fo)
    out /= np.max(np.abs(out)) * 1.15
    with wave.open(str(destino), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes((out * 32767).astype(np.int16).tobytes())
    return destino


def _quadros(pov: dict, pasta: Path, chrome: str) -> Path:
    """Draws every frame of the page (FPS a second) into pasta/q; returns that folder."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        from patchright.sync_api import sync_playwright
    trabalho = pasta / "p"
    for sub in ("meme", "story"):
        shutil.copytree(RAIZ / sub, trabalho / sub)
    js = json.dumps(pov, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = trabalho / "meme" / "pov.html"
    html.write_text(html.read_text(encoding="utf-8").replace("<script>\nconst C", f"<script>window.CAMPOS = {js};</script>\n<script>\nconst C", 1),
                    encoding="utf-8")
    q = pasta / "q"
    q.mkdir()
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=chrome or None,
                                args=["--allow-file-access-from-files", "--disable-dev-shm-usage", "--disable-gpu"])
        pg = b.new_page(viewport={"width": LARGURA, "height": ALTURA})
        pg.goto(f"file://{html}")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(300)
        for i in range(int(DURACAO * FPS)):
            pg.evaluate(f"document.body.dataset.t = '{i / FPS}'; document.dispatchEvent(new Event('quadro'))")
            pg.screenshot(path=str(q / f"f{i:04d}.jpg"), type="jpeg", quality=92)
        b.close()
    return q


def _mascaras(pasta: Path, largura: int, altura: int) -> tuple[Path, Path]:
    from PIL import Image, ImageDraw
    m = Image.new("L", (largura, altura), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, largura - 1, altura - 1), radius=34, fill=255)
    borda = Image.new("RGBA", (largura + 16, altura + 16), (0, 0, 0, 0))
    ImageDraw.Draw(borda).rounded_rectangle((0, 0, largura + 15, altura + 15), radius=42, fill=(255, 255, 255, 255))
    m.save(pasta / "mascara.png")
    borda.save(pasta / "borda.png")
    return pasta / "mascara.png", pasta / "borda.png"


def montar(pov: dict, saida: Path, chrome: str = "", baixar=_baixar) -> dict:
    """The Reel in `saida`: pov.mp4, capa.jpg (the cover: the "after") and 3 frames for the Crítico.
    Returns {"video", "capa", "quadros", "meme"}; raises ValueError when the POV breaks a rule or the meme is missing.
    Playwright's sync API refuses to run where an asyncio loop runs (the agent's own thread): then in a worker thread."""
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _montar(pov, saida, chrome, baixar)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_montar, pov, saida, chrome, baixar).result(timeout=900)


def _montar(pov: dict, saida: Path, chrome: str, baixar) -> dict:
    erro = validar(pov)
    if erro:
        raise ValueError(erro)
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    trabalho = Path(tempfile.mkdtemp(prefix="pov_"))
    try:
        meme = trabalho / "meme.mp4"
        url = buscar_meme(pov["meme"]["busca"], meme, int(pov["meme"].get("indice") or 0), baixar)
        dims = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                               "-of", "csv=p=0", str(meme)], capture_output=True, text=True, check=True).stdout.strip()
        w, h = (int(x) for x in dims.split(",")[:2])
        mx, my, largura, maxima = CENAS[pov.get("cena") or "caderno"]
        altura = min(maxima, int(largura * h / w) // 2 * 2)
        mascara, borda = _mascaras(trabalho, largura, altura)
        q = _quadros(pov, trabalho, chrome)
        trilha = som(trabalho / "som.wav")
        fim = TROCA - 0.05
        video = saida / "pov.mp4"
        filtro = (f"[1:v]scale={largura}:{altura}:force_original_aspect_ratio=increase,crop={largura}:{altura},"
                  f"fps={FPS},format=rgba[n];[2:v]format=gray,scale={largura}:{altura}[m];"
                  f"[n][m]alphamerge,trim=duration={DURACAO},setpts=PTS-STARTPTS[na];[3:v]format=rgba[bd];"
                  f"[0:v][bd]overlay=x={mx - 8}:y={my - 8}:enable='between(t,0.35,{fim})'[v1];"
                  f"[v1][na]overlay=x={mx}:y={my}:enable='between(t,0.35,{fim})'[v]")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(q / "f%04d.jpg"),
                        "-stream_loop", "-1", "-i", str(meme), "-loop", "1", "-i", str(mascara), "-loop", "1", "-i", str(borda),
                        "-i", str(trilha), "-filter_complex", filtro, "-map", "[v]", "-map", "4:a", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-t", str(DURACAO),
                        "-movflags", "+faststart", str(video)], check=True, capture_output=True, timeout=600)
        quadros = []
        for nome, t in (("quadro-1", 2.0), ("quadro-2", TROCA + 0.1), ("capa", DURACAO - 1.0)):
            destino = saida / f"{nome}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1", "-q:v", "3",
                            str(destino)], check=True, capture_output=True, timeout=60)
            quadros.append(str(destino))
        return {"video": str(video), "capa": quadros[-1], "quadros": quadros, "meme": url}
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)

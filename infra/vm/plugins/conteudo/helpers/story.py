"""Stories of @raiz.connect drawn from the kit's layouts (22/10, Matheus: "story sim todo dia ... fazer as artes").

The Raiz carousels and Reels are made piece by piece in an operator session (infra/reels); a story is simpler and
comes every day, so the agent renders it here from five fixed layouts in story/story.html (1080x1920, the kit's
identity): "dica", "post-novo", "video-novo", "bastidor" (a real screen of the system) and "oferta". Rules that are code:
- a field is plain text (the page escapes it); images only from files that exist on this machine (no URL);
- headline up to MANCHETE_MAX letters, no emoji, no dash (AR Board), R$ only with "valores de exemplo" nearby;
- the JPEG comes out 1080x1920 (the size Meta takes for a story).
"""

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

LAYOUTS = ("dica", "post-novo", "video-novo", "bastidor", "oferta")
CAMPOS = ("layout", "manchete", "destaque", "texto", "chamada", "etiqueta", "imagem", "tela", "nota", "pergunta",
          "itens", "claro", "preco", "preco_nota")
MANCHETE_MAX = 90
TEXTO_MAX = 220
LARGURA, ALTURA = 1080, 1920
PASTA = Path(__file__).resolve().parents[1] / "story"
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U0001F900-\U0001F9FF☀-➿⬀-⯿←-⇿️‍⃣]")
TRACO = re.compile("[—–]")
CHROME = ("/a0/tmp/playwright/chromium-1228/chrome-linux/chrome", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def validar(campos: dict) -> str:
    """'' when the story can be drawn, else why not."""
    if not isinstance(campos, dict):
        return "campos: objeto"
    if campos.get("layout") not in LAYOUTS:
        return f"layout deve ser um de: {', '.join(LAYOUTS)}"
    extra = set(campos) - set(CAMPOS)
    if extra:
        return f"campos desconhecidos: {', '.join(sorted(extra))}"
    textos = [str(campos.get(k) or "") for k in ("manchete", "destaque", "texto", "chamada", "etiqueta", "nota", "pergunta",
                                                 "preco", "preco_nota")]
    textos += [str(i) for i in campos.get("itens") or []]
    if campos["layout"] != "oferta" and not str(campos.get("manchete") or "").strip():
        return "manchete vazia"
    if len(str(campos.get("manchete") or "")) > MANCHETE_MAX:
        return f"manchete com mais de {MANCHETE_MAX} letras"
    if any(len(t) > TEXTO_MAX for t in textos):
        return f"texto com mais de {TEXTO_MAX} letras"
    tudo = " ".join(textos)
    if EMOJI.search(tudo):
        return "tem emoji (regra: sem emoji em nada público)"
    if TRACO.search(tudo):
        return "tem travessão (regra do AR Board)"
    if re.search(r"R\$\s*\d", tudo) and campos["layout"] != "oferta" and not re.search(r"valores? de exemplo", tudo, re.I):
        return 'número em R$ sem "valores de exemplo"'
    for k in ("imagem", "tela"):
        if campos.get(k) and not Path(str(campos[k])).is_file():
            return f"{k}: arquivo não encontrado ({campos[k]})"
    if campos["layout"] == "bastidor" and not campos.get("tela"):
        return "bastidor precisa de uma tela real do sistema (tela)"
    if campos.get("itens") is not None and not (isinstance(campos["itens"], list) and 1 <= len(campos["itens"]) <= 4):
        return "itens: lista de 1 a 4"
    return ""


def injetar(pagina: str, dados: dict) -> str:
    """The fields as a JS object before the page's script. "<", ">" and "&" go as \\u escapes, so a text with
    "</script>" can never close the tag and run in the browser (which reads local files)."""
    js = json.dumps(dados, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return pagina.replace("<script>\nconst C", f"<script>window.CAMPOS = {js};</script>\n<script>\nconst C", 1)


def _chrome() -> str:
    return os.environ.get("CHROME") or next((c for c in CHROME if Path(c).exists()), "")


def renderizar(campos: dict, saida: str) -> str:
    """Draws one story into `saida` (.jpg). Raises ValueError when the fields break a rule. Playwright's sync API
    refuses to run where an asyncio loop runs (the agent's own thread): then it draws in a worker thread."""
    erro = validar(campos)
    if erro:
        raise ValueError(erro)
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _desenhar(campos, saida)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_desenhar, campos, saida).result(timeout=180)


def _desenhar(campos: dict, saida: str) -> str:
    from PIL import Image
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # Agent Zero's own browser runs on patchright, the same API (22/10: no playwright there)
        from patchright.sync_api import sync_playwright

    trabalho = Path(tempfile.mkdtemp(prefix="story_"))
    try:
        shutil.copytree(PASTA, trabalho / "s")
        dados = dict(campos)
        for k in ("imagem", "tela"):  # images go next to the page, under a fixed name
            if dados.get(k):
                destino = trabalho / "s" / f"{k}{Path(str(dados[k])).suffix.lower()}"
                shutil.copy(str(dados[k]), destino)
                dados[k] = destino.name
        pagina = injetar((trabalho / "s" / "story.html").read_text(encoding="utf-8"), dados)
        (trabalho / "s" / "story.html").write_text(pagina, encoding="utf-8")
        png = trabalho / "story.png"
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_chrome() or None, args=["--allow-file-access-from-files"])
            pg = b.new_page(viewport={"width": LARGURA, "height": ALTURA})
            pg.goto(f"file://{trabalho / 's' / 'story.html'}")
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(300)
            pg.screenshot(path=str(png))
            b.close()
        Path(saida).parent.mkdir(parents=True, exist_ok=True)
        Image.open(png).convert("RGB").save(saida, "JPEG", quality=92)
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)
    return saida

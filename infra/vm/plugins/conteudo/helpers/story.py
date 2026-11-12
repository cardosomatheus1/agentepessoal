"""Stories of @raiz.connect drawn from the kit's layouts (22/10, Matheus: "story sim todo dia ... fazer as artes").

The Raiz carousels and Reels are made piece by piece in an operator session (infra/reels); a story is simpler and
comes every day, so the agent renders it here from the layouts in story/story.html (1080x1920, the kit's identity).

11/11, Matheus: "Esses storys iguais só com texto diferente postados diariamente estão péssimos, zero criatividade":
nine stories in a row were the same art (dark green, logo on top, white headline with one italic word, paragraph,
button), six of them the "dica". The five layouts shared one composition. Now each layout has its own composition and
background, and VISUAL names the family each one belongs to: the week's rule (helpers/semana.py variedade) never puts
the same layout or the same family on two days in a row, and no layout more than twice in seven days.

Rules that are code:
- a field is plain text (the page escapes it); images only from files that exist on this machine (no URL);
- headline up to MANCHETE_MAX letters, no emoji, no dash (AR Board), R$ only with "valores de exemplo" nearby;
- each layout's own fields (OBRIGA) and sizes, so a text never comes out cut;
- the JPEG comes out 1080x1920 (the size Meta takes for a story).
"""

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

# layout -> the visual family (composition + background). Two layouts of one family look alike at a glance.
VISUAL = {
    "dica": "verde-escuro",          # dark green, headline, paragraph, button
    "oferta": "verde-escuro",        # dark green, headline, list, button
    "bastidor": "tela",              # dark, the system's screen whole
    "tela-zoom": "tela",             # dark, the screen with a big magnifier and a handwritten note
    "post-novo": "creme-capa",       # cream, the carousel's cover fanned out
    "video-novo": "capa-video",      # the Reel's cover full-bleed and blurred behind, play button
    "enquete": "duas-metades",       # the screen split in two, lime and night: "isso ou aquilo"
    "quiz": "creme-carimbo",         # cream paper, the claim in big serif, two stamps (mito / verdade)
    "numero": "lima",                # all lime, one giant number
    "antes-depois": "caderno",       # the notebook sheet above, the system's card below
    "conversa": "whatsapp",          # a WhatsApp chat print (the owner's pain)
    "checklist": "prancheta",        # a white sheet on a clipboard, to screenshot
    "foto": "foto",                  # a full-bleed photo with the text over the gradient
    "caixinha": "caixinha",          # the Instagram question box with the answer below
}
LAYOUTS = tuple(VISUAL)
CAMPOS = ("layout", "manchete", "destaque", "texto", "chamada", "etiqueta", "imagem", "tela", "nota", "pergunta",
          "itens", "claro", "preco", "preco_nota", "opcoes", "resposta", "numero", "antes", "depois", "contato",
          "mensagens", "foco", "seta")
# what each layout needs besides the headline, as the creator reads it (COMO) and as code checks it (validar)
COMO = {
    "dica": "manchete, destaque, texto, chamada (fundo verde escuro; \"claro\": true para o fundo creme)",
    "post-novo": "chama o carrossel do dia: manchete (até 70 letras, do MESMO assunto do post), destaque, chamada; a capa entra sozinha",
    "video-novo": "chama o Reel do dia: manchete (até 70 letras, do MESMO assunto do vídeo), destaque, chamada; a capa entra sozinha",
    "bastidor": "tela (caminho de uma tela real do sistema), manchete, pergunta \"Responde aqui no direct: ...\"",
    "oferta": "Lucro na Mão em 30 Dias: manchete, destaque, itens (1 a 4), chamada",
    "enquete": "isso ou aquilo: manchete = a pergunta (até 70 letras), opcoes = [A, B] (até 34 letras cada), duas escolhas opostas de verdade, nunca a mesma coisa dita de dois jeitos; a resposta vem pelo direct",
    "quiz": "mito ou verdade: manchete = a afirmação (até 80 letras), resposta (\"mito\" ou \"verdade\"), texto = o porquê (até 150)",
    "numero": "número do dia: numero (até 8 letras, ex.: \"32%\", \"7 dias\"), manchete = o que ele quer dizer (até 70), texto (até 140), nota",
    "antes-depois": "antes = 2 a 4 linhas do caderno (até 26 letras cada, no chute), depois = 2 a 3 linhas do sistema (até 40), manchete (até 60)",
    "conversa": "print de WhatsApp com a dor do dono: contato (ex.: \"Fornecedor Queijos\"), mensagens = 2 a 4 [[\"ele\" ou \"eu\", texto até 70]], manchete = a virada (até 60); a arte já traz o selo \"conversa encenada · valores de exemplo\" (não é depoimento: não ponha \"exemplo\" nas falas nem no contato)",
    "checklist": "para printar: manchete (até 50), itens = 3 a 5 (até 52 letras cada), chamada",
    "tela-zoom": "tela (caminho de uma tela real), foco = {\"x\", \"y\"} em % da tela (o ponto que a lupa aumenta: um percentual, um rótulo ou um gráfico, nunca um total em R$ da conta de exemplo), seta = anotação à mão (até 22), manchete (até 64)",
    "foto": "imagem = caminho de uma foto real de comida/cozinha de /a0/usr/moldes/midia/fotos/, manchete (até 70), texto (até 120); chamada é opcional (sem ela sai \"Responde aqui no direct\")",
    "caixinha": "pergunta = a dúvida do dono, como ele fala (até 90), manchete = a resposta (até 70), texto (até 150)",
}
LIMITES = {  # layout -> {field: max letters}; a text over it would be cut or pushed out of the safe area
    "post-novo": {"manchete": 70}, "video-novo": {"manchete": 70},
    "enquete": {"manchete": 70}, "quiz": {"manchete": 80, "texto": 150},
    "numero": {"numero": 8, "manchete": 70, "texto": 140, "nota": 60},
    "antes-depois": {"manchete": 60}, "conversa": {"manchete": 60, "contato": 26},
    "checklist": {"manchete": 50}, "tela-zoom": {"manchete": 64, "seta": 22},
    "foto": {"manchete": 70, "texto": 120}, "caixinha": {"pergunta": 90, "manchete": 70, "texto": 150},
}
MANCHETE_MAX = 90
TEXTO_MAX = 220
LARGURA, ALTURA = 1080, 1920
PASTA = Path(__file__).resolve().parents[1] / "story"
FOTOS = (Path("/a0/usr/moldes/midia/fotos"),  # the moldes' photo bank on the VM; in the repository, infra/reels/moldes
         *(p / "reels" / "moldes" / "midia" / "fotos" for p in Path(__file__).resolve().parents if p.name == "infra"))
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U0001F900-\U0001F9FF☀-➿⬀-⯿←-⇿️‍⃣]")
TRACO = re.compile("[—–]")
CHROME = ("/a0/tmp/playwright/chromium-1228/chrome-linux/chrome", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def _lista(v, minimo: int, maximo: int, letras: int, nome: str) -> str:
    if not (isinstance(v, list) and minimo <= len(v) <= maximo and all(isinstance(x, str) and x.strip() for x in v)):
        return f"{nome}: lista de {minimo} a {maximo} textos"
    if any(len(x) > letras for x in v):
        return f"{nome}: cada um com até {letras} letras"
    return ""


def _do_layout(c: dict) -> str:
    """The layout's own fields: '' or what is missing or too long."""
    layout = c["layout"]
    for campo, maximo in LIMITES.get(layout, {}).items():
        if len(str(c.get(campo) or "")) > maximo:
            return f"{layout}: {campo} com mais de {maximo} letras"
    if layout == "bastidor" and not c.get("tela"):
        return "bastidor precisa de uma tela real do sistema (tela)"
    if layout == "enquete":
        return _lista(c.get("opcoes"), 2, 2, 34, "enquete: opcoes (as duas escolhas)")
    if layout == "quiz":
        if str(c.get("resposta") or "").lower() not in ("mito", "verdade"):
            return "quiz: resposta é \"mito\" ou \"verdade\""
        return "" if str(c.get("texto") or "").strip() else "quiz: texto com o porquê da resposta"
    if layout == "numero":
        return "" if re.search(r"\d", str(c.get("numero") or "")) else "numero: o campo numero leva o número (ex.: \"32%\")"
    if layout == "antes-depois":
        return _lista(c.get("antes"), 2, 4, 26, "antes-depois: antes") or _lista(c.get("depois"), 2, 3, 40, "antes-depois: depois")
    if layout == "conversa":
        m = c.get("mensagens")
        if not (isinstance(m, list) and 2 <= len(m) <= 4 and all(
                isinstance(x, (list, tuple)) and len(x) == 2 and x[0] in ("ele", "eu") and isinstance(x[1], str)
                and 0 < len(x[1]) <= 70 for x in m)):
            return "conversa: mensagens = 2 a 4 pares [\"ele\" ou \"eu\", texto de até 70 letras]"
        if sum(len(x[1]) for x in m) > 200:
            return "conversa: as mensagens somam mais de 200 letras (não cabem acima da manchete)"
        return "" if str(c.get("contato") or "").strip() else "conversa: contato (quem manda a mensagem)"
    if layout == "checklist":
        return _lista(c.get("itens"), 3, 5, 52, "checklist: itens")
    if layout == "tela-zoom":
        f = c.get("foco")
        if not c.get("tela"):
            return "tela-zoom precisa de uma tela real do sistema (tela)"
        if not (isinstance(f, dict) and all(isinstance(f.get(k), (int, float)) and 8 <= f[k] <= 92 for k in ("x", "y"))):
            return "tela-zoom: foco = {\"x\", \"y\"} de 8 a 92 (% da tela onde a lupa aponta)"
        return ""
    if layout == "foto":
        if not c.get("imagem"):
            return "foto precisa de uma foto real (imagem)"
        if not any(Path(str(c["imagem"])).resolve().parent == f.resolve() for f in FOTOS):
            return f"foto: imagem só do banco de fotos ({FOTOS[0]})"
        return ""
    if layout == "caixinha":
        return "" if str(c.get("pergunta") or "").strip() else "caixinha: pergunta (a dúvida do dono)"
    return ""


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
                                                 "preco", "preco_nota", "numero", "contato", "seta", "resposta")]
    for k in ("itens", "opcoes", "antes", "depois"):
        textos += [str(i) for i in (campos.get(k) if isinstance(campos.get(k), list) else [])]
    textos += [str(m[1]) for m in (campos.get("mensagens") if isinstance(campos.get("mensagens"), list) else [])
               if isinstance(m, (list, tuple)) and len(m) == 2]
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
    if campos.get("itens") is not None and not (isinstance(campos["itens"], list) and 1 <= len(campos["itens"]) <= 5):
        return "itens: lista de 1 a 5"
    return _do_layout(campos)


def injetar(pagina: str, dados: dict) -> str:
    """The fields as a JS object before the page's script. "<", ">" and "&" go as \\u escapes, so a text with
    "</script>" can never close the tag and run in the browser (which reads local files)."""
    js = json.dumps(dados, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return pagina.replace("<script>\nconst C", f"<script>window.CAMPOS = {js};</script>\n<script>\nconst C", 1)


def _chrome() -> str:
    achado = os.environ.get("CHROME") or next((c for c in CHROME if Path(c).exists()), "")
    if not achado:  # any Chromium Playwright installed on this machine
        achado = next((str(c) for c in sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome"))), "")
    return achado


DESENHO_MAX = 90  # s: a story takes 1 to 3 s to draw
_DESENHO_CMD = None  # the tests set it (the command that draws); else this file run with --desenhar


def renderizar(campos: dict, saida: str) -> str:
    """Draws one story into `saida` (.jpg). Raises ValueError when the fields break a rule.
    12/11: in the simulated week a checklist story hung inside the browser for more than ten minutes (the same fields
    draw in 1 s when run again) and held the whole week's production. The drawing runs in a process of its own, killed
    with its browser after DESENHO_MAX seconds and tried once more; it also keeps Playwright's sync API away from the
    agent's asyncio loop."""
    erro = validar(campos)
    if erro:
        raise ValueError(erro)
    import signal
    import subprocess
    import sys
    cmd = list(_DESENHO_CMD or [sys.executable, str(Path(__file__).resolve()), "--desenhar"]) + [
        json.dumps(campos, ensure_ascii=False), str(saida)]
    falha = ""
    for _ in range(2):
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            _out, err = proc.communicate(timeout=DESENHO_MAX)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)  # the browser goes with it
            except OSError:
                pass
            proc.communicate()
            falha = f"o desenho do story travou (mais de {DESENHO_MAX} s)"
            continue
        if proc.returncode == 0 and Path(saida).exists():
            return saida
        linhas = [x for x in (err or "").strip().splitlines() if x.strip()]
        raise RuntimeError("o desenho do story falhou: " + (linhas[-1] if linhas else f"código {proc.returncode}")[:300])
    raise RuntimeError(falha + ", duas vezes")


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


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 4 and sys.argv[1] == "--desenhar":
        _desenhar(json.loads(sys.argv[2]), sys.argv[3])

"""The agent sees the page after every browser action that changes it (21/10, 99Food: the password went into a hidden
field, the "Entrar" button never enabled and the menu had no refs; the agent never looked at the screen, Matheus: "era
só enxergar a tela").

The browser tool already saves a screenshot after each action, but only for the UI: the model reads the page as text
and sees an image only when it asks for one. After an action that acts on the page, the screenshot goes into the
history as an image, with what to check. Only the latest one stays: older ones become a line of text."""

import base64
from pathlib import Path

MARCA = "<print automático do navegador>"
TOKENS = 1500

# actions that change the page; reading ones (content, screenshot, list, state, detail) do not need a print
AGEM = {"open", "navigate", "back", "forward", "reload", "click", "double_click", "right_click", "drag", "type",
        "submit", "type_submit", "keyboard", "key_chord", "mouse", "wheel", "scroll", "evaluate", "select_option",
        "set_checked", "upload_file", "multi"}

ORIENTACAO = (
    "Print da página depois de `{acao}` ({largura}x{altura} px; as coordenadas desta imagem são as de "
    "browser action=click com x e y). Confira olhando: o campo ficou preenchido, o botão habilitou, a tela mudou? "
    "Se não, não repita a mesma ação: o elemento que você quer pode não ter ref ou estar escondido. Clique pelas "
    "coordenadas do que aparece aqui (action=click com x,y; para digitar, clique no campo e use action=keyboard "
    "com text). Não use evaluate para clicar.")


def acao_que_age(tool_name: str, args: dict | None) -> str:
    """The browser action when it changes the page, else ''."""
    if (tool_name or "").lower() != "browser" or not isinstance(args, dict):
        return ""
    acao = str(args.get("action") or "").strip().lower().replace("-", "_")
    return acao if acao in AGEM else ""


def caminho_do_print(kvps) -> str:
    snap = (kvps or {}).get("browser_snapshot") if isinstance(kvps, dict) else None
    caminho = str((snap or {}).get("path") or "") if isinstance(snap, dict) else ""
    return caminho if caminho and Path(caminho).is_file() else ""


def _tamanho(dados: bytes) -> tuple[int, int]:
    try:
        from io import BytesIO

        from PIL import Image

        return Image.open(BytesIO(dados)).size
    except Exception:
        return (0, 0)


def mensagem(caminho: str, acao: str) -> dict | None:
    """RawMessage with the text and the image, or None when the file cannot be read."""
    try:
        dados = Path(caminho).read_bytes()
    except OSError:
        return None
    if not dados:
        return None
    largura, altura = _tamanho(dados)
    mime = "image/png" if caminho.lower().endswith(".png") else "image/jpeg"
    url = f"data:{mime};base64,{base64.b64encode(dados).decode()}"
    return {"raw_content": [{"type": "text", "text": ORIENTACAO.format(acao=acao, largura=largura or "?",
                                                                     altura=altura or "?")},
                            {"type": "image_url", "image_url": {"url": url}}],
            "preview": MARCA}


def apagar_antigos(mensagens) -> int:
    """Older automatic prints become a line of text (only the latest one is worth its tokens)."""
    n = 0
    for m in mensagens or []:
        conteudo = getattr(m, "content", None)
        if isinstance(conteudo, dict) and conteudo.get("preview") == MARCA and not getattr(m, "summary", ""):
            m.set_summary("(print antigo do navegador removido)")
            n += 1
    return n

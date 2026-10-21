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
    "browser action=click com x e y). Os números em amarelo sobre os elementos são as refs da leitura da página: "
    "para clicar ou digitar num deles, use a ref (action=click com ref). Confira olhando: o campo ficou preenchido, o botão habilitou, a tela mudou? "
    "Se não, não repita a mesma ação: o elemento que você quer pode não ter ref ou estar escondido. Clique pelas "
    "coordenadas do que aparece aqui (action=click com x,y; para digitar, clique no campo e use action=keyboard "
    "com text). Não use evaluate para clicar.")


# What the 99Food form taught (21/10), in the system prompt every turn: a fixed text, the prompt cache stays.
LICOES = """## Navegador: como agir numa página (lições de 21/10)
- Chame `browser` com os argumentos direto em tool_args (`{"action": "click", "browser_id": 1, "ref": 5}`). Nunca ponha tool_name/tool_args dentro de tool_args.
- Depois de cada ação que muda a página, você recebe o print dela. Só conte como feito o que aparece no print: campo com o texto, botão habilitado, tela nova.
- Item sem ref no `content` (menu, aba, item de lista suspensa): clique pelas coordenadas x,y do print.
- Lista suspensa longa: com ela aberta, role em cima da própria lista (`wheel` com x,y dentro dela e `delta_y` 300 ou mais; o nome é delta_y), olhe o print e repita até aparecer a opção. Ou digite o texto com ela aberta.
- Anexar arquivo: `upload_file` com `path` e a `ref` do botão que abre a escolha de arquivo do computador (ex.: "Anexar", "Navegar neste computador"); sem botão, só o `path`. Depois confira no print que o arquivo aparece anexado.
- Janela do site ("Tem certeza?", "Excluir?"): ela é respondida sozinha com Cancelar e o resultado diz o que perguntou. Se era para confirmar, `{"action": "dialog", "accept": true}` e repita a ação.
- Clicou e nada aconteceu, ou o site deu erro sem dizer o quê: `{"action": "erros"}` mostra os erros da página e as chamadas que falharam (ex.: 422 = dados recusados).
- Esperar a página: `{"action": "wait", "text": "Pedido enviado"}` (também `text_gone`, `selector`, `url`, `load`: true e `timeout` em segundos, até 60). Use em vez de reler a página várias vezes enquanto ela carrega.
- Não use `evaluate` para clicar nem para digitar. Ele não dispara os eventos da página, e a página fica como estava.
- Ação que não mudou nada: não repita a mesma. Tente outro jeito (ref → coordenadas → teclado → endereço direto da tela). Só peça ao Matheus depois de três jeitos diferentes, dizendo quais tentou."""


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

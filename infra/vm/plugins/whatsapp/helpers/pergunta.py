"""Item 15 of docs/AUDITORIA_MATURIDADE_AGENTE.md (Hermes clarify_tool.py, OpenClaw ask-user-tool.ts): a question
whose answer is the person's to give goes to the phone with the options as buttons; the task waits a few minutes in
the same turn and continues with the choice (21/10: 11 of 578 answers ended asking in plain text, "1. … 2. …?", and
the work stopped until he typed back).

The question lives in the asking chat's data (CHAVE); a button is "pg:<login>:<chat id>:<option>"."""

CHAVE = "_pergunta"
PREFIXO = "pg:"
OPCOES_MAX = 3  # Telegram row / WhatsApp reply buttons
TITULO_MAX = 20  # WhatsApp button title limit; the full text goes numbered in the message


def montar(usuario: str, contexto: str, pergunta: str, opcoes: list) -> tuple[str, list]:
    """(message, buttons) for 2 to 3 options; ValueError when the options do not fit."""
    opcoes = [" ".join(str(o).split()) for o in (opcoes or []) if str(o).strip()]
    if not 2 <= len(opcoes) <= OPCOES_MAX:
        raise ValueError(f"de 2 a {OPCOES_MAX} opções (veio {len(opcoes)})")
    texto = f"❓ {' '.join(str(pergunta).split())}\n\n" + "\n".join(f"{i + 1}. {o}" for i, o in enumerate(opcoes))
    botoes = [{"id": f"{PREFIXO}{usuario}:{contexto}:{i}",
               "titulo": (o if len(o) <= TITULO_MAX else f"{i + 1}. {o[:TITULO_MAX - 4]}…")}
              for i, o in enumerate(opcoes)]
    return texto, botoes


def escolher(ctx, usuario: str, botao: str, dono: str) -> tuple[str, str]:
    """(chosen option, '') when the button answers the open question of that chat, pressed by its owner (`dono`, the
    chat's owner login); else ('', why not). Records it."""
    _, login, contexto, indice = (botao.split(":") + ["", "", "", ""])[:4]
    if login != usuario or dono != usuario or ctx is None or str(getattr(ctx, "id", "")) != contexto:
        return "", "outra pessoa ou outra conversa"
    p = ctx.get_data(CHAVE)
    if not isinstance(p, dict) or p.get("escolha"):
        return "", "essa pergunta já foi respondida"
    try:
        escolha = p["opcoes"][int(indice)]
    except (ValueError, IndexError, KeyError, TypeError):
        return "", "opção inválida"
    ctx.set_data(CHAVE, dict(p, escolha=escolha))
    return escolha, ""


def recado_depois(pergunta: str, escolha: str) -> str:
    """The choice made after the task stopped waiting: it reaches that chat as his message."""
    return f"Minha escolha para «{pergunta}»: {escolha}"

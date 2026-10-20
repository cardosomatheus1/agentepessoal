"""Shorter prompt for every model call (20/10): the tool list goes with one line per tool, and each tool's full
description (its manual) comes once per chat, right after the tool's first result.

Measured on 20/10 in Matheus's phone chat: 52 tools = 23.2k tokens of descriptions in every call, ~60% of the fixed part
of the prompt. The model needs the detail of a tool only when it uses it.

Switch: the file DESLIGADO exists = everything here is off (full descriptions again, no manual), no deploy needed."""

import copy
from pathlib import Path

DESLIGADO = Path("/a0/usr/plugins/prompt_enxuto/desligado")
MARCA = "📘 Manual da ferramenta `{nome}`"

# full descriptions seen in this process, by tool name (filled by the first model call after a start or deploy)
MANUAIS: dict[str, str] = {}


def ligado() -> bool:
    try:
        return not DESLIGADO.exists()
    except OSError:
        return True


def encurtar(ferramentas: list, curtas: dict, min_ganho: int, manuais: dict | None = None) -> list:
    """A copy of the Responses tool list with the short descriptions; the full ones are kept in `manuais`.
    Only the description changes (name and parameters stay), and only when it saves at least `min_ganho` characters."""
    manuais = MANUAIS if manuais is None else manuais
    saida = []
    for f in ferramentas or []:
        if not isinstance(f, dict):
            saida.append(f)
            continue
        nome, descricao = str(f.get("name") or ""), str(f.get("description") or "")
        curta = curtas.get(nome)
        if not curta or len(descricao) - len(curta) < min_ganho:
            saida.append(f)
            continue
        manuais[nome] = descricao
        nova = copy.copy(f)
        nova["description"] = curta
        saida.append(nova)
    return saida


def _texto(conteudo) -> str:
    if isinstance(conteudo, str):
        return conteudo
    try:
        return str(conteudo)
    except Exception:
        return ""


def no_historico(saida_historico, trecho: str) -> bool:
    """`trecho` is in what the model still sees of the history (a summarized part no longer counts)."""
    for m in saida_historico or []:
        conteudo = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        if trecho in _texto(conteudo):
            return True
    return False


def manual(nome: str, manuais: dict | None = None) -> str:
    """The history message with a tool's manual, or "" when there is none."""
    texto = (MANUAIS if manuais is None else manuais).get(nome, "")
    if not texto:
        return ""
    return (f"{MARCA.format(nome=nome)} (vem uma vez por conversa; siga-o nesta e nas próximas chamadas dela; "
            f"as regras que valem sempre continuam valendo):\n\n{texto}")

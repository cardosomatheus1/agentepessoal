"""Approve / always allow / refuse the action waiting in a chat (buttons in the chat screen).

Login and chat ownership are checked by Agent Zero and login_usuarios before this runs.
"""

import importlib.util
import sys
from pathlib import Path

from helpers.api import ApiHandler, Request, Response


def carregar(nome: str, caminho: Path):
    """Load a helper by path, again when the file changed (a deploy), keeping pending state."""
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        for estado in ("PENDENTES", "PEDIDOS"):  # waiting approvals / code requests survive
            if antigo is not None and hasattr(antigo, estado):
                setattr(modulo, estado, getattr(antigo, estado))
        sys.modules[nome] = modulo
    return sys.modules[nome]


def revisor():
    nome = "aprovacoes_revisor"
    caminho = Path(__file__).resolve().parents[1] / "helpers" / "revisor.py"
    return carregar(nome, caminho)


class Decidir(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        rv, ctx_id = revisor(), str(input.get("context") or "")
        ok = rv.decidir(ctx_id, str(input.get("decisao") or ""), str(input.get("id") or ""))
        if ok:
            rv.retomar_adiada(ctx_id)  # an action that waited while its task went on, and the task already ended
        return {"ok": ok}

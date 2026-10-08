"""The approval waiting in a chat (polled by the card in the chat screen)."""

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
        if antigo is not None and hasattr(antigo, "PENDENTES"):
            modulo.PENDENTES = antigo.PENDENTES
        sys.modules[nome] = modulo
    return sys.modules[nome]


def revisor():
    nome = "aprovacoes_revisor"
    caminho = Path(__file__).resolve().parents[1] / "helpers" / "revisor.py"
    return carregar(nome, caminho)


class Pendente(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        ctx_id = str(input.get("context") or "")
        p = revisor().PENDENTES.get(ctx_id)
        if not p or p.get("decisao"):
            return {"pendente": None}
        return {"pendente": {"id": p["id"], "resumo": p["resumo"], "categoria": p["categoria"]}}

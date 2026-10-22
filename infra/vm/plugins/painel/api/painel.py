"""The saved live panel of the logged-in person (read only: whatever comes in the request, nothing is changed or read
again from the sources; the page only shows what the job saved)."""

import importlib.util
import sys
from pathlib import Path

from helpers.api import ApiHandler, Request, Response


def painel():
    caminho = Path(__file__).resolve().parents[1] / "helpers" / "painel.py"
    antigo, mtime = sys.modules.get("painel_helper"), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location("painel_helper", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules["painel_helper"] = m
    return sys.modules["painel_helper"]


def _usuario() -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    u = sep.usuario_da_requisicao() if sep else None
    return (u or "matheus").lower()  # single-user installs: the owner


def vivos():
    caminho = Path(__file__).resolve().parents[1] / "helpers" / "vivos.py"
    antigo = sys.modules.get("painel_vivos")
    if antigo is None or getattr(antigo, "_mtime", None) != caminho.stat().st_mtime:
        spec = importlib.util.spec_from_file_location("painel_vivos", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = caminho.stat().st_mtime
        sys.modules["painel_vivos"] = m
    return sys.modules["painel_vivos"]


class Painel(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        usuario = _usuario()
        try:
            lista = vivos().listar(usuario)
        except Exception:
            lista = []
        for d in lista:  # the times, ready to show
            d["lido_as"] = painel().hora(d.get("atualizado"))
            d.pop("receita", None)
        return {"painel": painel().ler(usuario), "vivos": lista}

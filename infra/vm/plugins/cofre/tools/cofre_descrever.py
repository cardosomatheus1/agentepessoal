"""Tool `cofre_descrever`: record what a vault secret is for (account/site) — never its value."""

import importlib.util
import sys
from pathlib import Path

from helpers.tool import Response, Tool


def cofre():
    nome = "cofre_helper"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "cofre.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


class CofreDescrever(Tool):
    async def execute(self, nome: str = "", para: str = "", **kwargs) -> Response:
        c = cofre()
        usuario = c.dono(self.agent.context)
        try:
            c.descrever(usuario, str(nome).strip().upper(), para)
        except ValueError as exc:
            return Response(message=str(exc), break_loop=False)
        return Response(message=f"{nome}: {para} — anotado.", break_loop=False)

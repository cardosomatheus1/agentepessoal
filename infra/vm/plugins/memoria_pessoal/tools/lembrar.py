"""Tool `lembrar`: search the speaker's own old conversations (helpers/busca.py), with date and chat id."""

import asyncio
import importlib.util
import sys
from pathlib import Path

from helpers.tool import Response, Tool

DONO = "matheus"
RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def _busca():
    nome = "memoria_pessoal_busca"
    caminho = RAIZ / "helpers" / "busca.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def quem(context) -> str:
    """Whose conversations: the person speaking (same rule as `decisao`); never someone else's."""
    falante = (context.get_data("usuario") or "").strip().lower()
    if falante:
        return falante
    sep = sys.modules.get("login_usuarios_separacao")
    return ((sep.dono_contexto(context) if sep else context.get_data("dono")) or DONO).strip().lower()


class Lembrar(Tool):
    async def execute(self, busca: str = "", limite: int = 8, **kwargs) -> Response:
        consulta = str(busca or kwargs.get("query") or kwargs.get("texto") or "").strip()
        if not consulta:
            return Response(message="Diga o que procurar em `busca` (palavras do assunto).", break_loop=False)
        b = _busca()
        try:
            n = max(1, min(int(limite or 8), 15))
        except (TypeError, ValueError):
            n = 8
        r = await asyncio.to_thread(b.buscar, quem(self.agent.context), consulta, n)
        return Response(message=b.texto(r, consulta), break_loop=False)

"""Tool `conteudo`: read-only view of the @raiz.connect calendar and of how the posts did (14/10, the weekly marketing
routine of the plan). Scheduling and changes stay with the operator scripts; this tool never writes."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from helpers.tool import Response, Tool

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def _helper():
    caminho = RAIZ / "helpers" / "conteudo.py"
    antigo, mtime = sys.modules.get("conteudo_helper_tool"), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location("conteudo_helper_tool", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules["conteudo_helper_tool"] = m
    return sys.modules["conteudo_helper_tool"]


def _dias(valor, padrao: int) -> int:
    try:
        return max(1, min(60, int(float(str(valor)))))
    except (TypeError, ValueError):
        return padrao


class Conteudo(Tool):
    async def execute(self, acao: str = "agenda", dias=7, **kwargs) -> Response:
        c = _helper()
        acao = str(acao or "agenda").lower()
        if acao == "desempenho":
            api = c.api_do_cofre()
            if not api:
                return Response(message="Sem o token da Meta no cofre (META_IG_TOKEN / META_IG_USER_ID).", break_loop=False)
            r = await asyncio.get_event_loop().run_in_executor(None, c.desempenho, api, _dias(dias, 7))
        else:
            r = c.agenda_proxima(_dias(dias, 7))
        return Response(message=json.dumps(r, ensure_ascii=False), break_loop=False)

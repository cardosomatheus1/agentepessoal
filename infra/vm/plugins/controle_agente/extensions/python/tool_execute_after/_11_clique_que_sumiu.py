"""A browser click on a reference that vanished gets the way out in its own result (helpers/clique.py)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_ARQ = Path(__file__).resolve().parents[3] / "helpers" / "clique.py"
_spec = importlib.util.spec_from_file_location("controle_agente_clique", _ARQ)
clique = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clique)


class CliqueQueSumiu(Extension):
    async def execute(self, response=None, tool_name: str = "", **kwargs):
        if response is None:
            return
        extra = clique.dica(tool_name, str(getattr(response, "message", "") or ""))
        if extra:
            response.message += extra

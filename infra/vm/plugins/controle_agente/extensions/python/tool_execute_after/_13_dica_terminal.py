"""A failed terminal command (or one still running) gets the next step in its own result (helpers/terminal.py)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_ARQ = Path(__file__).resolve().parents[3] / "helpers" / "terminal.py"
_spec = importlib.util.spec_from_file_location("controle_agente_terminal_depois", _ARQ)
terminal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(terminal)


class DicaTerminal(Extension):
    async def execute(self, response=None, tool_name: str = "", **kwargs):
        try:
            if tool_name == "code_execution_tool" and response is not None and isinstance(getattr(response, "message", None), str):
                response.message += terminal.dica(response.message)
        except Exception as exc:  # never break a tool result over this
            print(f"controle_agente: dica do terminal: {exc}", flush=True)

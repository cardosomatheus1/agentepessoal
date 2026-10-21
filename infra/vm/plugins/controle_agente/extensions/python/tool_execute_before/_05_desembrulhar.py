"""Arguments the model wrapped twice reach the tool unwrapped, and browser names in camelCase in snake_case
(helpers/argumentos.py)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_ARQ = Path(__file__).resolve().parents[3] / "helpers" / "argumentos.py"
_spec = importlib.util.spec_from_file_location("controle_agente_argumentos", _ARQ)
argumentos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(argumentos)


class Desembrulhar(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        mudou = argumentos.desembrulhar(tool_name, tool_args)
        mudou = argumentos.nomes_do_navegador(tool_name, tool_args) or mudou
        if mudou:
            tool = getattr(getattr(self.agent, "loop_data", None), "current_tool", None)
            if tool is not None and isinstance(getattr(tool, "args", None), dict) and tool.args is not tool_args:
                argumentos.desembrulhar(tool_name, tool.args)
                argumentos.nomes_do_navegador(tool_name, tool.args)

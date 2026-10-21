"""Before a tool runs (helpers/argumentos.py, ported from Hermes Agent's argument validation):
- repair what is safe: unwrap arguments the model wrapped twice, and turn browser names in camelCase into snake_case;
- validate: an argument the tool does not take means the call is NOT run, and the model gets the accepted names back
  (21/10: deltaY, direction, wait_until... were silently ignored and the agent believed it had acted)."""

import importlib.util
from pathlib import Path

from helpers.errors import RepairableException
from helpers.extension import Extension

_ARQ = Path(__file__).resolve().parents[3] / "helpers" / "argumentos.py"
_spec = importlib.util.spec_from_file_location("controle_agente_argumentos", _ARQ)
argumentos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(argumentos)

_ACEITOS: dict = {}  # tool class -> accepted names (None: unknown, fail open)


class Desembrulhar(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        mudou = argumentos.desembrulhar(tool_name, tool_args)
        mudou = argumentos.nomes_do_navegador(tool_name, tool_args) or mudou
        tool = getattr(getattr(self.agent, "loop_data", None), "current_tool", None)
        if mudou and tool is not None and isinstance(getattr(tool, "args", None), dict) and tool.args is not tool_args:
            argumentos.desembrulhar(tool_name, tool.args)
            argumentos.nomes_do_navegador(tool_name, tool.args)
        if tool is None or str(getattr(tool, "name", "")) != str(tool_name):
            return  # e.g. a tool run through the ferramentas_extras bridge: not this object's arguments
        classe = type(tool)
        if classe not in _ACEITOS:
            try:
                _ACEITOS[classe] = argumentos.aceitos(classe.execute)
            except Exception:
                _ACEITOS[classe] = None
        erro = argumentos.conferir(tool_name, tool_args, argumentos.com_extras(tool_name, _ACEITOS[classe]))
        if erro:
            raise RepairableException(erro)

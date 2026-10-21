"""A terminal command prints its exit code when it fails (helpers/terminal.py, item 6 of the audit)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_ARQ = Path(__file__).resolve().parents[3] / "helpers" / "terminal.py"
_spec = importlib.util.spec_from_file_location("controle_agente_terminal_antes", _ARQ)
terminal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(terminal)


class CodigoDeSaida(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        try:
            if (tool_name == "code_execution_tool" and isinstance(tool_args, dict)
                    and str(tool_args.get("runtime", "")).strip().lower() == "terminal"
                    and isinstance(tool_args.get("code"), str)):
                tool_args["code"] = terminal.com_codigo_de_saida(tool_args["code"])
        except Exception as exc:  # never block the agent over this
            print(f"controle_agente: código de saída: {exc}", flush=True)

"""After a browser action that changes the page, keep its screenshot to show the model (helpers/ver_tela.py)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_ARQ = Path(__file__).resolve().parents[3] / "helpers" / "ver_tela.py"
_spec = importlib.util.spec_from_file_location("navegador_rapido_ver_tela", _ARQ)
ver_tela = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ver_tela)


class GuardarPrint(Extension):
    async def execute(self, response=None, tool_name: str = "", **kwargs):
        try:
            tool = getattr(getattr(self.agent, "loop_data", None), "current_tool", None)
            acao = ver_tela.acao_que_age(tool_name, getattr(tool, "args", None))
            caminho = ver_tela.caminho_do_print(getattr(getattr(tool, "log", None), "kvps", None)) if acao else ""
            if caminho:
                self.agent.set_data("_navegador_print", {"caminho": caminho, "acao": acao})
        except Exception as exc:  # never break a tool result over this
            print(f"navegador_rapido: print: {exc}", flush=True)

"""Before the next model call, the page screenshot kept by tool_execute_after goes into the history as an image, after
the tool result (helpers/ver_tela.py). Only the latest one stays."""

import importlib.util
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension

_ARQ = Path(__file__).resolve().parents[3] / "helpers" / "ver_tela.py"
_spec = importlib.util.spec_from_file_location("navegador_rapido_ver_tela", _ARQ)
ver_tela = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ver_tela)


class MostrarPrint(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        pendente = self.agent.get_data("_navegador_print") if self.agent else None
        if not pendente:
            return
        self.agent.set_data("_navegador_print", None)
        try:
            msg = ver_tela.mensagem(pendente.get("caminho", ""), pendente.get("acao", ""))
            if msg is None:
                return
            ver_tela.apagar_antigos(self.agent.history.all_messages())
            self.agent.hist_add_message(False, content=msg, tokens=ver_tela.TOKENS)
        except Exception as exc:  # never block the model call over this
            print(f"navegador_rapido: mostrar print: {exc}", flush=True)

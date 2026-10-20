"""Every model call carries the tool list with one line per tool (helpers/indice.py) instead of each tool's whole
prompt; the full text is kept as the tool's manual, which the chat gets once, after the tool's first result
(_functions/agent/Agent/hist_add_tool_result/end/_50_manual_na_primeira.py). Only the Responses API sends a tool list
(the presets use it); any surprise leaves the list as it was."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("prompt_enxuto_carregar", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)


class FerramentasCurtas(Extension):
    async def execute(self, call_data: dict | None = None, **kwargs):
        if not isinstance(call_data, dict) or not call_data.get("a0_responses_function_tools"):
            return
        try:
            e, i = carregar.modulo("enxuto"), carregar.modulo("indice")
            if e.ligado():
                call_data["a0_responses_function_tools"] = e.encurtar(
                    call_data["a0_responses_function_tools"], i.CURTAS, i.MIN_GANHO)
        except Exception as exc:  # never in the way of a model call
            print(f"prompt_enxuto: lista de ferramentas mantida inteira: {type(exc).__name__}: {exc}", flush=True)
        try:
            # 21/10: the tools outside the core go behind ferramentas_extras (helpers/sob_demanda.py)
            sd = carregar.modulo("sob_demanda")
            if sd.ligado() and self.agent is not None:
                lista, ocultas = sd.separar(call_data["a0_responses_function_tools"])
                self.agent.set_data(sd.CHAVE, ocultas)
                call_data["a0_responses_function_tools"] = sd.com_ponte(lista, ocultas)
        except Exception as exc:
            print(f"prompt_enxuto: ferramentas sob demanda desligadas nesta chamada: {type(exc).__name__}: {exc}",
                  flush=True)

"""Text mode (the Sonnet preset, `a0_api_mode: chat`): Agent Zero sends no native tool list and writes each tool's
whole prompt into the system prompt ("## available tools"; 77 thousand characters measured on 20/10). Here that
section gets the same short line per tool as the native list (helpers/indice.py); the whole prompt becomes the tool's
manual, which comes once per chat after the first result (_functions/.../hist_add_tool_result/end/_50_manual_na_primeira.py).

Runs after every system_prompt extension and before the extras (cache_prompt, _98). The Responses mode is left alone
(its tool list is shortened in chat_model_call_before/_50_ferramentas_curtas.py). Any surprise leaves the prompt as
it was."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("prompt_enxuto_carregar", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)


class FerramentasCurtasTexto(Extension):
    async def execute(self, loop_data=None, **kwargs):
        agent = self.agent
        sistema = getattr(loop_data, "system", None)
        if agent is None or not isinstance(sistema, list) or not sistema:
            return
        try:
            e, i = carregar.modulo("enxuto"), carregar.modulo("indice")
            if not e.ligado() or not e.modo_texto(agent):
                return
            partes = e.partes_das_ferramentas(agent)
            # the tools section: the system part holding the most tool prompts (Agent Zero's _11_tools_prompt)
            contagem = [sum(1 for _, p in partes if p and isinstance(s, str) and p in s) for s in sistema]
            if partes and max(contagem) > 0:
                n = contagem.index(max(contagem))
                sistema[n] = e.encurtar_texto(sistema[n], partes, i.CURTAS, i.MIN_GANHO)
        except Exception as exc:  # never in the way of a model call
            print(f"prompt_enxuto: ferramentas do prompt de texto mantidas inteiras: {type(exc).__name__}: {exc}",
                  flush=True)

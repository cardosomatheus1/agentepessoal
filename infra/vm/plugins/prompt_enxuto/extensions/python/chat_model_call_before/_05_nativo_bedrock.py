"""Claude on Bedrock in native tool mode (preset in Responses mode, through our proxy): the call goes without Agent
Zero's prompt-cache markers, otherwise Agent Zero switches it to Chat Completions and drops the tool list
(helpers/nativo.py has the why). The proxy puts the cache points. Only when the call carries native tools; works with
the plugin's switch on or off (it is about the tools reaching the model, not about shortening). Any surprise leaves
the call as it was."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("prompt_enxuto_carregar", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)


class NativoBedrock(Extension):
    async def execute(self, call_data: dict | None = None, **kwargs):
        if not isinstance(call_data, dict) or not call_data.get("a0_responses_function_tools"):
            return
        try:
            if call_data.get("explicit_caching") and carregar.modulo("nativo").sem_marcas_do_a0(call_data.get("model")):
                call_data["explicit_caching"] = False
        except Exception as exc:  # never in the way of a model call
            print(f"prompt_enxuto: chamada nativa mantida como estava: {type(exc).__name__}: {exc}", flush=True)

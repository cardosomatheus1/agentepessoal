"""Mirror a subordinate's steps onto the chat the person is watching.

While the main agent waits on a subordinate (or a parallel job), its chat used to sit still for
minutes with no sign of life — "travou?" — and the person stopped it right before it finished.
"""

import importlib.util
import sys
import time
from pathlib import Path

from helpers.extension import Extension

def _familia():
    name = "controle_agente_familia_v2"
    if name not in sys.modules:
        root = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
        spec = importlib.util.spec_from_file_location(name, root / "helpers" / "familia.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]

class ProgressoSubagente(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if not self.agent:
            return
        try:
            ctx = self.agent.context
            raiz = _familia().raiz(ctx)
            if raiz is ctx and self.agent.number == 0:
                if tool_name in _familia().ESPERA:  # main agent starts waiting on subordinates
                    ctx.set_data("_subagente_inicio", time.time())
                    ctx.set_data("_subagente_passos", 0)
                return
            passos = int(raiz.get_data("_subagente_passos") or 0) + 1
            raiz.set_data("_subagente_passos", passos)
            minutos = int((time.time() - (raiz.get_data("_subagente_inicio") or time.time())) // 60)
            raiz.log.set_progress(f"Subagente · passo {passos} · {tool_name} · {minutos} min", active=True)
        except Exception:
            pass

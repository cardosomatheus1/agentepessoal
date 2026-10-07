"""Held messages still pending when the task ends become interventions, which
_40_resgatar_mensagem then delivers as a new turn."""

import importlib.util
import sys
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


class EntregarNoFim(Extension):
    async def execute(self, **kwargs):
        if not self.agent:
            return
        try:
            _familia().entregar(self.agent.context)
        except Exception:
            pass

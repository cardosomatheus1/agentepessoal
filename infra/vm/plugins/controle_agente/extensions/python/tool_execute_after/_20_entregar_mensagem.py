"""Hand held messages to the main agent right after the subordinate's result is saved (the next check reads it)."""

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


class EntregarDepoisDaFerramenta(Extension):
    async def execute(self, tool_name: str = "", **kwargs):
        if not self.agent or self.agent.number != 0:
            return
        try:
            _familia().entregar(self.agent.context)
        except Exception:
            pass

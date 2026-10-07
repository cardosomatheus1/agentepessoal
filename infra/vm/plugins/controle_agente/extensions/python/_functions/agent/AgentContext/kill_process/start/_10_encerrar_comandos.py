"""Stop / Nudge / chat reset: also end the commands the agent left running in its terminals."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

def _processos():
    """Load helpers/processos.py once per server, so frozen-pid state survives extension reloads."""
    name = "controle_agente_processos_v2"
    if name not in sys.modules:
        root = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
        spec = importlib.util.spec_from_file_location(name, root / "helpers" / "processos.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


class EncerrarComandos(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        args = (data or {}).get("args") or ()
        context = args[0] if args else None
        if context is not None and getattr(context, "task", None) is not None:
            _processos().end(context)

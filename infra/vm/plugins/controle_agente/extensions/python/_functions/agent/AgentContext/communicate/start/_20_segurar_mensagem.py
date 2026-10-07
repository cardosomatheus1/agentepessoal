"""Hold a message that arrives while the main agent waits on a subordinate (see helpers/familia.py)."""

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


class SegurarMensagem(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        try:
            args = (data or {}).get("args") or ()
            ctx = args[0] if args else None
            msg = args[1] if len(args) > 1 else (data or {}).get("kwargs", {}).get("msg")
            if ctx is None or msg is None or not (msg.message or msg.attachments):
                return
            familia = _familia()
            if familia.esperando_subagente(ctx):
                familia.adiar(ctx, msg)
                data["result"] = ctx.task  # skip communicate(): no intervention now
        except Exception:
            pass

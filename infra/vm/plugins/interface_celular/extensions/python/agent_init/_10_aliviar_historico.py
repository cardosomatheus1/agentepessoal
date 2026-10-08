"""Send long chats to the screen with older steps trimmed (idempotent)."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension


def _aliviar():
    name = "interface_celular_aliviar"
    root = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
    path = root / "helpers" / "aliviar.py"
    m = sys.modules.get(name)
    if m is None or getattr(m, "_mtime", None) != path.stat().st_mtime:  # first load or updated file
        spec = importlib.util.spec_from_file_location(name, path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = path.stat().st_mtime
        sys.modules[name] = m
    return m


class AliviarHistorico(Extension):
    def execute(self, **kwargs):
        try:
            _aliviar().aplicar()
        except Exception as exc:
            print(f"interface_celular: histórico leve não aplicado: {exc}", flush=True)

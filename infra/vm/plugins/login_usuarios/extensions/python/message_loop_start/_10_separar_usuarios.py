"""Apply the per-user separation patches (idempotent)."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

def _sep():
    name = "login_usuarios_separacao"
    if name not in sys.modules:
        root = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
        spec = importlib.util.spec_from_file_location(name, root / "helpers" / "separacao.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules[name] = m
        spec.loader.exec_module(m)
    return sys.modules[name]


class SepararUsuarios(Extension):
    def execute(self, **kwargs):
        try:
            _sep().aplicar()
        except Exception as exc:
            print(f"login_usuarios: separação não aplicada: {exc}", flush=True)

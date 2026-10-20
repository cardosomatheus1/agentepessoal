"""Load this plugin's helper by path (reloaded when the file changes), as the other plugins do."""

import importlib.util
import sys
from pathlib import Path

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def objetivo():
    nome = "objetivo_vivo_objetivo"
    caminho = _RAIZ / "helpers" / "objetivo.py"
    mtime = caminho.stat().st_mtime
    antigo = sys.modules.get(nome)
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]

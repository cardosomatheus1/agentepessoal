"""Load this plugin's helpers by path (Agent Zero loads each extension file on its own), again when a file changes, so a
deploy takes effect without restarting the agent. The full tool descriptions already seen survive a reload."""

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def modulo(arquivo: str):
    nome, caminho = f"prompt_enxuto_{arquivo}", RAIZ / "helpers" / f"{arquivo}.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        novo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(novo)
        novo._mtime = mtime
        if antigo is not None and isinstance(getattr(antigo, "MANUAIS", None), dict):
            novo.MANUAIS.update(antigo.MANUAIS)
        sys.modules[nome] = novo
    return sys.modules[nome]

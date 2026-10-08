"""Apply the vault masking of the on-screen step log (helpers/mascarar_log.py)."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def _carregar(nome: str, caminho: Path):
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        sys.modules[nome] = modulo
    return sys.modules[nome]


class MascararLog(Extension):
    def execute(self, **kwargs):
        try:
            cofre = _carregar("cofre_helper", RAIZ / "helpers" / "cofre.py")
            _carregar("cofre_mascarar_log", RAIZ / "helpers" / "mascarar_log.py").aplicar(cofre)
        except Exception as exc:
            print(f"cofre: step-log masking not applied: {exc}", flush=True)

"""Apply the browser fixes once per server (idempotent)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension


class CorrigirNavegador(Extension):
    def execute(self, tool_args=None, tool_name: str = "", **kwargs):
        root = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
        spec = importlib.util.spec_from_file_location("navegador_rapido_correcoes", root / "helpers" / "correcoes.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            module.aplicar()
            if tool_name == "browser":
                module.argumentos_de_upload(tool_args)
        except Exception as exc:  # never block the agent over this
            print(f"navegador_rapido: {exc}", flush=True)

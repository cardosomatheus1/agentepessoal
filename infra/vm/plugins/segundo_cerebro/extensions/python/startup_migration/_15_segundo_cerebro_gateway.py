"""Before the web app is built: wrap UiServerRuntime.create so it gets the Segundo Cérebro gateway (idempotent)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension


def _gateway():
    root = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
    spec = importlib.util.spec_from_file_location("segundo_cerebro_gateway", root / "helpers" / "gateway.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m._mtime = (root / "helpers" / "gateway.py").stat().st_mtime
    return m


class SegundoCerebroGateway(Extension):
    def execute(self, **kwargs):
        try:
            g = _gateway()
            problemas = g.validar_plugin()
            if problemas:
                print(f"segundo_cerebro: gateway não registrado: {'; '.join(problemas)}", flush=True)
                return
            g.instalar_wrapper()
        except Exception as exc:
            print(f"segundo_cerebro: gateway não registrado: {type(exc).__name__}: {exc}", flush=True)

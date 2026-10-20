"""Lifecycle of the Segundo Cérebro gateway (framework runtime). No execute.py: nothing here is manual.

install     validate the plugin and wrap UiServerRuntime.create (the gateway registers when the web app is built)
pre_update  stop the Node server, so the updated release starts clean on the next request
uninstall   stop the Node server and switch the gateway off in this process (routes stop being served)
"""

import importlib.util
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _gateway():
    spec = importlib.util.spec_from_file_location("segundo_cerebro_gateway_hooks", _DIR / "helpers" / "gateway.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def install() -> bool:
    g = _gateway()
    problemas = g.validar_plugin(_DIR)
    if problemas:
        raise RuntimeError("segundo_cerebro: " + "; ".join(problemas))
    g.instalar_wrapper()
    return True


def pre_update() -> bool:
    _gateway().parar_tudo()
    return True


def uninstall() -> bool:
    g = _gateway()
    g.parar_tudo()
    g.estado().desativado = True
    return True

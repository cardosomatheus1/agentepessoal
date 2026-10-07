"""A new chat belongs to whoever is logged in when it is created (and applies the patches)."""

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


class DonoDaConversa(Extension):
    def execute(self, **kwargs):
        try:
            sep = _sep()
            sep.aplicar()
            if not self.agent or self.agent.number != 0:
                return
            ctx = self.agent.context
            u = sep.usuario_da_requisicao()
            if u and not ctx.get_data("dono"):
                ctx.set_data("dono", u)
        except Exception as exc:
            print(f"login_usuarios: dono não definido: {exc}", flush=True)

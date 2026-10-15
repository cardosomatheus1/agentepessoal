"""A guest's chat (helpers/convidados.py) only runs the guest's tools, only inside the guest's project, and never
on local paths outside the guest's own folders."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def convidados():
    nome, caminho = "login_usuarios_convidados", RAIZ / "helpers" / "convidados.py"
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def dono(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return sep.dono_contexto(context) if sep else str(context.get_data("dono") or "matheus").lower()


class Convidado(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if not self.agent or not tool_name:
            return
        c = convidados()
        login = dono(self.agent.context)
        if not c.convidado(login):
            return
        from helpers import projects

        motivo = c.bloqueio(login, tool_name, tool_args or {}, projects.get_context_project_name(self.agent.context))
        if motivo:
            from helpers.errors import RepairableException

            print(f"login_usuarios: convidado {login} sem {tool_name}: {motivo[:80]}", flush=True)
            raise RepairableException(motivo)

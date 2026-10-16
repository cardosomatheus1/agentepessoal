"""A guest listing or reading scheduled tasks sees only their own (the scheduler tool lists everyone's)."""

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


class AgendaConvidado(Extension):
    async def execute(self, response=None, tool_name: str = "", **kwargs):
        if not self.agent or response is None or tool_name.partition(":")[0] != "scheduler":
            return
        sep = sys.modules.get("login_usuarios_separacao")
        login = sep.dono_contexto(self.agent.context) if sep else str(self.agent.context.get_data("dono") or "")
        c = convidados()
        if not c.convidado(login):
            return
        if str(getattr(response, "message", "")).lstrip().startswith(("[", "{")):  # task lists / task details
            response.message = c.filtrar_agenda(login, response.message)

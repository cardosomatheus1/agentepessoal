"""§§secret(NAME) in a tool's arguments becomes the chat owner's value, right before it runs
(after the approval gate, which only ever sees the placeholder)."""

import importlib.util
import sys
from pathlib import Path


def cofre():
    nome = "cofre_helper"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "cofre.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


from helpers.extension import Extension


class SegredosDaPessoa(Extension):
    async def execute(self, tool_args: dict | None = None, **kwargs):
        if not self.agent or not tool_args:
            return
        c = cofre()
        dados = c.carregar(c.dono(self.agent.context))
        if not dados:
            return
        for k, v in list(tool_args.items()):
            tool_args[k] = c.trocar(v, dados)

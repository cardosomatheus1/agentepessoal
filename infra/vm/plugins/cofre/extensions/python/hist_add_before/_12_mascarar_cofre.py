"""Values from the chat owner's vault never enter the history: a password pasted in a message
(or echoed by any tool) is stored as §§secret(NAME)."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension


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


def _mascarar(valor, c, dados):
    if isinstance(valor, str):
        return c.mascarar(valor, dados)
    if isinstance(valor, dict):
        return {k: _mascarar(v, c, dados) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_mascarar(v, c, dados) for v in valor]
    return valor


class MascararCofre(Extension):
    def execute(self, content_data: dict | None = None, **kwargs):
        if not self.agent or not content_data:
            return
        c = cofre()
        dados = c.carregar(c.dono(self.agent.context))
        if dados and "content" in content_data:
            content_data["content"] = _mascarar(content_data["content"], c, dados)

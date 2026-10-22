"""A channel chat (plugins/canais) carries its name and purpose in its instructions every turn (22/10, Claude Duet)."""

import importlib.util
import sys
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension


def canais():
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "canais.py"
    antigo = sys.modules.get("canais_helper")
    if antigo is None or getattr(antigo, "_mtime", None) != caminho.stat().st_mtime:
        spec = importlib.util.spec_from_file_location("canais_helper", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = caminho.stat().st_mtime
        sys.modules["canais_helper"] = m
    return sys.modules["canais_helper"]


class CanalPrompt(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent or self.agent.number != 0:
            return
        canal = self.agent.context.get_data("canal")
        if isinstance(canal, dict) and canal.get("nome") and canal.get("proposito"):
            system_prompt.append(canais().instrucao(canal))

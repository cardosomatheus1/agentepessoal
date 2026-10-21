"""The browser lessons from the 99Food form (helpers/ver_tela.py LICOES), in every system prompt."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_ARQ = Path(__file__).resolve().parents[3] / "helpers" / "ver_tela.py"
_spec = importlib.util.spec_from_file_location("navegador_rapido_ver_tela", _ARQ)
ver_tela = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ver_tela)


class LicoesNavegador(Extension):
    async def execute(self, system_prompt: list[str] = [], **kwargs):
        system_prompt.append(ver_tela.LICOES)

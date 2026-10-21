"""Tool `ler`: a whole file in pages (helpers/ler.py)."""

import importlib.util
from pathlib import Path

from helpers.tool import Response, Tool

_ARQ = Path(__file__).resolve().parents[1] / "helpers" / "ler.py"
_spec = importlib.util.spec_from_file_location("ler_arquivo_ler", _ARQ)
leitor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(leitor)


class Ler(Tool):
    async def execute(self, caminho: str = "", inicio: int = 1, limite: int = 0, aba: str = "", **kwargs) -> Response:
        try:
            texto = leitor.ler(caminho, inicio, limite or None, aba)
        except Exception as exc:
            texto = f"Não consegui ler {caminho}: {type(exc).__name__}: {exc}. Tente pelo código (python) ou outro formato."
        return Response(message=texto, break_loop=False)

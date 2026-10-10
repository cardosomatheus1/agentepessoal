"""POST /plugins/prospeccao/testar {"so": "<part of a test name>"}: run tests/suite.py inside the agent process."""

import importlib.util
from pathlib import Path

from helpers.api import ApiHandler, Request, Response


class Testar(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        caminho = Path(__file__).resolve().parents[1] / "tests" / "suite.py"
        spec = importlib.util.spec_from_file_location("prospeccao_testes", caminho)
        suite = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(suite)
        return await suite.Suite().rodar(str(input.get("so") or ""))

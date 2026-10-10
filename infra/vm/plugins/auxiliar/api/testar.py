"""POST /plugins/auxiliar/testar
{"so": "<part of a test name>"}  run tests/suite.py inside the agent process
{"limpar": true}                 remove every chat of the "teste_*" logins (after tests/e2e.py)"""

import importlib.util
from pathlib import Path

from helpers.api import ApiHandler, Request, Response


def _de_teste(ctx) -> bool:
    return any(str(ctx.get_data(k) or "").startswith("teste_") for k in ("dono", "whatsapp_de", "gatilhos_de"))


class Testar(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        if input.get("limpar"):
            from agent import AgentContext
            from helpers import persist_chat

            removidos = []
            for ctx in list(AgentContext.all()):
                if _de_teste(ctx):
                    ctx.reset()
                    AgentContext.remove(ctx.id)
                    persist_chat.remove_chat(ctx.id)
                    removidos.append(ctx.id)
            return {"removidos": removidos}
        caminho = Path(__file__).resolve().parents[1] / "tests" / "suite.py"
        spec = importlib.util.spec_from_file_location("auxiliar_testes", caminho)
        suite = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(suite)
        return await suite.Suite().rodar(str(input.get("so") or ""))

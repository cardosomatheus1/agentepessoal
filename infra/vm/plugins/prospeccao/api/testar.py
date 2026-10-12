"""POST /plugins/prospeccao/testar {"so": "<part of a test name>"}: run tests/suite.py in a SEPARATE process.

12/10 review: it used to run inside the agent, and the suite swaps the reviewer for an approve-all stand-in and the
clock while it runs: a live round at the same moment would have used them. Now nothing the suite does reaches the agent.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from helpers.api import ApiHandler, Request, Response

SUITE = Path(__file__).resolve().parents[1] / "tests" / "suite.py"


async def rodar_fora(so: str = "", timeout: int = 900) -> dict:
    proc = await asyncio.create_subprocess_exec(sys.executable or "/opt/venv-a0/bin/python", str(SUITE), so, "--json",
                                                cwd="/a0", env={**os.environ, "PYTHONPATH": "/a0"},
                                                stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    try:
        saida, erro = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return {"erro": f"a suíte passou de {timeout} s"}
    linha = next((l for l in reversed(saida.decode("utf-8", "replace").splitlines()) if l.startswith("{")), "")
    try:
        return json.loads(linha)
    except ValueError:
        return {"erro": erro.decode("utf-8", "replace")[-2000:] or saida.decode("utf-8", "replace")[-2000:]}


class Testar(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        return await rodar_fora(str(input.get("so") or ""))

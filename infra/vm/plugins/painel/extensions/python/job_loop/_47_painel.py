"""Light job of the live panel: reads the due sources (helpers/painel.py) and saves the panel the page shows. Runs in a
thread so the loop never waits for Meta; the guard lives in the helper module, which stays in sys.modules."""

import asyncio
import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def painel():
    caminho = RAIZ / "helpers" / "painel.py"
    antigo, mtime = sys.modules.get("painel_helper"), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location("painel_helper", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules["painel_helper"] = m
    return sys.modules["painel_helper"]


def _passo(p) -> None:
    try:
        p.passo()
    finally:
        p.ESTADO["rodando"] = False


class AtualizarPainel(Extension):
    async def execute(self, **kwargs):
        try:
            p = painel()
            if p.ESTADO["rodando"]:
                return
            p.ESTADO["rodando"] = True
            asyncio.get_running_loop().run_in_executor(None, _passo, p)
        except Exception as exc:  # never stops the job loop
            print(f"painel: {type(exc).__name__}: {exc}", flush=True)

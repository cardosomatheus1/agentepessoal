"""Wake gate: the round the gate let through ended. Without error, what its sources showed becomes the state the
next round compares against; with an error, it is dropped (the next round sees the same change and runs again)."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def portao():
    nome, caminho = "rotinas_portao", RAIZ / "helpers" / "portao.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


class PortaoFim(Extension):
    async def execute(self, data: dict | None = None, **kwargs):
        agente = self.agent
        if data is None or agente is None or getattr(agente, "number", 1) != 0:
            return
        try:
            ctx = agente.context
            uuid = ctx.get_data("_portao_pendente")
            if not uuid:
                return
            ctx.set_data("_portao_pendente", None)
            if isinstance(data.get("exception"), BaseException):
                portao().descartar(uuid)
            else:
                portao().confirmar(uuid)
        except Exception as exc:
            print(f"rotinas: portão não fechou a rodada: {type(exc).__name__}: {exc}", flush=True)

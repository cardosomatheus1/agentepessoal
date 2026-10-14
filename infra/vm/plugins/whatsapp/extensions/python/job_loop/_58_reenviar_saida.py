"""Messages the bridge did not deliver are tried again: 30 s and then 2 min after (3 tries in all, within 24 h).

The outbox and its rules are in helpers/ponte.py (SAIDA, reenviar_pendentes), tested there. The job loop runs once a
minute, so a retry due before the next pass gets its own timer.
"""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

from helpers.extension import Extension


def ponte():
    nome = "whatsapp_ponte"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "ponte.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        for estado in ("PENDENTES", "PEDIDOS"):
            if antigo is not None and hasattr(antigo, estado):
                setattr(modulo, estado, getattr(antigo, estado))
        sys.modules[nome] = modulo
    return sys.modules[nome]


class ReenviarSaida(Extension):
    async def execute(self, **kwargs):
        p = ponte()
        for r in await asyncio.to_thread(p.reenviar_pendentes):
            print(f"whatsapp: resend {r['id']}: {r['resultado']}" + (f" ({r['erro'][:150]})" if r["erro"] else ""), flush=True)
        proxima = p.proxima_saida()
        if proxima is not None and proxima - time.time() < 60:
            asyncio.create_task(p.reenviar_depois(proxima - time.time() + 1))

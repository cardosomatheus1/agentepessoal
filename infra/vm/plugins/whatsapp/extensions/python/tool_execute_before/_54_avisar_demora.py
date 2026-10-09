"""When the phone chat hands work to helpers, tell the person on the phone right away.

A voice note asking for research was answered only after the helpers finished, minutes later,
with nothing on the phone meanwhile ("travou depois do meu áudio"). The first call_subordinate or
parallel after each incoming message now sends a short "on it" notice.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

DEMORADAS = {"call_subordinate", "parallel"}
AVISO = ("🔎 Recebi. Estou pesquisando isso agora, pode levar alguns minutos; te mando o resultado aqui. "
         "Se não era isso, mande /parar e diga o que fazer.")


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


class AvisarDemora(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if not self.agent or self.agent.number != 0 or tool_name not in DEMORADAS:
            return
        ctx = self.agent.context
        destino = ctx.get_data("whatsapp_de")
        entrada = ctx.get_data("whatsapp_ultima_entrada") or 0
        if not destino or not entrada or (ctx.get_data("whatsapp_aviso_demora") or 0) >= entrada:
            return
        ctx.set_data("whatsapp_aviso_demora", entrada)  # once per incoming message
        erro = await asyncio.to_thread(ponte().enviar, destino, AVISO)
        if erro:
            print(f"whatsapp: on-it notice not delivered: {erro}", flush=True)

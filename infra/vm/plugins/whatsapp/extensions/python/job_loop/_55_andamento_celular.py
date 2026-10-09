"""While the agent works on a phone request, tell the person on the phone it is still going.

Two research requests by voice note ran 8–12 minutes with nothing on the phone ("tem alguma coisa
errada"). Now, 90 s after a phone message with no answer yet, a "working on it" notice goes out,
then a short progress line every 4 minutes until the answer is sent.
"""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

from helpers.extension import Extension

PRIMEIRO = 90
INTERVALO = 4 * 60


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


def _fazendo(ctx) -> str:
    """The progress line the chat shows (e.g. "Subagente · passo 205 · browser · 8 min")."""
    texto = str(getattr(ctx.log, "progress", "") or "").strip()
    return texto.replace("Subagente", "ajudante")[:120]


class AndamentoCelular(Extension):
    async def execute(self, **kwargs):
        from agent import AgentContext

        agora = time.time()
        for ctx in AgentContext.all():
            destino = ctx.get_data("whatsapp_de")
            entrada = ctx.get_data("whatsapp_ultima_entrada") or 0
            if not destino or not entrada or not ctx.is_running():
                continue
            ultimo = max(entrada, ctx.get_data("whatsapp_ultimo_andamento") or 0)
            primeiro = ultimo == entrada
            if agora - ultimo < (PRIMEIRO if primeiro else INTERVALO):
                continue
            ctx.set_data("whatsapp_ultimo_andamento", agora)
            minutos = max(1, round((agora - entrada) / 60))
            if primeiro:
                texto = ("⏳ Recebi e estou trabalhando nisso. Te mando o resultado aqui assim que terminar "
                         "(/parar cancela).")
            else:
                fazendo = _fazendo(ctx)
                texto = f"⏳ Ainda trabalhando no seu pedido ({minutos} min" + (f" · {fazendo}" if fazendo else "") + ")."
            erro = await asyncio.to_thread(ponte().enviar, destino, texto)
            print(f"whatsapp: progress notice to {destino} ({minutos} min): {erro or 'sent'}", flush=True)

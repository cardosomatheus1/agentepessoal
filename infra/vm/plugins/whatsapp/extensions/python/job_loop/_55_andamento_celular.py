"""While the agent works on phone requests, the person sees ONE progress message that updates itself.

Two research requests by voice note ran 8–12 minutes with nothing on the phone ("tem alguma coisa errada"): a
"working on it" notice went out 90 s after a phone message with no answer yet, then a new line every 4 minutes —
per request, so 2–3 requests in parallel sent 4–8 messages (12/10 review §6). Now each person has one progress
message listing every request still running (the bridge edits it in place on Telegram; WhatsApp gets at most one
every 4 min) and, when all are answered, it turns into "✅ Terminei". The rules are in helpers/ponte.py
(proximos_andamentos), tested there.
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


def _fazendo(ctx) -> str:
    """The progress line the chat shows (e.g. "Subagente · passo 205 · browser · 8 min")."""
    texto = str(getattr(ctx.log, "progress", "") or "").strip()
    return texto.replace("Subagente", "ajudante")[:120]


class AndamentoCelular(Extension):
    async def execute(self, **kwargs):
        from agent import AgentContext

        p = ponte()
        agora = time.time()
        por_pessoa: dict[str, list] = {}
        for ctx in AgentContext.all():
            destino = ctx.get_data("whatsapp_de")
            entrada = ctx.get_data("whatsapp_ultima_entrada") or 0
            if not destino or not entrada or not ctx.is_running():
                continue
            por_pessoa.setdefault(destino, []).append({"pedido": str(ctx.get_data("whatsapp_ultimo_pedido") or ""),
                                                       "desde": float(entrada), "fazendo": _fazendo(ctx)})
        for destino, texto, fim, n in p.proximos_andamentos(por_pessoa, p.andamento_aberto(), agora):
            erro = await asyncio.to_thread(p.andamento, destino, texto, fim, n)
            print(f"whatsapp: progress to {destino} ({'done' if fim else f'{n} request(s)'}): {erro or 'ok'}", flush=True)

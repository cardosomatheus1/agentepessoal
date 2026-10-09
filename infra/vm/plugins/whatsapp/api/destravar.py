"""Watchdog for chats stuck on "Calling LLM…" (called every minute by ponte_whatsapp).

A model call can hang without ever answering; the agent then waits forever and the person on
Telegram/WhatsApp gets nothing. A running chat whose progress is "Calling LLM" with no new step
for LIMITE seconds is nudged (the same as the UI's nudge: the step is redone) and its owner is
told. At most MAX_NUDGES per 30 minutes per chat; after that the owner is asked to /parar.
Authenticated by the bridge's shared key.
"""

import importlib.util
import secrets
import sys
import time
from pathlib import Path

from helpers.api import ApiHandler, Request, Response

CHAVE = Path("/a0/usr/whatsapp/.chave")
LIMITE = 6 * 60
MAX_NUDGES = 2


def ponte():
    nome = "whatsapp_ponte"
    caminho = Path(__file__).resolve().parents[1] / "helpers" / "ponte.py"
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


def _ultimo_passo(ctx) -> float:
    try:
        return max(float(getattr(i, "timestamp", 0) or 0) for i in ctx.log.logs[-5:])
    except ValueError:
        return 0.0


class Destravar(ApiHandler):
    @classmethod
    def requires_auth(cls) -> bool:
        return False

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def requires_api_key(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            ok = secrets.compare_digest(request.headers.get("X-Chave", ""), CHAVE.read_text().strip())
        except OSError:
            ok = False
        if not ok:
            return Response('{"erro": "sem acesso"}', status=403, mimetype="application/json")
        from agent import AgentContext

        agora, feitos = time.time(), []
        for ctx in AgentContext.all():
            if not ctx.is_running() or "Calling LLM" not in (ctx.log.progress or ""):
                continue
            parado = agora - _ultimo_passo(ctx)
            if parado < LIMITE:
                continue
            recentes = [t for t in (ctx.get_data("_destravado_em") or []) if agora - t < 1800]
            nome = ctx.name or ctx.id
            p = ponte()
            if len(recentes) >= MAX_NUDGES:
                if not ctx.get_data("_destravar_avisado"):
                    ctx.set_data("_destravar_avisado", True)
                    p.enviar(p.dono(ctx), f"⚠️ «{nome}» travou de novo esperando o modelo. Mande /parar e repita o pedido.", tipo="urgente")
                continue
            ctx.set_data("_destravado_em", recentes + [agora])
            ctx.set_data("_destravar_avisado", False)
            ctx.log.log(type="info", content=f"Passo parado há {int(parado // 60)} min esperando o modelo: refeito sozinho.")
            ctx.nudge()
            print(f"whatsapp: nudged stuck chat {ctx.id} after {int(parado)} s", flush=True)
            p.enviar(p.dono(ctx), f"⚙️ «{nome}» ficou parado {int(parado // 60)} min esperando o modelo; refiz o passo sozinho.",
                    tipo="progresso")
            feitos.append(ctx.id)
        return {"ok": True, "destravados": feitos}

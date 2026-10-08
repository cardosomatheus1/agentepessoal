"""notify_user (the agent's progress notices, e.g. "update me every 2 minutes") reaches the phone too.

Agent Zero only shows these in the web app, so a person following a task from Telegram/WhatsApp
saw nothing. Same rule as final answers: a phone chat always, any other chat when the person is
away, a scheduled task, or the "Gatilhos" chat.
"""

import asyncio
import time

from helpers.extension import Extension

AUSENTE = 5 * 60
LIMITE = 1500


def ponte():
    from pathlib import Path
    import importlib.util
    import sys

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


class AvisarCelular(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if not self.agent or tool_name != "notify_user":
            return
        args = tool_args or {}
        titulo = str(args.get("title") or "").strip()
        texto = str(args.get("message") or args.get("text") or "").strip()
        if not (titulo or texto):
            return
        ctx = self.agent.context
        p = ponte()
        destino = ctx.get_data("whatsapp_de")
        if not destino:
            try:
                from agent import AgentContextType

                tarefa = ctx.type == AgentContextType.TASK
            except Exception:
                tarefa = False
            ultima = float(ctx.get_data("_whatsapp_ultima_do_usuario") or 0)
            ausente = bool(ultima) and time.time() - ultima > AUSENTE
            if not (tarefa or ausente or ctx.get_data("avisar_sempre")):
                return
            destino = p.dono(ctx)
        mensagem = (f"🔔 *{titulo}*\n" if titulo else "🔔 ") + texto[:LIMITE]
        erro = await asyncio.to_thread(p.enviar, destino, mensagem)
        if erro:
            print(f"whatsapp: notice not delivered: {erro}", flush=True)

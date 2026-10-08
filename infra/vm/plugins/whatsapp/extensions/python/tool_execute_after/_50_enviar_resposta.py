"""The main agent's final answers go to WhatsApp.

- WhatsApp chat: every final answer goes to the person who wrote.
- Any other chat: when the person is away (no message from them for AUSENTE seconds) or it is a
  scheduled task, they get a short notice — the agent finished, or stopped to ask something.
Intermediate answers during a /goal (the goal plugin turns them into "keep going") are not sent.
"""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

from helpers.extension import Extension

AUSENTE = 5 * 60
RESUMO = 700


def carregar(nome: str, caminho: Path):
    """Load a helper by path, again when the file changed (a deploy), keeping pending state."""
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        if antigo is not None and hasattr(antigo, "PENDENTES"):
            modulo.PENDENTES = antigo.PENDENTES
        sys.modules[nome] = modulo
    return sys.modules[nome]


def ponte():
    nome = "whatsapp_ponte"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
    return carregar(nome, caminho / "helpers" / "ponte.py")


def _aviso(ctx, texto: str, tarefa: bool) -> str:
    nome = ctx.name or "conversa"
    resumo = " ".join(texto.split())
    if len(resumo) > RESUMO:
        resumo = resumo[:RESUMO].rsplit(" ", 1)[0] + "…"
    titulo = f"📋 Tarefa agendada «{nome}» terminou" if tarefa else f"💬 «{nome}»"
    return f"*{titulo}*\n\n{resumo}\n\n_(a conversa completa está no app)_"


class EnviarResposta(Extension):
    async def execute(self, response=None, tool_name: str = "", **kwargs):
        agent = self.agent
        if not agent or agent.number != 0 or tool_name != "response" or response is None:
            return
        if not getattr(response, "break_loop", False):  # a /goal still running
            return
        texto = agent.get_data("_whatsapp_resposta") or ""
        if not texto.strip():
            return
        ctx = agent.context
        try:
            from agent import AgentContextType

            tarefa = ctx.type == AgentContextType.TASK
        except Exception:
            tarefa = False

        p = ponte()
        de_whatsapp = ctx.get_data("whatsapp_de")
        if de_whatsapp:
            destino, mensagem = de_whatsapp, texto
        else:
            ultima = float(ctx.get_data("_whatsapp_ultima_do_usuario") or 0)
            ausente = bool(ultima) and time.time() - ultima > AUSENTE
            if not (tarefa or ausente):
                return
            destino, mensagem = p.dono(ctx), _aviso(ctx, texto, tarefa)
        erro = await asyncio.to_thread(p.enviar, destino, mensagem)
        if erro and de_whatsapp:
            print(f"whatsapp: answer not delivered: {erro}", flush=True)

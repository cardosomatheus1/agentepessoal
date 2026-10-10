"""The main agent's final answers go to WhatsApp.

- WhatsApp chat: every final answer goes to the person who wrote.
- Any other chat: when the person is away (no message from them for AUSENTE seconds) or it is a
  scheduled task, they get a short notice — the agent finished, or stopped to ask something.
Intermediate answers during a /goal (the goal plugin turns them into "keep going") are not sent, nor
a scheduled round whose answer starts with "SEM NOVIDADE".
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
        for estado in ("PENDENTES", "PEDIDOS"):  # waiting approvals / code requests survive
            if antigo is not None and hasattr(antigo, estado):
                setattr(modulo, estado, getattr(antigo, estado))
        sys.modules[nome] = modulo
    return sys.modules[nome]


def ponte():
    nome = "whatsapp_ponte"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
    return carregar(nome, caminho / "helpers" / "ponte.py")


# Rounds written to be read on the phone (proactive ones): sent whole, under their own name, instead of
# the cut-down "task finished" notice that points to the app.
PARA_O_CELULAR = ("🧵", "📰", "🔎", "📅", "📝", "🗓️")
LIMITE_CELULAR = 3500


def _aviso(ctx, texto: str, tarefa: bool, nome_tarefa: str = "") -> str:
    nome = ctx.name or "conversa"
    if ctx.get_data("gatilhos_de"):  # an event trigger (e.g. the Google watcher): short, read on the phone, whole
        return f"*⚡ Aviso*\n\n{texto.strip()[:LIMITE_CELULAR]}"  # fixed title: the agent renames that chat
    if tarefa and nome_tarefa.startswith(PARA_O_CELULAR):
        return f"*{nome_tarefa}*\n\n{texto.strip()[:LIMITE_CELULAR]}"
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
        p = ponte()
        nome_tarefa = p.tarefa(ctx) or ""
        tarefa = bool(nome_tarefa)
        avisos = ctx.get_data("_avisos_do_evento") or []  # notices held during an event (_52_avisar_celular)
        ctx.set_data("_avisos_do_evento", [])
        if avisos and texto.strip().upper().startswith(p.SILENCIO):  # the notices were the outcome: one message
            tipo = "urgente" if any(t == "urgente" for _, t in avisos) else "progresso"
            erro = await asyncio.to_thread(p.enviar, p.dono(ctx), "\n\n".join(m for m, _ in avisos), "", "", None, tipo)
            if erro:
                print(f"whatsapp: event notice from {ctx.id} not delivered: {erro}", flush=True)
            return
        # with a real outcome, the outcome alone goes (it covers what the held notices said)
        if (tarefa or ctx.get_data("avisar_sempre")) and texto.strip().upper().startswith(p.SILENCIO):
            # a round (or a trigger, e.g. the Google watcher) with nothing new stays quiet
            return

        de_whatsapp = ctx.get_data("whatsapp_de")
        if de_whatsapp:
            destino, mensagem = de_whatsapp, texto
        else:
            ultima = float(ctx.get_data("_whatsapp_ultima_do_usuario") or 0)
            ausente = bool(ultima) and time.time() - ultima > AUSENTE
            tarefa = tarefa or bool(ctx.get_data("avisar_sempre"))  # the "Gatilhos" chat
            if not (tarefa or ausente):
                return
            destino, mensagem = p.dono(ctx), _aviso(ctx, texto, tarefa, nome_tarefa)
        # a phone chat is a conversation (answer now); a task round or an away notice is progress, held during
        # the person's quiet hours unless it says it needs them
        urgente = p.URGENTE.match(texto) or any(t == "urgente" for _, t in avisos)
        tipo = "resposta" if de_whatsapp else ("urgente" if urgente else "progresso")
        erro = await asyncio.to_thread(p.enviar, destino, mensagem, "", "", None, tipo)
        if erro:
            print(f"whatsapp: answer from {ctx.id} not delivered: {erro}", flush=True)
        elif tarefa:
            print(f"whatsapp: scheduled task {ctx.id} result sent to {destino}", flush=True)

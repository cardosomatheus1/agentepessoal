"""20/10 (prompt-cache diagnosis): every model call says which chat, scheduled task and agent made it, so the host
proxy can log it in uso.jsonl next to the token counts (infra/operador/cache_relatorio.py reads it), key the GPT
cache per routine/chat and give a person's chat the 1-hour Claude cache. Ids and numbers only, never content.

X-A0-Conversa = the chat's context id; X-A0-Rotina = uuid of the scheduled task that runs in that chat (or in the chat
that started it, for a parallel worker); X-A0-Agente = agent number (0 = main, n = helper); X-A0-Papel = "chat" (chat
model) or "util" (utility model)."""

import re

CONVERSA, ROTINA, AGENTE, PAPEL = "X-A0-Conversa", "X-A0-Rotina", "X-A0-Agente", "X-A0-Papel"
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _pai_id(ctx) -> str:
    try:
        pid = ctx.get_output_data("parent_context_id") or ""
    except Exception:
        pid = ""
    return pid or ctx.get_data("_parallel_parent_context_id") or ctx.get_data("parent_context_id") or ""


def rotina_de(ctx, tarefas_do_contexto, buscar_contexto) -> str:
    """uuid of the scheduled task running in this chat or, for a worker chat, in the chat that started it ("" for a
    person's chat). `tarefas_do_contexto(id)` = the scheduler's tasks of a context; `buscar_contexto(id)` = AgentContext.get."""
    for _ in range(8):
        if ctx is None:
            break
        tarefas = tarefas_do_contexto(ctx.id) or []
        if tarefas:
            return str(getattr(tarefas[0], "uuid", "") or "")
        pid = _pai_id(ctx)
        ctx = buscar_contexto(pid) if pid and pid != ctx.id else None
    return ""


def cabecalhos(conversa, rotina, agente, papel: str) -> dict:
    """The X-A0-* headers, only with well-formed values (anything else is left out)."""
    out = {}
    if _ID.match(str(conversa or "")):
        out[CONVERSA] = str(conversa)
    if _ID.match(str(rotina or "")):
        out[ROTINA] = str(rotina)
    if isinstance(agente, int) and 0 <= agente < 100:
        out[AGENTE] = str(agente)
    if papel in ("chat", "util"):
        out[PAPEL] = papel
    return out


def do_agente(agent, papel: str) -> dict:
    """The headers of a call made by `agent`; {} on any surprise (never in the way of a model call)."""
    try:
        ctx = agent.context
        try:
            from agent import AgentContext
            from helpers.task_scheduler import TaskScheduler

            sched = TaskScheduler.get()
            rotina = rotina_de(ctx, sched.get_tasks_by_context_id, AgentContext.get)
        except Exception:
            rotina = ""
        return cabecalhos(ctx.id, rotina, getattr(agent, "number", None), papel)
    except Exception:
        return {}

"""Chats that start other chats: subordinates (call_subordinate) and parallel workers run in
their own contexts while the person keeps watching the chat that started them.

Agent Zero turns a message typed during a step into an "intervention" raised right after the
tool returns — before the tool's result is saved. For a subordinate that means minutes of
research thrown away and redone. While the main agent waits on one, messages are held here
and handed over once the result is in the history.
"""

import time

from agent import AgentContext, UserMessage

ESPERA = {"call_subordinate", "parallel"}
ADIADAS = "_mensagens_adiadas"


def pai(ctx) -> "AgentContext | None":
    pid = ""
    try:
        pid = ctx.get_output_data("parent_context_id") or ""
    except Exception:
        pass
    pid = pid or ctx.get_data("_parallel_parent_context_id") or ctx.get_data("parent_context_id") or ""
    return AgentContext.get(pid) if pid and pid != ctx.id else None


def raiz(ctx):
    for _ in range(8):
        p = pai(ctx)
        if p is None:
            break
        ctx = p
    return ctx


def esperando_subagente(ctx) -> bool:
    try:
        tool = ctx.agent0.loop_data.current_tool
        return bool(ctx.is_running() and tool is not None and tool.name in ESPERA)
    except Exception:
        return False


def adiar(ctx, msg) -> None:
    ctx.set_data(ADIADAS, [*(ctx.get_data(ADIADAS) or []), msg])
    passos = ctx.get_data("_subagente_passos") or 0
    minutos = int((time.time() - (ctx.get_data("_subagente_inicio") or time.time())) // 60)
    andamento = f"{passos} passos, {minutos} min até agora" if passos else f"{minutos} min até agora"
    ctx.log.log(
        type="info",
        content=(
            f"Recebi sua mensagem. O agente não travou: está esperando um subagente terminar ({andamento}). "
            "Ele lê sua mensagem assim que o resultado chegar, sem perder o trabalho feito. "
            "Para cortar agora, use **Pausar** ou **Parar**."
        ),
        finished=True,
    )


def entregar(ctx) -> bool:
    """Turn held messages into one intervention on the main agent (read at its next check)."""
    msgs = [m for m in (ctx.get_data(ADIADAS) or []) if m.message or m.attachments]
    ctx.set_data(ADIADAS, [])
    if not msgs:
        return False
    agent = ctx.agent0
    if agent.intervention is not None:
        msgs.insert(0, agent.intervention)
    agent.intervention = msgs[0] if len(msgs) == 1 else UserMessage(
        "\n\n---\n\n".join(m.message for m in msgs if m.message),
        [a for m in msgs for a in m.attachments],
        id=msgs[-1].id,
    )
    return True

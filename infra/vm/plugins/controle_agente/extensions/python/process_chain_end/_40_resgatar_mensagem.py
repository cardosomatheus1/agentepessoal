"""Deliver messages that arrived while the task was finishing.

Agent Zero reads a message typed during a task only between steps. One that lands
after the last check (final answer, memory saving) was silently kept until the next
user message. Pick it up and start a new turn with it once the task is over.
"""

import asyncio

from agent import AgentContext, UserMessage
from helpers.extension import Extension
from helpers.state_monitor_integration import mark_dirty_for_context


class ResgatarMensagem(Extension):
    async def execute(self, **kwargs):
        context = self.agent.context if self.agent else None
        if not context:
            return
        pending: list[UserMessage] = []
        agent = context.agent0
        while agent is not None:
            if agent.intervention is not None:
                pending.append(agent.intervention)
                agent.intervention = None
            agent = agent.data.get("_subordinate")
        pending = [m for m in pending if m.message or m.attachments]  # nudges are not messages
        if pending:
            asyncio.create_task(self._deliver(context, pending))

    async def _deliver(self, context: AgentContext, pending: list[UserMessage]):
        for _ in range(600):  # wait for this task to end (60 s max)
            if not context.is_running():
                break
            await asyncio.sleep(0.1)
        if len(pending) == 1:
            msg = pending[0]
        else:
            msg = UserMessage(
                "\n\n---\n\n".join(m.message for m in pending if m.message),
                [a for m in pending for a in m.attachments],
                id=pending[-1].id,
            )
        context.communicate(msg)  # new turn, or read at the next step if something started meanwhile
        mark_dirty_for_context(context.id, reason="controle_agente_mensagem_resgatada")

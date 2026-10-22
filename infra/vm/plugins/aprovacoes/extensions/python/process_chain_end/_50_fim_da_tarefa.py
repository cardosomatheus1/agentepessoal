"""The task ended: what was approved "Nesta tarefa" in this chat stops counting (helpers/revisor.py). A task that died
before reaching this point is told apart by its mark (marca_tarefa), so its approvals never pass to the next one.
22/10: an action that waited for his ok while the task went on (adiada) and that he already answered, but that the
agent never came back to, returns to the chat as a message a moment after the task ends (revisor.retomar_adiada)."""

import asyncio
import sys

from helpers.extension import Extension


class FimDaTarefa(Extension):
    async def execute(self, **kwargs):
        ctx = self.agent.context if self.agent else None
        if ctx is None:
            return
        if ctx.get_data("_aprovacoes_tarefa"):
            ctx.set_data("_aprovacoes_tarefa", None)
        rv = sys.modules.get("aprovacoes_revisor")
        pendente = rv.PENDENTES.get(ctx.id) if rv else None
        if pendente and pendente.get("adiada") and pendente.get("decisao"):
            asyncio.get_running_loop().call_later(3, rv.retomar_adiada, ctx.id)  # once this task has really stopped

"""The task ended: what was approved "Nesta tarefa" in this chat stops counting (helpers/revisor.py). A task that died
before reaching this point is told apart by its mark (marca_tarefa), so its approvals never pass to the next one."""

from helpers.extension import Extension


class FimDaTarefa(Extension):
    async def execute(self, **kwargs):
        ctx = self.agent.context if self.agent else None
        if ctx is not None and ctx.get_data("_aprovacoes_tarefa"):
            ctx.set_data("_aprovacoes_tarefa", None)

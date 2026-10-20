"""A new task (one monologue: a user turn, or one job handed to a helper) starts the step count, the failures in a row
and the results seen from zero (helpers/guardas.py). monologue() is @extensible, so this runs once per task, even
when a repairable error restarts the inner loop (monologue_start would run again then)."""

from helpers.extension import Extension

CHAVES = ("_guardas_passos", "_guardas_falhas", "_guardas_resultados", "_guardas_resultado_pendente",
          "_guardas_delegacoes")


class ZerarGuardas(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        if not self.agent:
            return
        for k in CHAVES:
            self.agent.data.pop(k, None)

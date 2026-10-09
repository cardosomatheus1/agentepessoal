"""Helpers do not open helpers of their own.

A phone question about washer-dryers went A0 → A1 → … → A7, with five helper chats researching the
same thing, 175 steps and no answer after 5 minutes. Only the main agent (A0) and its direct helper
(A1) may delegate, and one `parallel` starts at most MAX_AJUDANTES helpers.
"""

import json

from helpers.extension import Extension

NIVEL_MAXIMO = 1  # agents A0 and A1 may delegate; A2+ do the work themselves
MAX_AJUDANTES = 4


class LimiteAjudantes(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if not self.agent or tool_name not in ("call_subordinate", "parallel"):
            return
        if tool_name == "parallel":
            try:
                texto = json.dumps(tool_args or {}, ensure_ascii=False)
            except (TypeError, ValueError):
                texto = str(tool_args)
            ajudantes = texto.count("call_subordinate")
            if not ajudantes:
                return  # parallel searches/reads are fine at any level
        else:
            ajudantes = 1
        from helpers.errors import RepairableException

        if self.agent.number > NIVEL_MAXIMO:
            raise RepairableException(
                "Você já é um ajudante de um ajudante: não abra outros ajudantes (call_subordinate). Faça a pesquisa "
                "você mesmo com search_engine/browser e devolva o resultado; se faltar algo, diga o que faltou.")
        if ajudantes > MAX_AJUDANTES:
            raise RepairableException(
                f"No máximo {MAX_AJUDANTES} ajudantes de uma vez (você pediu {ajudantes}). Junte partes parecidas, "
                "dê a cada ajudante uma parte diferente (sem pesquisas repetidas) e tente de novo.")

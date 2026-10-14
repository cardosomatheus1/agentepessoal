"""A new task in a chat (a scheduled run, a new message; not a message read in the middle of a task) starts the count
of model calls from zero (chat_model_call_after/_10_contar_chamadas.py)."""

import time

from helpers.extension import Extension

CHAVE = "_limpeza_chamadas"


class ZerarChamadas(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        try:
            args = (data or {}).get("args") or ()
            agent = args[0] if args else self.agent
            kw = (data or {}).get("kwargs") or {}
            no_meio = kw.get("intervention", args[2] if len(args) > 2 else False)
            if agent is not None and not no_meio:
                agent.context.set_data(CHAVE, {"n": 0, "ultima": 0.0, "desde": time.time()})
        except Exception:
            pass

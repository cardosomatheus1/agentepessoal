"""Count the model calls that came back in each chat, and when the last one did (job_loop/_41_destravar_rotinas.py).

A round that failed before any call came back did nothing and spent nothing, so running it again cannot repeat an
action; a round whose chat sees no new call nor log item for a long time is stuck. The main loop goes through
call_chat_model_turn and others through call_chat_model: both end in this extension point, only after a call that
came back. Restarted with each new task (hist_add_user_message/start/_10_zerar_chamadas.py)."""

import time

from helpers.extension import Extension

CHAVE = "_limpeza_chamadas"  # context data; "_" keys are not saved with the chat


class ContarChamadas(Extension):
    async def execute(self, **kwargs):
        try:
            ctx = self.agent.context
            antes = ctx.get_data(CHAVE) or {}
            ctx.set_data(CHAVE, {"n": int(antes.get("n") or 0) + 1, "ultima": time.time(), "desde": antes.get("desde")})
        except Exception:
            pass

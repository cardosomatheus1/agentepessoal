"""Remember when the person last wrote in each chat (to know whether they are still around)."""

import time

from helpers.extension import Extension


class HoraDaMensagem(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        try:
            args = (data or {}).get("args") or ()
            agent = args[0] if args else None
            if agent is not None and agent.number == 0:
                agent.context.set_data("_whatsapp_ultima_do_usuario", time.time())
        except Exception:
            pass

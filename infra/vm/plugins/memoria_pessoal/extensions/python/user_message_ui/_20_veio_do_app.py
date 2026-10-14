"""Remember which messages of a chat were typed in the app (not on the phone): the operator's scripts post there as
the person, so the end-of-conversation reviewer only learns from what came through the phone bridge."""

import hashlib

from helpers.extension import Extension

MAX = 60


def marca(texto: str) -> str:  # same as helpers/conversas.py marca()
    return hashlib.sha256(" ".join(str(texto or "").split()).encode("utf-8")).hexdigest()[:16]


class VeioDoApp(Extension):
    async def execute(self, data: dict | None = None, **kwargs):
        try:
            if not self.agent or not data or not data.get("message"):
                return
            ctx = self.agent.context
            marcas = list(ctx.get_data("_memoria_do_app") or [])[-(MAX - 1):] + [marca(data["message"])]
            ctx.set_data("_memoria_do_app", marcas)
        except Exception:
            pass

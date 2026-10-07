"""Remember, per chat, who sent the latest message (from the login session)."""

from helpers.extension import Extension


class QuemFala(Extension):
    async def execute(self, data: dict | None = None, **kwargs):
        try:
            from flask import has_request_context, session

            if not has_request_context() or not self.agent:
                return
            nome = session.get("usuario_nome")
            if nome:
                self.agent.context.set_data("usuario", session.get("usuario"))
                if not self.agent.context.get_data("dono"):
                    self.agent.context.set_data("dono", session.get("usuario"))
                self.agent.context.set_data("usuario_nome", nome)
        except Exception:
            pass

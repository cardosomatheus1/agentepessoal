"""Loopback-only: reload /a0/usr/.env so login changes apply without restarting Agent Zero."""
from helpers import dotenv
from helpers.api import ApiHandler, Request, Response


class RecarregarEnv(ApiHandler):
    @classmethod
    def requires_auth(cls): return False
    @classmethod
    def requires_csrf(cls): return False
    @classmethod
    def requires_loopback(cls): return True

    async def process(self, input: dict, request: Request) -> dict | Response:
        dotenv.load_dotenv()
        from helpers import login
        return {"ok": True, "login_obrigatorio": login.is_login_required()}

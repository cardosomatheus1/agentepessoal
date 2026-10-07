"""Loopback-only: reload /a0/usr/.env and apply the per-user separation, without restarting Agent Zero."""
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
        import importlib.util
        import sys
        from pathlib import Path

        from helpers import login

        name = "login_usuarios_separacao"
        spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / "helpers" / "separacao.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        if name in sys.modules:  # already patched: swap in the new rules, the patches look them up by name
            antigo = sys.modules[name]
            for k in ("usuario_da_requisicao", "dono_contexto", "dono_projeto", "_usuario_do_socket", "_filtrar", "_proibido", "_pai_id"):
                setattr(antigo, k, getattr(m, k))
        else:
            sys.modules[name] = m
        m.aplicar()  # new code: also applies patches added since the first load
        from datetime import timedelta

        from flask import current_app

        current_app.permanent_session_lifetime = timedelta(days=400)
        current_app.config["SESSION_REFRESH_EACH_REQUEST"] = False  # see login_handler extension
        current_app.extensions.pop("login_usuarios_bloqueio", None)  # also clears failed-login locks
        return {"ok": True, "login_obrigatorio": login.is_login_required(), "separacao": True}

"""Log in any user listed in /a0/usr/usuarios.json and keep them logged in for 400 days.

Agent Zero checks one AUTH_LOGIN/AUTH_PASSWORD pair and stores its hash in the session. The
.env holds a random "master" pair (so login is required); a listed user who logs in gets that
same session marker, plus their name in session["usuario"].
"""

import importlib.util
import sys
from datetime import timedelta
from pathlib import Path

from flask import current_app, redirect, render_template_string, request, session, url_for

from helpers import login
from helpers.extension import Extension

DURACAO = timedelta(days=400)


def _mod():
    name = "login_usuarios_helpers"
    if name not in sys.modules:
        root = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
        spec = importlib.util.spec_from_file_location(name, root / "helpers" / "usuarios.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules[name] = m
        spec.loader.exec_module(m)
    return sys.modules[name]


def _pagina(erro: str = "", proximo: str = ""):
    root = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
    html = (root / "webui" / "login.html").read_text(encoding="utf-8")
    return render_template_string(html, error=erro, next=proximo)


class VariosUsuarios(Extension):
    async def execute(self, data: dict | None = None, **kwargs):
        if data is None:
            return
        u = _mod()
        if not u.carregar():
            return  # no users file: keep Agent Zero's own login
        current_app.permanent_session_lifetime = DURACAO
        proximo = request.form.get("next") if request.method == "POST" else request.args.get("next")
        proximo = proximo if (proximo or "").startswith("/") and not (proximo or "").startswith("//") else ""

        if request.method != "POST":
            data["result"] = _pagina("", proximo)
            return

        bloqueio = current_app.extensions.setdefault("login_usuarios_bloqueio", u.Bloqueio())
        ip = request.headers.get("CF-Connecting-IP") or request.remote_addr or "?"
        if bloqueio.bloqueado(ip):
            data["result"] = _pagina("Muitas tentativas erradas. Espere 15 minutos e tente de novo.", proximo)
            return
        usuario = u.verificar(request.form.get("username", ""), request.form.get("password", ""))
        if not usuario:
            bloqueio.falhou(ip)
            import asyncio
            await asyncio.sleep(1)
            data["result"] = _pagina("Usuário ou senha incorretos.", proximo)
            return
        bloqueio.ok(ip)
        session.permanent = True
        session["authentication"] = login.get_credentials_hash()
        session["usuario"] = (request.form.get("username", "").strip().lower())
        session["usuario_nome"] = usuario.get("nome") or session["usuario"].title()
        data["result"] = redirect(proximo or url_for("serve_index"))

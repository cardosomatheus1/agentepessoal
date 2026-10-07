"""Each person sees only their own chats, scheduled tasks and agents (projects).

Owner of a chat = context data "dono" (set when it is created, from the login); of a project =
.a0proj/dono.txt. Anything without an owner (from before logins existed) belongs to DONO.
Applied at runtime over Agent Zero (no core file edits):
- the state snapshot (sidebar lists + open chat), for /poll and for each WebSocket connection;
- the projects list, and project creation (records the owner);
- every HTTP API call naming a chat or project the caller does not own -> 403.
"""

import sys

DONO = "matheus"
MARCA = "_login_usuarios_separacao_v1"


def usuario_da_requisicao() -> str | None:
    try:
        from flask import has_request_context, session

        if has_request_context():
            return session.get("usuario") or None
    except Exception:
        pass
    return None


def _pai_id(ctx) -> str:
    try:
        pid = ctx.get_output_data("parent_context_id") or ""
    except Exception:
        pid = ""
    return pid or ctx.get_data("_parallel_parent_context_id") or ctx.get_data("parent_context_id") or ""


def dono_contexto(ctx) -> str:
    """Subordinate and parallel-worker chats belong to whoever owns the chat that started them."""
    try:
        from agent import AgentContext

        for _ in range(8):
            if ctx.get_data("dono"):
                return ctx.get_data("dono").lower()
            pid = _pai_id(ctx)
            pai = AgentContext.get(pid) if pid and pid != ctx.id else None
            if pai is None:
                break
            ctx = pai
    except Exception:
        pass
    return DONO


def dono_projeto(nome: str) -> str:
    try:
        from helpers import projects

        with open(projects.get_project_meta(nome, "dono.txt"), encoding="utf-8") as f:
            return (f.read().strip() or DONO).lower()
    except Exception:
        return DONO


def _usuario_do_socket(identidade) -> str | None:
    try:
        from helpers.state_monitor import get_state_monitor

        manager = get_state_monitor()._manager
        u = manager.sid_to_user.get(identidade) if manager else None
        return None if not u or u == "single_user" else u
    except Exception:
        return None


def _filtrar(snapshot: dict, usuario: str | None) -> dict:
    from agent import AgentContext

    def meu(cid):
        ctx = AgentContext.get(cid) if cid else None
        return ctx is not None and usuario is not None and dono_contexto(ctx) == usuario

    for chave in ("contexts", "tasks"):
        lista = snapshot.get(chave)
        if isinstance(lista, list):
            snapshot[chave] = [c for c in lista if meu(c.get("id") or c.get("context_id"))]
    if snapshot.get("context") and not meu(snapshot["context"]):
        snapshot.update({"context": "", "deselect_chat": True, "logs": [], "log_guid": "",
                         "log_version": 0, "log_progress": 0, "log_progress_active": False, "paused": False})
    return snapshot


def _envolver_snapshot(original):
    def wrapper(*args, **kwargs):
        usuario = usuario_da_requisicao()
        if usuario is None:  # WebSocket push: find the connection in the caller's frame
            identidade = sys._getframe(1).f_locals.get("identity")
            usuario = _usuario_do_socket(identidade) if identidade else None

        async def run():
            return _filtrar(await original(*args, **kwargs), usuario)

        return run()

    wrapper.__wrapped__ = original
    return wrapper


def _contexto_vazio() -> None:
    """An API call without a chat id used the server's first chat, whoever owned it: send it to
    the caller's own first chat, or a new one."""
    from helpers import context_utils

    if getattr(context_utils, MARCA, False):
        return
    original = context_utils.use_context

    def use_context(lock, ctxid, create_if_not_exists=True):
        usuario = usuario_da_requisicao()
        if not ctxid and usuario:
            from agent import AgentContext

            meus = [c for c in AgentContext.all() if dono_contexto(c) == usuario and not _pai_id(c)]
            if meus:
                AgentContext.use(meus[0].id)
                return meus[0]
            ctxid = AgentContext.generate_id()
        return original(lock, ctxid, create_if_not_exists)

    context_utils.use_context = use_context
    setattr(context_utils, MARCA, True)


def aplicar() -> None:
    from helpers import api, projects, state_monitor, state_snapshot

    _contexto_vazio()
    if getattr(state_snapshot, MARCA, False):
        return

    original = state_snapshot.build_snapshot_from_request
    envolvido = _envolver_snapshot(original)
    state_snapshot.build_snapshot_from_request = envolvido
    state_monitor.build_snapshot_from_request = envolvido

    lista_original = projects.get_active_projects_list

    def get_active_projects_list():
        itens = lista_original()
        u = usuario_da_requisicao()
        return itens if u is None else [p for p in itens if dono_projeto(p.get("name", "")) == u]

    projects.get_active_projects_list = get_active_projects_list

    criar_original = projects.create_project

    def create_project(name, data):
        nome = criar_original(name, data)
        u = usuario_da_requisicao()
        if u:
            try:
                with open(projects.get_project_meta(nome or name, "dono.txt"), "w", encoding="utf-8") as f:
                    f.write(u)
            except Exception:
                pass
        return nome

    projects.create_project = create_project

    handle_original = api.ApiHandler.handle_request

    async def handle_request(self, request):
        u = usuario_da_requisicao()
        if u is not None and _proibido(self, request, u):
            return api.Response('{"error": "sem acesso"}', status=403, mimetype="application/json")
        return await handle_original(self, request)

    api.ApiHandler.handle_request = handle_request
    setattr(state_snapshot, MARCA, True)


def _proibido(handler, request, usuario: str) -> bool:
    from agent import AgentContext

    try:
        dados = request.get_json(silent=True) if request.is_json else dict(request.form or {})
    except Exception:
        dados = {}
    if not isinstance(dados, dict):
        return False
    for chave in ("context", "ctxid", "context_id"):
        cid = dados.get(chave)
        if isinstance(cid, str) and cid:
            ctx = AgentContext.get(cid)
            if ctx is not None and dono_contexto(ctx) != usuario:
                return True
    if type(handler).__name__ == "Projects" and dados.get("action") not in ("list", "list_options", "create", "clone"):
        projeto = dados.get("project") if isinstance(dados.get("project"), dict) else {}
        nome = dados.get("name") or projeto.get("name")
        if isinstance(nome, str) and nome and dono_projeto(nome) != usuario:
            return True
    return False

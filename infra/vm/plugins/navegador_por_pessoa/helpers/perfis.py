"""Pick the browser runtime (Chromium + profile) by the owner of the chat, not one for everybody."""

import sys
import threading

DONO_DO_PERFIL_COMPARTILHADO = "matheus"
_runtimes: dict[str, object] = {}
_lock = threading.RLock()


def dono(context_id: str) -> str:
    try:
        from agent import AgentContext

        ctx = AgentContext.get(context_id)
        if ctx is None:
            return ""
        sep = sys.modules.get("login_usuarios_separacao")
        if sep is not None:
            return (sep.dono_contexto(ctx) or "").lower()
        return (ctx.get_data("dono") or "").lower()
    except Exception:
        return ""


def runtime_da_pessoa(login: str, modulo):
    with _lock:
        rt = _runtimes.get(login)
        if rt is None:
            rt = modulo.BrowserRuntime(f"pessoa_{login}")
            _runtimes[login] = rt
        return rt


def aplicar() -> bool:
    """Wrap BrowserRuntimeSession.__init__ once; every caller (tool, WebUI, prompts) goes through it."""
    from plugins._browser.helpers import runtime as modulo

    classe = modulo.BrowserRuntimeSession
    if getattr(classe, "_por_pessoa", False):
        return False
    original = classe.__init__

    def __init__(self, context_id, runtime):
        login = dono(str(context_id))
        if login and login != DONO_DO_PERFIL_COMPARTILHADO:
            runtime = runtime_da_pessoa(login, modulo)
        original(self, context_id, runtime)

    classe.__init__ = __init__
    classe._por_pessoa = True
    # sessions cached before the patch keep the old runtime: drop the ones that belong to someone else
    with modulo._runtime_lock:
        for cid in list(modulo._runtimes):
            login = dono(cid)
            if login and login != DONO_DO_PERFIL_COMPARTILHADO:
                modulo._runtimes.pop(cid, None)
    return True

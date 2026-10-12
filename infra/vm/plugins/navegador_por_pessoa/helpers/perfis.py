"""Pick the browser runtime (Chromium + profile) by the owner of the chat, not one for everybody; keep the profiles
(the logins of Instagram, Google, Meta) outside the container's own layer."""

import os
import sys
import threading
import time
from pathlib import Path

DONO_DO_PERFIL_COMPARTILHADO = "matheus"
_runtimes: dict[str, object] = {}
_lock = threading.RLock()

# 12/10 review: the profiles lived in /a0/tmp/browser/sessions, inside the container's own layer, outside the volume:
# recreating the container (new image, setup.sh) would log the agent out of everything. They now live in /a0/usr
# (the host disk, in the daily snapshot; left out of the hourly S3 sync, which they would flood) behind a symlink.
SESSOES = Path("/a0/tmp/browser/sessions")
FORA = Path("/a0/usr/navegador/sessions")


def _cmdline(pid: int) -> bytes:
    return Path(f"/proc/{pid}/cmdline").read_bytes()


def perfil_em_uso(sessoes: Path, cmdline=_cmdline) -> bool:
    """Chromium keeps SingletonLock -> '<host>-<pid>' in a profile it has open; a stale one (process gone, or the pid
    now belongs to something else after a restart) does not count."""
    for lock in sessoes.glob("*/SingletonLock"):
        try:
            pid = int(os.readlink(lock).rsplit("-", 1)[1])
            if b"chrom" in cmdline(pid).lower():
                return True
        except (OSError, ValueError, IndexError):
            continue
    return False


def guardar_perfis_fora(sessoes: Path = SESSOES, fora: Path = FORA, cmdline=_cmdline) -> str:
    """Point the profiles folder at the copy outside the container. Only when no browser has a profile open; the
    folder found in the way is kept aside (renamed), never deleted."""
    if sessoes.is_symlink():
        return "ok"
    if not fora.is_dir():
        return "sem cópia fora do contêiner"  # the move was not done yet: leave everything as it is
    if sessoes.exists():
        if perfil_em_uso(sessoes, cmdline):
            return "navegador aberto: fica para o próximo início"
        sessoes.rename(sessoes.with_name(f"sessions.antes-{time.strftime('%Y%m%d-%H%M%S')}"))
    sessoes.parent.mkdir(parents=True, exist_ok=True)
    sessoes.symlink_to(fora, target_is_directory=True)
    return "ligado"


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

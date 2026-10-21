"""Keep Agent Zero's Time Travel (version history of /a0/usr files) out of folders it cannot handle.

21/10, measured on the VM: /a0/usr/workdir had 5.5 GB and ~60k files Time Travel walks after its own exclusions.
43k of them are the Hermes/OpenClaw installs (workdir/agentes, read-only infrastructure of agent_delegates) and 12k
are copies of git repositories (aibusiness, agentepessoal-* worktrees), which have their own history. Each snapshot
ran `git add` over all of it, hit Time Travel's 20 s limit, left `index.lock` behind, and every later snapshot failed
("Unable to create … index.lock: File exists", since 20/10 20:52), while still walking the folder at every file change.

Time Travel's exclusions are fixed in plugins/_time_travel/helpers/time_travel.py (EXCLUDED_DIR_NAMES /
EXCLUDED_DIR_PATTERNS, read at each use); this adds ours to those sets at every job-loop pass (cheap, idempotent, and
again after a restart). /a0 is not edited. A lock older than LOCK_VELHO with no git writing is removed (Time Travel's
own sweep does the same after 30 minutes, but only every 6 hours)."""

import time
from pathlib import Path

from helpers.extension import Extension

PASTAS = {"agentes"}  # dir names excluded anywhere (agent_delegates' installs)
PADROES = {"agentepessoal-*", "aibusiness", "erp-saas*"}  # git repository copies
TT = Path("/a0/usr/.time_travel/workspaces")
LOCK_VELHO = 30 * 60


def aplicar(modulo) -> int:
    """Add our exclusions to Time Travel's sets; returns how many were new."""
    antes = len(modulo.EXCLUDED_DIR_NAMES) + len(modulo.EXCLUDED_DIR_PATTERNS)
    modulo.EXCLUDED_DIR_NAMES.update(PASTAS)
    modulo.EXCLUDED_DIR_PATTERNS.update(PADROES)
    return len(modulo.EXCLUDED_DIR_NAMES) + len(modulo.EXCLUDED_DIR_PATTERNS) - antes


def destravar(raiz: Path = TT, agora: float | None = None, git_rodando=None) -> list[str]:
    """Remove index.lock files older than LOCK_VELHO when no git process writes; returns the paths removed."""
    agora = time.time() if agora is None else agora
    if git_rodando is None:
        git_rodando = _git_escrevendo
    removidos = []
    for lock in raiz.glob("*/repo.git/index.lock"):
        try:
            if agora - lock.stat().st_mtime > LOCK_VELHO and not git_rodando():
                lock.unlink()
                removidos.append(str(lock))
        except OSError:
            continue
    return removidos


def _git_escrevendo() -> bool:
    """A git command that writes (add, commit, write-tree…) is running in the container."""
    for cmd in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            partes = cmd.read_bytes().split(b"\0")
        except OSError:
            continue
        if partes and partes[0].endswith(b"git") and b"cat-file" not in partes:  # cat-file: GitPython's readers
            return True
    return False


class TimeTravelLeve(Extension):
    async def execute(self, **kwargs):
        try:
            from plugins._time_travel.helpers import time_travel

            if aplicar(time_travel):
                print("limpeza: Time Travel sem as pastas agentes/ e cópias de repositórios", flush=True)
            for lock in destravar():
                print(f"limpeza: trava velha do Time Travel removida: {lock}", flush=True)
        except Exception as exc:
            print(f"limpeza: Time Travel não ajustado: {type(exc).__name__}: {exc}", flush=True)

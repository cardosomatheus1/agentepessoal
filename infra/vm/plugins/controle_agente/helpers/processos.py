"""Processes the agent started from its terminals (scripts, adb loops, games).

Agent Zero's Pause/Stop/Nudge only act on the agent's own loop; a command already
running in a terminal keeps going. These helpers find those commands (children of
the terminal shells of every agent in a chat) so we can freeze, resume or end them.
"""

import os
import signal
import threading
import time

THREAD_NAME = "controle_agente_pausa_v2"
_frozen: dict[str, set[int]] = {}  # chat id -> pids we stopped


def _agents(context):
    agent = getattr(context, "agent0", None)
    seen = set()
    while agent is not None and id(agent) not in seen:
        seen.add(id(agent))
        yield agent
        agent = agent.data.get("_subordinate")


def _shell_pids(context) -> list[int]:
    pids = []
    for agent in _agents(context):
        state = agent.get_data("_cet_state")
        for shell in (getattr(state, "shells", None) or {}).values():
            tty = getattr(getattr(shell, "session", None), "session", None)
            proc = getattr(tty, "_proc", None)
            pid = getattr(proc, "pid", None)
            if pid:
                pids.append(pid)
    return pids


def _children_map() -> dict[int, list[int]]:
    children: dict[int, list[int]] = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat") as f:
                stat = f.read()
            ppid = int(stat[stat.rfind(")") + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        children.setdefault(ppid, []).append(int(name))
    return children


def command_pids(context) -> list[int]:
    """Everything running under the agent's shells (not the shells themselves)."""
    children = _children_map()
    out, stack = [], [c for pid in _shell_pids(context) for c in children.get(pid, [])]
    while stack:
        pid = stack.pop()
        out.append(pid)
        stack.extend(children.get(pid, []))
    return out


def _signal(pids, sig) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass


def freeze(context) -> None:
    pids = command_pids(context)
    _signal(pids, signal.SIGSTOP)
    _frozen.setdefault(context.id, set()).update(pids)


def thaw(context_id: str) -> None:
    _signal(_frozen.pop(context_id, set()), signal.SIGCONT)


def end(context) -> None:
    """Stop button / nudge / chat reset: end the running commands (Ctrl+C, then kill)."""
    pids = command_pids(context) + list(_frozen.pop(context.id, set()))
    if not pids:
        return
    _signal(pids, signal.SIGCONT)
    _signal(pids, signal.SIGINT)

    def finish():
        time.sleep(2)
        _signal(pids, signal.SIGKILL)

    threading.Thread(target=finish, daemon=True).start()


def _watch() -> None:
    from agent import AgentContext
    from helpers.state_monitor_integration import mark_dirty_for_context

    last_paused: dict[str, bool] = {}
    while True:
        try:
            alive = set()
            for context in list(AgentContext.all()):
                alive.add(context.id)
                if last_paused.get(context.id, False) != bool(context.paused):
                    # /pause doesn't push new state, so an older snapshot flipped the
                    # button back and a second tap undid the pause. Push it now.
                    last_paused[context.id] = bool(context.paused)
                    mark_dirty_for_context(context.id, reason="controle_agente_pausa")
                if context.paused:
                    freeze(context)  # also catches commands started right before the pause
                elif context.id in _frozen:
                    thaw(context.id)
            for context_id in [c for c in _frozen if c not in alive]:
                thaw(context_id)
            for context_id in [c for c in last_paused if c not in alive]:
                last_paused.pop(context_id)
        except Exception as exc:  # never let the watcher die
            print(f"controle_agente: {exc}", flush=True)
        time.sleep(0.25)


def start_watcher() -> None:
    if any(t.name == THREAD_NAME for t in threading.enumerate()):
        return
    threading.Thread(target=_watch, name=THREAD_NAME, daemon=True).start()

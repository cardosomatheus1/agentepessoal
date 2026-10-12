"""A reboot (or a crash) leaves scheduled tasks marked "running" with nothing running: the scheduler then never runs
them again (10/10: the prospecting round and "fios soltos" stayed stuck after the VM reboot). Every 10 minutes, a
task that has been "running" for more than 90 minutes with no live run goes back to idle.

A recurring task that ended in "error" is never run again either (the scheduler only runs idle tasks; 11/10: the
prospecting search and the NEXOS watch died for good when the model proxy was down during a reboot). A recurring
task in error for more than ERRO_MIN minutes goes back to idle, so it runs again at its next scheduled time.

12/10: the check looked for the run only in the chat (ctx.task), but the scheduler keeps its own run (a DeferredTask
in TaskScheduler._running_deferred_tasks), so every scheduled run looked dead; and it counted the minutes from
last_run, the start of the PREVIOUS run. The search (2 runs a day) and the first execution round of the morning were
put back to idle minutes after starting, and the scheduler started them again in the same chat: 3 copies of each ran
at once and 4 «PRECISA DE VOCÊ» reached the phone. Now a run the scheduler still holds is never touched, and the
minutes count from when the task became "running" (updated_at)."""

import json
import time
from pathlib import Path

from helpers.extension import Extension

INTERVALO = 10 * 60
PRESA_MIN = 90
ERRO_MIN = 5
LOG = Path("/a0/usr/limpeza/log.jsonl")
_ultima = {"t": 0.0}


def _vivo(tarefa) -> bool:
    if tarefa is None:
        return False
    try:
        return bool(tarefa.is_alive())
    except Exception:
        return True  # cannot tell: leave it alone


def _minutos(quando, agora: float) -> float:
    return (agora - quando.timestamp()) / 60 if quando else 9999


def destravar(tarefas, rodando: dict, tarefa_do_chat, agora: float, running, error) -> list[dict]:
    """Which tasks go back to idle. `rodando`: the scheduler's live runs by task uuid; `tarefa_do_chat(id)`: the run
    of the task's chat, or None."""
    soltas = []
    for t in tarefas:
        if t.state == error and getattr(t, "schedule", None) is not None:
            m = _minutos(getattr(t, "last_run", None) or getattr(t, "updated_at", None), agora)
            if m > ERRO_MIN:
                soltas.append({"tarefa": t.uuid, "nome": t.name, "erro_min": int(m)})
            continue
        if t.state != running:
            continue
        if _vivo(rodando.get(t.uuid)) or _vivo(tarefa_do_chat(t.context_id) if t.context_id else None):
            continue
        m = _minutos(getattr(t, "updated_at", None) or getattr(t, "last_run", None), agora)
        if m > PRESA_MIN:
            soltas.append({"tarefa": t.uuid, "nome": t.name, "presa_min": int(m)})
    return soltas


class DestravarRotinas(Extension):
    async def execute(self, **kwargs):
        if time.time() - _ultima["t"] < INTERVALO:
            return
        _ultima["t"] = time.time()
        try:
            from agent import AgentContext
            from helpers.task_scheduler import TaskScheduler, TaskState

            sched = TaskScheduler.get()
            with getattr(sched, "_running_tasks_lock", None) or _SemTrava():
                rodando = dict(getattr(sched, "_running_deferred_tasks", None) or {})

            def tarefa_do_chat(cid):
                ctx = AgentContext.get(cid)
                return getattr(ctx, "task", None) if ctx else None

            soltas = destravar(sched.get_tasks(), rodando, tarefa_do_chat, time.time(), TaskState.RUNNING, TaskState.ERROR)
            for s in soltas:
                await sched.update_task(s["tarefa"], state=TaskState.IDLE)
            if soltas:
                LOG.parent.mkdir(parents=True, exist_ok=True)
                with LOG.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"em": time.time(), "rotinas_destravadas": soltas}, ensure_ascii=False) + "\n")
                print(f"limpeza: unstuck {len(soltas)} scheduled tasks", flush=True)
        except Exception as exc:
            print(f"limpeza: unstick check failed: {exc}", flush=True)


class _SemTrava:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

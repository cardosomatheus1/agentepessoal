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
minutes count from when the task became "running" (updated_at).

Also 12/10: the loop detector paused the search round's chat (it kept opening the same profile while 3 copies ran);
a paused scheduled round never moves again, since nobody presses "resume", and the next run of the same round got
stuck behind it. A scheduled round paused for more than PAUSADA_MIN minutes is resumed once; paused again within 2
hours, the run is cancelled (the round runs again at its next time) and the chat unpaused."""

import json
import time
from pathlib import Path

from helpers.extension import Extension

INTERVALO = 10 * 60
PRESA_MIN = 90
ERRO_MIN = 5
PAUSADA_MIN = 10
REPETIR_H = 2
LOG = Path("/a0/usr/limpeza/log.jsonl")
PAUSAS = Path("/a0/usr/limpeza/pausadas.json")  # module state does not survive the job loop: kept in a file
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


def _inicio_processo() -> float:
    """When this Agent Zero process started (boot time + the process start in clock ticks): no run is older."""
    try:
        import os

        with open("/proc/self/stat") as f:
            ticks = int(f.read().rsplit(")", 1)[1].split()[19])  # field 22, starttime
        with open("/proc/stat") as f:
            boot = next(int(l.split()[1]) for l in f if l.startswith("btime"))
        return boot + ticks / os.sysconf("SC_CLK_TCK")
    except Exception:
        return 0.0


def destravar(tarefas, rodando: dict, tarefa_do_chat, agora: float, running, error, pausada=None,
              pausas: dict | None = None, inicio: float = 0.0) -> list[dict]:
    """Which tasks go back to idle (or get resumed / cancelled). `rodando`: the scheduler's live runs by task uuid;
    `tarefa_do_chat(id)`: the run of the task's chat, or None; `pausada(id)`: the chat is paused; `pausas`: per task,
    when it was first seen paused and when it was last resumed (updated in place)."""
    pausas = {} if pausas is None else pausas
    soltas = []
    for t in tarefas:
        if t.state == error and getattr(t, "schedule", None) is not None:
            m = _minutos(getattr(t, "last_run", None) or getattr(t, "updated_at", None), agora)
            if m > ERRO_MIN:
                soltas.append({"tarefa": t.uuid, "nome": t.name, "erro_min": int(m)})
            continue
        if t.state != running:
            if t.uuid in pausas:
                pausas[t.uuid].pop("desde", None)  # a pause belongs to a run: the next run starts counting again
            continue
        reg = pausas.get(t.uuid) or {}
        if pausada and t.context_id and pausada(t.context_id):
            reg.setdefault("desde", agora)
            pausas[t.uuid] = reg
            m = (agora - reg["desde"]) / 60
            if m > PAUSADA_MIN:
                cancelar = agora - reg.get("retomada", 0) < REPETIR_H * 3600
                soltas.append({"tarefa": t.uuid, "nome": t.name, "pausada_min": int(m), "acao": "cancelar" if cancelar else "retomar"})
                pausas[t.uuid] = {} if cancelar else {"retomada": agora}
            continue
        reg.pop("desde", None)
        if reg:
            pausas[t.uuid] = reg
        if _vivo(rodando.get(t.uuid)) or _vivo(tarefa_do_chat(t.context_id) if t.context_id else None):
            continue
        quando = getattr(t, "updated_at", None) or getattr(t, "last_run", None)
        m = _minutos(quando, agora)
        if m > PRESA_MIN or (inicio and quando and quando.timestamp() < inicio):
            # a run never survives a restart: marked "running" before this process started means nothing runs it
            soltas.append({"tarefa": t.uuid, "nome": t.name, "presa_min": int(m)})
    for k in [k for k, v in pausas.items() if not v.get("desde") and agora - v.get("retomada", 0) > REPETIR_H * 3600]:
        del pausas[k]
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

            def pausada(cid):
                ctx = AgentContext.get(cid)
                return bool(ctx and getattr(ctx, "paused", False))

            try:
                pausas = json.loads(PAUSAS.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pausas = {}
            tarefas = {t.uuid: t for t in sched.get_tasks()}
            soltas = destravar(tarefas.values(), rodando, tarefa_do_chat, time.time(), TaskState.RUNNING, TaskState.ERROR,
                               pausada, pausas, _inicio_processo())
            PAUSAS.parent.mkdir(parents=True, exist_ok=True)
            PAUSAS.write_text(json.dumps(pausas), encoding="utf-8")
            for s in soltas:
                ctx = AgentContext.get(tarefas[s["tarefa"]].context_id) if tarefas[s["tarefa"]].context_id else None
                if s.get("acao") == "retomar":
                    if ctx:
                        ctx.paused = False
                    continue
                if s.get("acao") == "cancelar":
                    sched.cancel_running_task(s["tarefa"])
                    if ctx:
                        ctx.paused = False
                await sched.update_task(s["tarefa"], state=TaskState.IDLE)
            if soltas:
                LOG.parent.mkdir(parents=True, exist_ok=True)
                with LOG.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"em": time.time(), "rotinas_destravadas": soltas}, ensure_ascii=False) + "\n")
                print(f"limpeza: unstuck {len(soltas)} scheduled tasks: {soltas}", flush=True)
        except Exception as exc:
            print(f"limpeza: unstick check failed: {exc}", flush=True)


class _SemTrava:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

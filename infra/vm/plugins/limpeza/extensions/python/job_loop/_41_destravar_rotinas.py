"""A reboot (or a crash) leaves scheduled tasks marked "running" with nothing running: the scheduler then never runs
them again (10/10: the prospecting round and "fios soltos" stayed stuck after the VM reboot). Every 10 minutes, a
task that has been "running" for more than 90 minutes while its chat has no live work goes back to idle.

A recurring task that ended in "error" is never run again either (the scheduler only runs idle tasks; 11/10: the
prospecting search and the NEXOS watch died for good when the model proxy was down during a reboot). A recurring
task in error for more than ERRO_MIN minutes goes back to idle, so it runs again at its next scheduled time."""

import json
import time
from pathlib import Path

from helpers.extension import Extension

INTERVALO = 10 * 60
PRESA_MIN = 90
ERRO_MIN = 5
LOG = Path("/a0/usr/limpeza/log.jsonl")
_ultima = {"t": 0.0}


class DestravarRotinas(Extension):
    async def execute(self, **kwargs):
        if time.time() - _ultima["t"] < INTERVALO:
            return
        _ultima["t"] = time.time()
        try:
            from agent import AgentContext
            from helpers.task_scheduler import TaskScheduler, TaskState

            sched = TaskScheduler.get()
            soltas = []
            for t in sched.get_tasks():
                if t.state == TaskState.ERROR and getattr(t, "schedule", None) is not None:
                    fim = getattr(t, "last_run", None) or getattr(t, "updated_at", None)
                    minutos = (time.time() - fim.timestamp()) / 60 if fim else 9999
                    if minutos > ERRO_MIN:
                        await sched.update_task(t.uuid, state=TaskState.IDLE)
                        soltas.append({"tarefa": t.uuid, "nome": t.name, "erro_min": int(minutos)})
                    continue
                if t.state != TaskState.RUNNING:
                    continue
                ctx = AgentContext.get(t.context_id) if t.context_id else None
                tarefa = getattr(ctx, "task", None) if ctx else None
                vivo = False
                try:
                    vivo = bool(tarefa and tarefa.is_alive())
                except Exception:
                    vivo = bool(tarefa)
                inicio = getattr(t, "last_run", None) or getattr(t, "updated_at", None)
                minutos = (time.time() - inicio.timestamp()) / 60 if inicio else 9999
                if not vivo and minutos > PRESA_MIN:
                    await sched.update_task(t.uuid, state=TaskState.IDLE)
                    soltas.append({"tarefa": t.uuid, "nome": t.name, "presa_min": int(minutos)})
            if soltas:
                LOG.parent.mkdir(parents=True, exist_ok=True)
                with LOG.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"em": time.time(), "rotinas_destravadas": soltas}, ensure_ascii=False) + "\n")
                print(f"limpeza: unstuck {len(soltas)} scheduled tasks", flush=True)
        except Exception as exc:
            print(f"limpeza: unstick check failed: {exc}", flush=True)

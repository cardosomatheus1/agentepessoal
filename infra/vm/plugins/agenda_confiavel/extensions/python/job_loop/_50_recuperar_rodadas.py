"""Run a scheduled round that Agent Zero's scheduler skipped because its 60 s check drifted."""

import time
from datetime import datetime, timedelta, timezone

from helpers.extension import Extension

ESPERA = 90          # give the normal tick its chance first
JANELA = 15 * 60     # older misses are not worth replaying
_feitos: set[tuple[str, str]] = set()


def _ultimo_horario(task) -> datetime | None:
    import pytz
    from crontab import CronTab

    from helpers.task_scheduler import normalize_schedule_timezone

    fuso = pytz.timezone(normalize_schedule_timezone(task.schedule.timezone))
    agora = datetime.now(timezone.utc).astimezone(fuso)
    segundos = CronTab(task.schedule.to_crontab()).previous(now=agora, default_utc=False)
    if segundos is None:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=segundos)  # previous() is negative


class RecuperarRodadas(Extension):
    async def execute(self, **kwargs):
        from helpers.task_scheduler import ScheduledTask, TaskScheduler, TaskState

        agendador = TaskScheduler.get()
        agora = datetime.now(timezone.utc)
        for task in agendador.get_tasks():
            if not isinstance(task, ScheduledTask) or task.state != TaskState.IDLE:
                continue
            try:
                previsto = _ultimo_horario(task)
            except Exception:
                continue
            if previsto is None:
                continue
            atraso = (agora - previsto).total_seconds()
            if not ESPERA < atraso < JANELA:
                continue
            ultima = task.last_run
            if ultima is not None and ultima.tzinfo is None:
                ultima = ultima.replace(tzinfo=timezone.utc)
            if ultima is not None and ultima >= previsto - timedelta(seconds=5):
                continue
            chave = (task.uuid, previsto.isoformat(timespec="minutes"))
            if chave in _feitos:
                continue
            _feitos.add(chave)
            print(f"agenda_confiavel: '{task.name}' skipped its {previsto:%H:%M} UTC round; running it now", flush=True)
            try:
                await agendador.run_task_by_uuid(task.uuid)
            except Exception as exc:
                print(f"agenda_confiavel: could not run '{task.name}': {exc}", flush=True)

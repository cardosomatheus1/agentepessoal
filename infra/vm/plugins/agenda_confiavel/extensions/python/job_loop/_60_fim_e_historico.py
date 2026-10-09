"""Scheduled tasks: keep the last 20 runs of each, and switch off a task past its end date."""

import importlib.util
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from helpers.extension import Extension


def carregar(nome: str, caminho: Path):
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        sys.modules[nome] = modulo
    return sys.modules[nome]


RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


class FimEHistorico(Extension):
    async def execute(self, **kwargs):
        from helpers.task_scheduler import ScheduledTask, TaskScheduler, TaskState

        L = carregar("agenda_limites", RAIZ / "helpers_limites.py")
        dados = L.carregar()
        agendador = TaskScheduler.get()
        agora = time.time()
        for task in agendador.get_tasks():
            if not isinstance(task, ScheduledTask):
                continue
            if task.last_run:
                try:
                    L.registrar_rodada(task.uuid, task.last_run.isoformat(), str(task.last_result or ""))
                except Exception:
                    pass
            reg = dados.get(task.uuid, {})
            if task.uuid in L.EXISTENTES or reg.get("permanente") or task.state == TaskState.DISABLED:
                continue
            criado = task.created_at if task.created_at.tzinfo else task.created_at.replace(tzinfo=timezone.utc)
            ate = reg.get("ate") or (criado.timestamp() + L.VALIDADE_PADRAO)
            if agora < ate or task.state == TaskState.RUNNING:
                continue
            try:
                await agendador.update_task(task.uuid, state=TaskState.DISABLED)
                print(f"agenda_confiavel: '{task.name}' reached its end date; disabled", flush=True)
                ponte = carregar("whatsapp_ponte", Path("/a0/usr/plugins/whatsapp/helpers/ponte.py"))
                ponte.enviar("matheus", f"📅 A tarefa agendada «{task.name}» chegou na data de fim e foi desativada. "
                             "Se quiser que continue, peça para reativar (ou deixar permanente).", tipo="progresso")
            except Exception as exc:
                print(f"agenda_confiavel: could not end '{task.name}': {exc}", flush=True)

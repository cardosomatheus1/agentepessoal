"""Scheduled tasks: keep the last 20 runs of each, and switch off a task past its end date."""

import importlib.util
import sys
import time
from pathlib import Path

from helpers.extension import Extension


def carregar(nome: str, caminho: Path):
    """Load by path, again when the file changes (a deploy takes effect without restarting the agent)."""
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_avisado = Path("/a0/usr/agenda/.limites_ilegiveis_avisado")


class FimEHistorico(Extension):
    async def execute(self, **kwargs):
        from helpers.task_scheduler import ScheduledTask, TaskScheduler, TaskState

        L = carregar("agenda_limites", RAIZ / "helpers_limites.py")
        try:
            dados = L.carregar()
            _avisado.unlink(missing_ok=True)
        except L.LimitesIlegiveis as exc:
            dados = None  # never switch a routine off when its limit cannot be read
            if not _avisado.exists():
                _avisado.touch()
                print(f"agenda_confiavel: {exc}; nenhuma rotina será desligada até o arquivo voltar", flush=True)
        agendador = TaskScheduler.get()
        tarefas = [t for t in agendador.get_tasks() if isinstance(t, ScheduledTask)]
        for task in tarefas:
            if task.last_run:
                try:
                    L.registrar_rodada(task.uuid, task.last_run.isoformat(), str(task.last_result or ""))
                except Exception:
                    pass
        for task in L.a_desligar(tarefas, dados, time.time(), TaskState.DISABLED, TaskState.RUNNING):
            try:
                await agendador.update_task(task.uuid, state=TaskState.DISABLED)
                print(f"agenda_confiavel: '{task.name}' reached its end date; disabled", flush=True)
                ponte = carregar("whatsapp_ponte", Path("/a0/usr/plugins/whatsapp/helpers/ponte.py"))
                ponte.enviar("matheus", f"📅 A tarefa agendada «{task.name}» chegou na data de fim e foi desativada. "
                             "Se quiser que continue, peça para reativar (ou deixar permanente).", tipo="progresso")
            except Exception as exc:
                print(f"agenda_confiavel: could not end '{task.name}': {exc}", flush=True)

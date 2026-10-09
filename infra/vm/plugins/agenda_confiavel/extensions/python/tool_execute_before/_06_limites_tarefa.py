"""Refuse schedules more frequent than every 10 minutes (the "every 2 minutes" game kept the VM awake)."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension


def limites():
    nome = "agenda_limites"
    if nome not in sys.modules:
        caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers_limites.py"
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        sys.modules[nome] = modulo
    return sys.modules[nome]


class LimitesTarefa(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if tool_name != "scheduler" or not tool_args:
            return
        if str(tool_args.get("action") or "") not in ("create_scheduled_task", "update_task"):
            return
        sched = tool_args.get("schedule")
        if not isinstance(sched, dict):
            return
        campos = [str(sched.get(k, "*")) for k in ("minute", "hour", "day", "month", "weekday")]
        try:
            gap = limites().menor_intervalo(" ".join(campos), str(sched.get("timezone") or tool_args.get("timezone") or "UTC"))
        except Exception:
            return
        if gap < limites().INTERVALO_MINIMO:
            from helpers.errors import RepairableException

            raise RepairableException(
                f"Tarefa agendada com intervalo de {int(gap // 60) or 1} min: o mínimo é 10 min (cada rodada acorda a VM "
                "e gasta modelo). Use um intervalo de 10 min ou mais; se o usuário precisa de algo contínuo por pouco "
                "tempo, faça dentro da conversa atual com `wait`, sem tarefa agendada.")

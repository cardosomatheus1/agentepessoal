"""A scheduled round of the main agent starts with only the previous round in the chat's history
(helpers/rodada.py). Runs after the gate (_10_portao): a skipped round (result already set to the gate's text) is not touched. Any failure leaves the history
as it was."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def rodada():
    nome, caminho = "rotinas_rodada", RAIZ / "helpers" / "rodada.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def e_tarefa(msg) -> bool:
    c = getattr(msg, "content", None)
    texto = str(c.get("user_message") or "") if isinstance(c, dict) else str(c or "")
    return texto.lstrip().startswith(("## Task", "## Context"))


def tarefa_rodando(contexto_id: str):
    from helpers.task_scheduler import ScheduledTask, TaskScheduler

    for t in TaskScheduler.get().get_tasks_by_context_id(contexto_id, only_running=True):
        if isinstance(t, ScheduledTask):
            return t
    return None


class RodadaEnxuta(Extension):
    async def execute(self, data: dict | None = None, **kwargs):
        agente = self.agent
        if data is None or agente is None or getattr(agente, "number", 1) != 0 or isinstance(data.get("result"), str):
            return
        ctx = agente.context
        msg = getattr(agente, "last_user_message", None)
        try:
            if msg is None or ctx.get_data("_rodada_enxuta_msg") == msg.id or not e_tarefa(msg):
                return
            tarefa = tarefa_rodando(ctx.id)
            if tarefa is None:
                return
            ctx.set_data("_rodada_enxuta_msg", msg.id)
            saiu = rodada().enxugar(agente.history)
            if saiu:
                ctx.log.log(type="info", content=f"Rodada nova: {saiu} rodada(s)/resumo(s) antigos saíram do histórico "
                                                 "do modelo (o registro da conversa continua inteiro).")
                print(f"rotinas: rodada de '{tarefa.name}' começa enxuta ({saiu} registros antigos fora)", flush=True)
        except Exception as exc:
            print(f"rotinas: rodada enxuta não aplicada: {type(exc).__name__}: {exc}", flush=True)

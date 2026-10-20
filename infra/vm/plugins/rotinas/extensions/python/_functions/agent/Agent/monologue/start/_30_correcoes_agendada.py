"""A scheduled round starts with the corrections Matheus approved for this routine (helpers/rotinas.py,
corrigir_agendada: the "Aplicar" of the self-assessment) appended to its task message, and is marked so that its end
(monologue/end/_20_autoavaliar.py) assesses it. The routine's prompt in the scheduler is never changed. Runs after the
gate: a round the gate skipped (result already set) is neither changed nor assessed. Any failure: the round runs as
before."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
MAX_PEDIDO = 3000  # chars of the routine's prompt kept for the assessment


def rotinas():
    nome, caminho = "rotinas_helper", RAIZ / "helpers" / "rotinas.py"
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


def anexar(msg, bloco: str) -> None:
    c = msg.content
    if isinstance(c, dict):
        msg.content = {**c, "user_message": f"{c.get('user_message') or ''}\n\n{bloco}"}
    else:
        msg.content = f"{c or ''}\n\n{bloco}"
    try:
        msg.tokens = msg.calculate_tokens()
    except Exception:
        pass


def bloco(correcoes: list) -> str:
    return "## Correções do Matheus para esta rotina (valem acima dos passos)\n" + "\n".join(f"- {c}" for c in correcoes)


class CorrecoesAgendada(Extension):
    async def execute(self, data: dict | None = None, **kwargs):
        agente = self.agent
        if data is None or agente is None or getattr(agente, "number", 1) != 0 or isinstance(data.get("result"), str):
            return
        ctx = agente.context
        msg = getattr(agente, "last_user_message", None)
        try:
            if msg is None or ctx.get_data("_correcoes_msg") == msg.id or not e_tarefa(msg):
                return
            tarefa = tarefa_rodando(ctx.id)
            if tarefa is None:
                return
            ctx.set_data("_correcoes_msg", msg.id)
            ctx.set_data("_autoavaliar", {"uuid": tarefa.uuid, "nome": tarefa.name,
                                          "pedido": str(getattr(tarefa, "prompt", "") or "")[:MAX_PEDIDO]})
            correcoes = rotinas().correcoes_agendada(tarefa.uuid)
            if correcoes:
                anexar(msg, bloco(correcoes))
                print(f"rotinas: '{tarefa.name}' roda com {len(correcoes)} correção(ões) aprovada(s)", flush=True)
        except Exception as exc:
            print(f"rotinas: correções da rotina não aplicadas: {type(exc).__name__}: {exc}", flush=True)

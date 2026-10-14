"""Wake gate (helpers/portao.py): a scheduled round with a gate in portao.json only calls the model when its cheap
source changed.

The scheduler is not extensible, but its run is `hist_add_user_message("## Task: …")` followed by
`agent.monologue()`, and monologue is. Here, once per run of the main agent in a chat whose scheduled task is running:
nothing changed → the task message leaves the history and the monologue returns "SEM NOVIDADE (portão)" without
running (the scheduler records a success and the task goes back to idle); changed → what changed is appended to the
task message and the round runs. Any failure of the gate itself lets the round run as before."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def portao():
    """helpers/portao.py, loaded again when the file changes (a deploy takes effect without restarting the agent)."""
    nome, caminho = "rotinas_portao", RAIZ / "helpers" / "portao.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def tarefa_rodando(contexto_id: str):
    """The scheduled task the scheduler is running in this chat, if any."""
    from helpers.task_scheduler import ScheduledTask, TaskScheduler

    for t in TaskScheduler.get().get_tasks_by_context_id(contexto_id, only_running=True):
        if isinstance(t, ScheduledTask):
            return t
    return None


async def chamar(ferramenta: str, argumentos: dict) -> tuple[bool, str]:
    from helpers.mcp_handler import MCPConfig

    try:
        r = await MCPConfig.get_instance().call_tool(f"google.{ferramenta}", argumentos)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    texto = "\n".join(str(getattr(c, "text", "") or "") for c in (getattr(r, "content", None) or []))
    return not getattr(r, "isError", False), texto


def texto_da_tarefa(msg) -> str:
    c = getattr(msg, "content", None)
    return str(c.get("user_message") or "") if isinstance(c, dict) else str(c or "")


def anexar(msg, bloco: str) -> None:
    """Appended at the end: the start of the message stays as the scheduler wrote it ("## Task:")."""
    c = msg.content
    if isinstance(c, dict):
        msg.content = {**c, "user_message": f"{c.get('user_message') or ''}\n\n{bloco}"}
    else:
        msg.content = f"{c or ''}\n\n{bloco}"
    try:
        msg.tokens = msg.calculate_tokens()
    except Exception:
        pass


class Portao(Extension):
    async def execute(self, data: dict | None = None, **kwargs):
        agente = self.agent
        if data is None or agente is None or getattr(agente, "number", 1) != 0:
            return  # subordinates (call_subordinate) share the chat: only the round's own agent is gated
        ctx = agente.context
        msg = getattr(agente, "last_user_message", None)
        try:
            if msg is None or ctx.get_data("_portao_msg") == msg.id:
                return
            if not texto_da_tarefa(msg).lstrip().startswith(("## Task", "## Context")):
                return
            tarefa = tarefa_rodando(ctx.id)
            if tarefa is None:
                return
            P = portao()
            cfg = P.config(tarefa.uuid)
            if not cfg:
                return
            ctx.set_data("_portao_msg", msg.id)
            decisao = await P.avaliar(tarefa.uuid, cfg, chamar)
        except Exception as exc:  # the gate never stops a round
            print(f"rotinas: portão falhou, a rodada segue normal: {type(exc).__name__}: {exc}", flush=True)
            return
        try:
            if decisao["rodar"]:
                anexar(msg, P.contexto(decisao))
                P.preparar(tarefa.uuid, decisao)
                ctx.set_data("_portao_pendente", tarefa.uuid)
                print(f"rotinas: portão de '{tarefa.name}': roda ({decisao['motivo']})", flush=True)
                return
            P.registrar_pulo(tarefa.uuid, decisao)
            P.descartar(tarefa.uuid)  # a pending state left by a cancelled round must not be confirmed by this one
            ctx.set_data("_portao_pendente", None)
            atual = agente.history.current.messages
            if atual and atual[-1] is msg:
                atual.pop()  # a skipped round leaves no unanswered prompt in the chat's history
            ctx.log.log(type="info", content="Portão: nada mudou nas fontes desta rotina desde a última rodada; "
                                             "rodada pulada sem chamar o modelo.")
            print(f"rotinas: portão de '{tarefa.name}': nada mudou, rodada pulada", flush=True)
            data["result"] = P.PULO
        except Exception as exc:
            print(f"rotinas: portão falhou depois de decidir, a rodada segue normal: {type(exc).__name__}: {exc}",
                  flush=True)

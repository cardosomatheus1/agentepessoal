"""Same tool failing in a row, and the step cap of helpers (helpers/guardas.py).

- 3rd failure in a row of the same tool (any arguments): the result carries a warning to change approach; the task
  goes on. Identical repeats are the loop detector's (_10): when it already warned, this stays quiet.
- A helper (A1+) at 80% of its cap gets a warning to wrap up; at the cap it stops and hands what it has to the agent
  that called it. The main agent (A0) has no cap; helpers of a prospecting round get a high one.
"""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("controle_agente_guardas", _RAIZ / "helpers" / "guardas.py")
guardas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guardas)


def _familia():
    name = "controle_agente_familia_v2"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, _RAIZ / "helpers" / "familia.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def nomes_raiz(ctx) -> list[str]:
    """Names of the chat that started this helper chain and of its scheduled task (a round's chat is named after it)."""
    nomes = []
    try:
        raiz = _familia().raiz(ctx)
        nomes.append(getattr(raiz, "name", "") or "")
        from helpers.task_scheduler import TaskScheduler

        nomes += [t.name for t in TaskScheduler.get().get_tasks_by_context_id(raiz.id)]
    except Exception:
        pass
    return nomes


class Guardas(Extension):
    async def execute(self, response=None, tool_name: str = "", **kwargs):
        agent = self.agent
        if not agent or response is None or tool_name in guardas.IGNORAR:
            return
        mensagem = str(getattr(response, "message", "") or "")

        falhas = guardas.Falhas(agent.data.get("_guardas_falhas"))
        n = falhas.registrar(tool_name, guardas.falhou(tool_name, mensagem))
        agent.data["_guardas_falhas"] = falhas.contagem
        if n >= guardas.FALHAS_AVISO and "⚠️ ATENÇÃO" not in mensagem and "⛔ LOOP" not in mensagem:
            response.message = mensagem = mensagem + guardas.aviso_falhas(tool_name, n)
            if n == guardas.FALHAS_AVISO:
                agent.context.log.log(
                    type="warning", heading="Ferramenta falhando",
                    content=f"{agent.agent_name}: `{tool_name}` falhou {n} vezes seguidas; avisei para mudar de abordagem.")

        limite = guardas.teto(agent.number, nomes_raiz(agent.context) if agent.number else ())
        if not limite:
            return
        passo = int(agent.data.get("_guardas_passos") or 0)
        if passo >= limite:
            response.message = guardas.parada_passos(agent.agent_name, limite, tool_name, mensagem)
            response.break_loop = True
            agent.context.log.log(
                type="warning", heading="Ajudante parado no teto de passos",
                content=f"{agent.agent_name} chegou a {passo} passos (teto {limite}) e devolveu o que tinha.")
        elif passo == guardas.passo_do_aviso(limite):
            response.message = mensagem + guardas.aviso_passos(passo, limite)

"""Catch agents that repeat the same step without progress.

A step = tool + arguments + result. Repeating one with the same result changes nothing
(seen in practice: a subordinate reloaded the same two image batches for 15+ minutes).
Steps whose result changes (game moves, growing command output) never match.

- an identical step past the warning limit: the tool result tells the agent to change course;
- past the pause limit: the chat is paused and the user sees why; any new message resumes it.
Limits (helpers/laco.py, 21/10, after Hermes and OpenClaw): reading/polling steps count apart and never pause a chat
with the person; action steps pause on the 8th in a chat, the 5th in a helper or a scheduled round; cycles warn.
"""

import hashlib
import importlib.util
import json
from pathlib import Path

from helpers.extension import Extension

_ARQ = Path(__file__).resolve().parents[3] / "helpers" / "laco.py"
_spec = importlib.util.spec_from_file_location("controle_agente_laco", _ARQ)
laco = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(laco)

JANELA = 14  # recent steps remembered per agent
IGNORAR = {"response", "wait"}


def atendida(agent) -> bool:
    """The main agent answering a person (not a helper, not a scheduled round)."""
    if getattr(agent, "number", 0):
        return False
    try:
        msg = getattr(agent, "last_user_message", None)
        c = getattr(msg, "content", None)
        texto = str(c.get("user_message") or "") if isinstance(c, dict) else str(c or "")
        return not texto.lstrip().startswith(("## Task", "## Context"))
    except Exception:
        return True


def _assinatura(tool: str, args: dict, resultado: str) -> str:
    try:
        a = json.dumps(args, sort_keys=True, default=str, ensure_ascii=False)
    except Exception:
        a = str(args)
    return hashlib.sha1(f"{tool}\x00{a}\x00{resultado.strip()}".encode("utf-8", "ignore")).hexdigest()


class DetectorLoop(Extension):
    async def execute(self, response=None, tool_name: str = "", **kwargs):
        agent = self.agent
        if not agent or response is None or tool_name in IGNORAR:
            return
        args = agent.get_data("_detector_loop_args") or {}
        sig = _assinatura(tool_name, args, str(getattr(response, "message", "") or ""))
        hist = (agent.get_data("_detector_loop_hist") or [])[-(JANELA - 1):] + [sig]
        agent.set_data("_detector_loop_hist", hist)
        n = hist.count(sig)
        avisar, pausar = laco.limites(laco.consulta(tool_name, args), atendida(agent))
        if n < avisar:
            if laco.ciclo(hist) and "🔁" not in str(response.message):
                response.message += laco.AVISO_CICLO
            return

        quem = agent.agent_name
        if pausar and n >= pausar:
            agent.set_data("_detector_loop_hist", [])  # fresh start after the user resumes
            response.message += (
                f"\n\n⛔ LOOP: esta mesma ação (`{tool_name}`, mesmos argumentos, mesmo resultado) já foi feita {n} vezes. "
                "O usuário foi avisado e a tarefa foi PAUSADA. Ao retomar, não repita: explique onde travou ou siga outro caminho."
            )
            agent.context.paused = True
            texto = (
                f"{quem} repetiu {n}× a mesma ação (`{tool_name}`) sem nenhum resultado novo, então pausei a tarefa "
                "para não gastar tempo e dinheiro à toa. Mande uma mensagem com outra instrução (isso retoma) "
                "ou toque em Resume Agent se quiser que ele tente de novo."
            )
            agent.context.log.log(type="warning", heading="Loop detectado — tarefa pausada", content=texto)
            try:
                from helpers.notification import NotificationManager, NotificationPriority, NotificationType

                NotificationManager.send_notification(
                    NotificationType.WARNING, NotificationPriority.HIGH, texto,
                    title="Agente pausado: loop", display_time=20, group="detector_loop",
                )
            except Exception:
                pass
            return

        response.message += (
            f"\n\n⚠️ ATENÇÃO: você já fez exatamente esta ação (`{tool_name}`, mesmos argumentos) e recebeu o mesmo resultado. "
            "Repetir não vai mudar nada. Mude de caminho agora: releia a página e escolha o alvo pelo nome, use outro "
            "botão, seletor, ferramenta ou código (para muitas imagens, `analisar_imagens`). Responda ao usuário só se "
            "já tentou outros caminhos ou se precisa dele. Se continuar repetindo, a tarefa será pausada."
        )
        if n == avisar:
            agent.context.log.log(
                type="warning", heading="Possível loop",
                content=f"{quem} repetiu a mesma ação (`{tool_name}`) com o mesmo resultado; avisei para mudar de estratégia.",
            )

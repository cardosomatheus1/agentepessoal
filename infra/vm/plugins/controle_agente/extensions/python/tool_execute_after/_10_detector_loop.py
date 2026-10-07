"""Catch agents that repeat the same step without progress.

A step = tool + arguments + result. Repeating one with the same result changes nothing
(seen in practice: a subordinate reloaded the same two image batches for 15+ minutes).
Steps whose result changes (game moves, growing command output) never match.

- 2nd identical step: the tool result carries a warning telling the agent to change course.
- 4th identical step: the chat is paused and the user sees why; any new message resumes it.
"""

import hashlib
import json

from helpers.extension import Extension

JANELA = 14  # recent steps remembered per agent
AVISAR = 2
PAUSAR = 4
IGNORAR = {"response", "wait"}


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
        if n < AVISAR:
            return

        quem = agent.agent_name
        if n >= PAUSAR:
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
            "Repetir não vai mudar nada. Use o que já obteve (suas notas), mude de estratégia — para muitas imagens use a "
            "ferramenta `analisar_imagens` — ou responda ao usuário explicando onde travou. Se continuar repetindo, a tarefa será pausada."
        )
        if n == AVISAR:
            agent.context.log.log(
                type="warning", heading="Possível loop",
                content=f"{quem} repetiu a mesma ação (`{tool_name}`) com o mesmo resultado; avisei para mudar de estratégia.",
            )

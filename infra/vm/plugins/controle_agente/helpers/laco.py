"""How strict the loop detector is (item 2 of docs/AUDITORIA_MATURIDADE_AGENTE.md).

Until 21/10 the 4th identical step paused the task, even in a chat with the person and even when the agent was only
re-reading a slow page. Hermes (agent/tool_guardrails.py:35-46, 84, 120-133) never stops a chat with the person (it only
warns), stops only unattended runs, keeps polling tools out of the count, and catches A,B,A,B cycles. OpenClaw
(tool-loop-detection.ts:57-59, 540, 572-597) warns at 10, blocks at 20 and gives polling its own limit.

- action steps: warn on the 2nd identical one; pause on the 8th in a chat with the person, the 5th in a helper or a
  scheduled round (nobody is watching those);
- reading/polling steps (page content, state, list, command output, waits): warn on the 5th, pause only unattended (12th);
- a cycle (two or three steps repeating in turn, twice in a row) gets a warning too.
"""

CONSULTAS_NAVEGADOR = {"content", "state", "list", "detail", "screenshot", "evaluate", "wait", "wait_for", "esperar"}
SUFIXOS_CONSULTA = ("_poll", "_status", "_get_result", "_output")


def consulta(tool: str, args) -> bool:
    """A step that only reads/waits: repeating it while something finishes is not a loop."""
    tool = (tool or "").lower()
    args = args if isinstance(args, dict) else {}
    if tool == "browser":
        return str(args.get("action") or "state").strip().lower().replace("-", "_") in CONSULTAS_NAVEGADOR
    if tool == "code_execution_tool":
        return str(args.get("runtime") or "").strip().lower() == "output"
    return tool.endswith(SUFIXOS_CONSULTA)


def limites(eh_consulta: bool, atendida: bool) -> tuple[int, int]:
    """(warn at, pause at) for identical steps; pause 0 = never."""
    if eh_consulta:
        return 5, (0 if atendida else 12)
    return 2, (8 if atendida else 5)


def ciclo(hist: list[str]) -> bool:
    """The last steps are a cycle of 2 or 3 different steps repeated twice (A,B,A,B or A,B,C,A,B,C)."""
    for k in (2, 3):
        if len(hist) >= 2 * k:
            bloco = hist[-k:]
            if hist[-2 * k:-k] == bloco and len(set(bloco)) == k:
                return True
    return False


AVISO_CICLO = ("\n\n🔁 ATENÇÃO: você está alternando as mesmas ações e voltando ao mesmo ponto. Isso não avança. Pare o "
               "vaivém: releia o objetivo e a página e tente um caminho diferente dos dois que está alternando.")

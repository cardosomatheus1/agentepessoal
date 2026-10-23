"""Hermes inside a delegate's box (caixa_delegados.py, 20/10): the installed AIAgent library with its real tools
(terminal, files, web search, browser, vision, plan) on a task the agent wrote. The box is the isolation: nothing of
the agent is mounted and its only way to the host is the relay (model + search), so the tools can be on.

Run by the box with Hermes's own Python: reads /trabalho/config.json and /trabalho/tarefa.txt, writes
/trabalho/resultado.json (the service reads it when the box exits)."""
import json
import logging
import signal
import sys
import time
from pathlib import Path

BASE = Path("/a0/usr/workdir/agentes")
TRABALHO = Path("/trabalho")
TOOLSETS = ["terminal", "file", "web", "browser", "vision", "todo"]


def escrever(dados: dict) -> None:
    (TRABALHO / "resultado.json").write_text(json.dumps(dados, ensure_ascii=False))


def esgotado(*_):
    raise TimeoutError("tempo da tarefa esgotado")


def main() -> int:
    cfg = json.loads((TRABALHO / "config.json").read_text())
    prompt = (TRABALHO / "tarefa.txt").read_text()
    limite = int(cfg.get("segundos") or 900)
    signal.signal(signal.SIGALRM, esgotado)
    signal.alarm(limite + 30)
    logging.getLogger().setLevel(logging.ERROR)
    inicio, agente, ferramentas = time.time(), None, []
    try:
        sys.path.insert(0, str(BASE / "hermes-agent"))
        from pm.environments import activate_dependencies

        activate_dependencies(BASE / "hermes-agent")
        from run_agent import AIAgent

        agente = AIAgent(
            model=cfg["modelo"], provider="relay", base_url=cfg["base_url"], api_key="relay-not-a-credential",
            api_mode=cfg.get("api_mode") or "codex_responses", enabled_toolsets=TOOLSETS, max_iterations=int(cfg.get("passos") or 80),
            quiet_mode=True, save_trajectories=False, verbose_logging=False, skip_context_files=True,
            skip_memory=True, skip_background_review=True, load_soul_identity=False, checkpoints_enabled=False,
            fallback_model={}, reasoning_config={"enabled": True, "effort": cfg.get("esforco") or "medium"},
            run_budget_seconds=limite, cwd=str(TRABALHO),
            tool_start_callback=lambda _id, nome, _args: ferramentas.append(str(nome)[:40]),
        )
        r = agente.run_conversation(user_message=prompt, system_message=cfg.get("sistema") or None)
        resposta = (r.get("final_response") or "").strip()
        escrever({"ok": bool(resposta), "motor": "hermes", "modelo": cfg["modelo"], "resposta": resposta,
                  "ferramentas": ferramentas[-200:], "segundos": round(time.time() - inicio)})
        return 0 if resposta else 1
    except BaseException as exc:  # no raw exception text: it may carry request details
        escrever({"ok": False, "motor": "hermes", "erro": type(exc).__name__, "ferramentas": ferramentas[-200:],
                  "segundos": round(time.time() - inicio)})
        return 1
    finally:
        if agente is not None:
            try:
                agente.close()
            except Exception:
                pass
        signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())

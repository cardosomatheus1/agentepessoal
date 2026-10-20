"""OpenClaw inside a delegate's box (caixa_delegados.py, 20/10): one embedded `agent exec` run with its real tools
(files, terminal, web fetch, code) on a task the agent wrote. The box is the isolation, as for Hermes. OpenClaw's own
browser needs its gateway, so the box gives it `agent-browser` on the terminal instead (the same browser Hermes uses).

Run by the box with the image's Python: reads /trabalho/config.json and /trabalho/tarefa.txt, writes
/trabalho/resultado.json."""
import json
import os
import subprocess
import time
from pathlib import Path

BASE = Path("/a0/usr/workdir/agentes")
TRABALHO = Path("/trabalho")
NODE = BASE / "runtime" / "node-v26.12.0-linux-arm64" / "bin" / "node"
OPENCLAW = BASE / "openclaw" / "lib" / "node_modules" / "openclaw" / "openclaw.mjs"
ESTADO = TRABALHO / "casa" / "openclaw"


def configuracao(cfg: dict) -> dict:
    """OpenClaw's config for this box: the relay as the only model provider, every tool but the ones that reach
    people, other sessions, schedules or a gateway; the broken built-in browser off (agent-browser on the terminal)."""
    return {
        "models": {"mode": "replace", "providers": {"relay": {
            "baseUrl": cfg["base_url"], "api": "openai-responses", "apiKey": "relay-not-a-credential",
            "models": [{"id": cfg["modelo"], "name": cfg["modelo"], "reasoning": True, "input": ["text", "image"],
                        "contextWindow": 200000, "maxTokens": 16000,
                        "compat": {"maxTokensField": "max_completion_tokens", "supportsStore": False}}]}}},
        "agents": {"defaults": {"model": {"primary": f"relay/{cfg['modelo']}", "fallbacks": []},
                                "workspace": str(TRABALHO), "skipBootstrap": True, "thinkingDefault": "low"}},
        "tools": {"profile": "full", "deny": ["group:messaging", "group:sessions", "cron", "gateway", "nodes",
                                             "browser", "computer"],
                  "exec": {"mode": "full"}, "fs": {"workspaceOnly": True}},
        "browser": {"enabled": False},
        "plugins": {"enabled": False},
        "skills": {"load": {"watch": False}},
        "env": {"shellEnv": {"enabled": False}},
        "discovery": {"mdns": {"mode": "off"}},
    }


def resultado(bruto: str, modelo: str) -> dict:
    """OpenClaw's --json output -> the box's result (the service shows only these fields to the agent)."""
    try:
        d = json.loads(bruto)
    except (ValueError, TypeError):
        return {"ok": False, "motor": "openclaw", "erro": "saída sem JSON"}
    if not isinstance(d, dict):
        return {"ok": False, "motor": "openclaw", "erro": "saída inesperada"}
    resposta = d.get("final") if isinstance(d.get("final"), str) else ""
    resumo = d.get("toolSummary") if isinstance(d.get("toolSummary"), dict) else {}
    ok = d.get("ok") is True and d.get("status") == "ok" and bool(resposta.strip())
    r = {"ok": ok, "motor": "openclaw", "modelo": str(d.get("model") or modelo), "resposta": resposta.strip(),
         "ferramentas": [str(t)[:40] for t in (resumo.get("tools") or [])][:200],
         "chamadas": resumo.get("calls"), "falhas": resumo.get("failures")}
    if not ok:
        r["erro"] = str(d.get("status") or "falhou")[:60]
    return r


def main() -> int:
    cfg = json.loads((TRABALHO / "config.json").read_text())
    limite = int(cfg.get("segundos") or 900)
    ESTADO.mkdir(parents=True, exist_ok=True)
    (ESTADO / "openclaw.json").write_text(json.dumps(configuracao(cfg)))
    tarefa = TRABALHO / "tarefa.txt"
    if cfg.get("sistema"):
        tarefa = TRABALHO / "tarefa_completa.txt"
        tarefa.write_text(cfg["sistema"] + "\n\n" + (TRABALHO / "tarefa.txt").read_text())
    env = {**os.environ, "OPENCLAW_STATE_DIR": str(ESTADO), "OPENCLAW_CONFIG_PATH": str(ESTADO / "openclaw.json")}
    inicio = time.time()
    try:
        p = subprocess.run([str(NODE), str(OPENCLAW), "agent", "exec", "--cwd", str(TRABALHO), "--json",
                            "--timeout", str(limite), "--message-file", str(tarefa)],
                           capture_output=True, timeout=limite + 60, env=env, cwd=str(TRABALHO))
        r = resultado(p.stdout.decode("utf-8", "replace"), cfg["modelo"])
        (TRABALHO / "openclaw_diagnostico.txt").write_text(p.stderr.decode("utf-8", "replace")[-20000:])
    except subprocess.TimeoutExpired:
        r = {"ok": False, "motor": "openclaw", "erro": "TimeoutError"}
    r["segundos"] = round(time.time() - inicio)
    (TRABALHO / "resultado.json").write_text(json.dumps(r, ensure_ascii=False))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

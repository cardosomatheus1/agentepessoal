"""Stop hook of the operator's sessions on this repository: what Matheus said in the turn and what the operator answered
go to the VM, where the Segundo Cérebro records them by itself (infra/vm/plugins/cerebro/helpers/trabalho.py).

21/10, Matheus: "o que falta não é você que devia adicionar, ele deveria atualizar sozinho de acordo com o que tem sido
feito". The anotação automática only read his chats with the agent; the work done with the operator never reached the
Pasta. Each Stop sends ONE small file: his new messages (origin "human" in the transcript; task notifications and tool
results are not his words) and the operator's text since the last file sent in this session (the report of what was
done). Nothing is decided here: the VM checks every item against a literal quote.

Never in the way of the session: it reads the transcript, writes the payload and hands the upload to a detached
process; any error is swallowed. Off with CEREBRO_OPERADOR=0. Long secrets-looking strings are masked before leaving."""

import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ESTADO = Path.home() / ".claude" / "cerebro_operador.json"
DESTINO = "/opt/a0/usr/segundo_cerebro/entrada"
RELATO_MAX = 6000
DELE_MAX = 2000
SEGREDO = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|"
                     r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}[A-Za-z0-9._-]*|[A-Za-z0-9+/_-]{40,})")
_LEMBRETE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)


def _mascarar(t: str) -> str:
    return SEGREDO.sub("[…]", t)


def _texto_do_usuario(d: dict) -> str:
    """His own words in a transcript entry, or ""."""
    if d.get("type") != "user" or d.get("isMeta") or d.get("isCompactSummary"):
        return ""
    origem = d.get("origin")
    if isinstance(origem, dict) and origem.get("kind") != "human":
        return ""
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list):
        if any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c):
            return ""
        c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    c = _LEMBRETE.sub("", str(c or "")).strip()
    if not c or c.startswith(("<task-notification>", "<command-", "This session is being continued")):
        return ""
    return c


def _texto_do_operador(d: dict) -> str:
    if d.get("type") != "assistant":
        return ""
    c = (d.get("message") or {}).get("content")
    if not isinstance(c, list):
        return ""
    return "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text").strip()


def novidades(linhas: list[str], ultimo: str) -> tuple[list[str], str, str]:
    """(his new messages, the operator's text, uuid of the last entry read), after the entry `ultimo`."""
    entradas = []
    for linha in linhas:
        try:
            entradas.append(json.loads(linha))
        except ValueError:
            continue
    inicio = None
    if ultimo:
        for i, d in enumerate(entradas):
            if d.get("uuid") == ultimo:
                inicio = i + 1
    if inicio is None:  # first Stop seen for this session (or a compacted one): only the current turn, never the backlog
        humanas = [i for i, d in enumerate(entradas) if _texto_do_usuario(d)]
        inicio = humanas[-1] if humanas else len(entradas)
    dele, relato, fim = [], [], ultimo
    for d in entradas[inicio:]:
        if d.get("isSidechain"):
            continue
        t = _texto_do_usuario(d)
        if t:
            dele.append(t[:DELE_MAX])
        o = _texto_do_operador(d)
        if o:
            relato.append(o)
        fim = d.get("uuid") or fim
    texto = "\n\n".join(relato)
    return [_mascarar(m) for m in dele], _mascarar(texto[-RELATO_MAX:]), fim


def _estado() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar(est: dict) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    if len(est) > 200:
        est = dict(list(est.items())[-100:])
    ESTADO.write_text(json.dumps(est), encoding="utf-8")


def enviar(payload: dict, sessao: str) -> None:
    """Hands the upload to a detached process (the session never waits on the VM)."""
    nome = f"{time.strftime('%Y%m%dT%H%M%S')}-{sessao[:8]}.json"
    b64 = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()
    cmd = f"mkdir -p {DESTINO} && echo {b64} | base64 -d > {DESTINO}/{nome}.tmp && mv {DESTINO}/{nome}.tmp {DESTINO}/{nome}"
    subprocess.Popen([sys.executable, str(RAIZ / "infra" / "operador" / "vmcmd.py"), cmd], cwd=str(RAIZ),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                     start_new_session=True)


def main() -> None:
    if os.environ.get("CEREBRO_OPERADOR", "1") == "0":
        return
    entrada = json.loads(sys.stdin.read() or "{}")
    caminho, sessao = entrada.get("transcript_path"), str(entrada.get("session_id") or "")
    if not caminho or not sessao or entrada.get("stop_hook_active"):
        return
    linhas = Path(caminho).read_text(encoding="utf-8", errors="replace").splitlines()
    est = _estado()
    dele, relato, fim = novidades(linhas, est.get(sessao, ""))
    est[sessao] = fim
    _guardar(est)
    if not dele and len(relato) < 200:  # nothing he said and no real report (a short status line)
        return
    enviar({"sessao": sessao, "login": "matheus", "dele": dele, "relato": relato, "em": time.time()}, sessao)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass

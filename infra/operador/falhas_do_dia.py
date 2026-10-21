"""The agent's own failures of the last hours, grouped, with the exact call that failed: the input of the nightly fix
session (Matheus, 21/10: "tem como ele ver a falha e se autocorrigir?" ... "pode fazer, direto no ar").

What 21/10 showed by hand, made repeatable: 55 clicks by selector failing with a wrong hint, 17 drop-downs drawn by the
site, 19 dead browsers, an argument check refusing the wait's timeout, 284 terminal calls returned at 30 s. Each group
carries a count, the chats where it happened and up to 3 real examples (arguments + start of the result), so a fix
can be tested with the call the agent really made.

Usage, from the repository root:  python3 infra/operador/falhas_do_dia.py [horas] [--json]
(reads /opt/a0/usr/chats on the VM through SSM; no live data is changed)."""

import json
import re
import sys
from pathlib import Path

# (name, pattern in a tool result). First match wins. A result with none of them is not a failure.
PADROES = [
    ("argumento recusado", r"NÃO foi executada: argumento desconhecido"),
    ("seletor sem ref", r"could not resolve selector"),
    ("ref sumiu", r"could not find reference|element is (not attached|detached)"),
    ("navegador caiu", r"Connection closed while reading from the driver|browser has been closed|Target page, context or browser has been closed"),
    ("lista feita pelo site", r"cannot select|helper-backed"),
    ("ref obrigatória", r"ref is required"),
    ("tecla desconhecida", r"Unknown key"),
    ("tempo esgotado", r"Timeout \d+ms exceeded"),
    ("terminal ainda rodando", r"Returning control to agent after \d+ seconds|might be still running"),
    ("terminal falhou", r"⟦código de saída [1-9]"),
    ("python com erro", r"Traceback \(most recent call last\)"),
    ("anexo recusado", r"Não foi possível anexar"),
    ("ferramenta falhou", r"\b[\w ]+ failed:"),
    ("erro genérico", r"^(Error|Erro)[: ]"),
]
_COMPILADOS = [(n, re.compile(p, re.I | re.M)) for n, p in PADROES]
AVISOS = [("laço", r"repetiu a mesma ação|Possível loop"), ("juiz barrou", r"Conferência antes de responder"),
          ("resposta repetida", r"Repeated response detected")]
_AVISOS = [(n, re.compile(p, re.I)) for n, p in AVISOS]
IGNORAR_ARGS = {"thoughts", "headline", "browser_snapshot", "Screenshot"}


def classificar(texto: str) -> str:
    """The failure kind of a tool result, or '' when it did not fail."""
    inicio = str(texto or "")[:1500]
    for nome, rx in _COMPILADOS:
        if rx.search(inicio):
            return nome
    return ""


def _args(kvps) -> dict:
    a = (kvps or {}).get("tool_args") if isinstance(kvps, dict) else None
    if isinstance(a, dict) and isinstance(a.get("tool_args"), dict):
        a = a["tool_args"]
    if not isinstance(a, dict):
        a = {k: v for k, v in (kvps or {}).items() if k not in ("tool_name", "_tool_name")} if isinstance(kvps, dict) else {}
    return {k: v for k, v in a.items() if k not in IGNORAR_ARGS and not str(k).startswith("_")}


def agrupar(itens: list) -> list:
    """itens: [{"chat", "tipo" (log type), "ferramenta", "args", "conteudo"}] -> groups, the biggest first:
    [{"tipo", "ferramenta", "acao", "vezes", "conversas", "exemplos": [{"chat", "args", "resultado"}]}]."""
    grupos: dict = {}
    for it in itens:
        if it.get("tipo") == "warning":
            nome = next((n for n, rx in _AVISOS if rx.search(str(it.get("conteudo") or ""))), "")
            ferramenta, acao = "(aviso)", ""
        else:
            nome = classificar(it.get("conteudo"))
            ferramenta = str(it.get("ferramenta") or "?")
            acao = str((it.get("args") or {}).get("action") or (it.get("args") or {}).get("runtime") or "")
        if not nome:
            continue
        chave = (nome, ferramenta, acao)
        g = grupos.setdefault(chave, {"tipo": nome, "ferramenta": ferramenta, "acao": acao, "vezes": 0,
                                      "conversas": [], "exemplos": []})
        g["vezes"] += 1
        if it.get("chat") not in g["conversas"]:
            g["conversas"].append(it.get("chat"))
        if len(g["exemplos"]) < 3:
            g["exemplos"].append({"chat": it.get("chat"), "args": json.dumps(it.get("args") or {}, ensure_ascii=False)[:300],
                                  "resultado": " ".join(str(it.get("conteudo") or "").split())[:400]})
    return sorted(grupos.values(), key=lambda g: (-g["vezes"], g["tipo"]))


def relatorio(grupos: list, horas: float, minimo: int = 1) -> str:
    linhas = [f"# Falhas do agente nas últimas {horas:g} h", ""]
    for g in grupos:
        if g["vezes"] < minimo:
            continue
        linhas.append(f"## {g['vezes']}× {g['tipo']} — {g['ferramenta']} {g['acao']} ({len(g['conversas'])} conversa(s))")
        for e in g["exemplos"]:
            linhas.append(f"- [{e['chat']}] args {e['args']}\n  → {e['resultado']}")
        linhas.append("")
    if len(linhas) == 2:
        linhas.append("Nenhuma falha no período.")
    return "\n".join(linhas)


# Runs on the VM (python3 on the host, which reads the chats Agent Zero writes): every log item of every chat changed in
# the window, as the items agrupar() reads.
COLETA = r'''
import json, glob, os, time, sys
horas = float(sys.argv[1])
desde = time.time() - horas * 3600
saida = []
for f in glob.glob("/opt/a0/usr/chats/*/chat.json"):
    if os.path.getmtime(f) < desde:
        continue
    try:
        d = json.load(open(f))
    except Exception:
        continue
    chat = f.split("/")[-2]
    def logs(o):
        if isinstance(o, dict):
            if isinstance(o.get("no"), int) and "type" in o:
                yield o
            for v in o.values():
                yield from logs(v)
        elif isinstance(o, list):
            for v in o:
                yield from logs(v)
    for l in logs(d):
        if l.get("type") not in ("tool", "code_exe", "warning", "error", "mcp", "browser"):
            continue
        if float(l.get("timestamp") or 0) < desde:
            continue
        kv = l.get("kvps") if isinstance(l.get("kvps"), dict) else {}
        saida.append({"chat": chat, "tipo": l["type"], "kvps": kv, "conteudo": str(l.get("content") or "")[:1500],
                      "ferramenta": kv.get("_tool_name") or kv.get("tool_name") or ("code_execution_tool" if l["type"] == "code_exe" else "")})
print(json.dumps(saida, ensure_ascii=False))
'''


def coletar(horas: float) -> list:
    import base64
    import subprocess

    codigo = base64.b64encode(COLETA.encode()).decode()
    cmd = f"echo {codigo} | base64 -d > /tmp/coleta_falhas.py && python3 /tmp/coleta_falhas.py {horas} > /tmp/coleta_falhas.json && wc -c /tmp/coleta_falhas.json && aws s3 cp /tmp/coleta_falhas.json s3://agentepessoal-backup-964862484412/operador/coleta_falhas.json >/dev/null"
    vm = Path(__file__).resolve().parent / "vmcmd.py"
    subprocess.run([sys.executable, str(vm), cmd], check=True, capture_output=True, text=True)
    destino = Path("/tmp/coleta_falhas.json")
    subprocess.run(["aws", "s3", "cp", "s3://agentepessoal-backup-964862484412/operador/coleta_falhas.json", str(destino)],
                   check=True, capture_output=True)
    brutos = json.loads(destino.read_text(encoding="utf-8"))
    return [{**b, "args": _args(b.get("kvps"))} for b in brutos]


def main(argv: list) -> int:
    horas = float(next((a for a in argv if not a.startswith("-")), 24))
    grupos = agrupar(coletar(horas))
    print(json.dumps(grupos, ensure_ascii=False, indent=1) if "--json" in argv else relatorio(grupos, horas))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

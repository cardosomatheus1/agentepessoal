"""Reading the person's own words out of a chat log (shared by the end-of-conversation reviewer and the `lembrar`
search). Checked on the VM 14/10: /a0/usr/chats/<id>/chat.json has "data" (dono, whatsapp_de, gatilhos_de...),
"output_data" (parent_context_id on helper chats) and "log" {"logs": [{no, type, content, timestamp, agentno, kvps}]},
the last 1000 items only; type "user" is what came in, "response" the agent's answers."""

import hashlib
import json
import re
from pathlib import Path

TAREFAS = Path("/a0/usr/scheduler/tasks.json")
DONO = "matheus"  # owner of chats from before logins existed (login_usuarios.separacao.DONO)

# text the phone plugin adds around his message (whatsapp/api/receber.py and the host bridge)
_SUFIXOS = ("\n\n(Ele respondeu citando ", "\n\n(leitura automática das abreviações")
_PARALELA = "[Pedido feito pelo celular enquanto"
# button follow-ups are written by code, not typed by him (whatsapp/api/receber.py _botao_*), and triggers by machines
_DE_BOTAO = ("✅ Faz pra mim", "✅ Bora", "✏️ Quero", "✅ Usar o rascunho", "⚡ Gatilho")
_tarefas = {"mtime": None, "ids": set()}


def marca(texto: str) -> str:
    return hashlib.sha256(" ".join(str(texto or "").split()).encode("utf-8")).hexdigest()[:16]


def texto_dele(conteudo: str) -> str:
    """The person's words in a "user" log item; "" when the item was not typed by them (a button, a trigger)."""
    t = str(conteudo or "")
    if t.startswith(_DE_BOTAO):
        return ""
    if t.startswith(_PARALELA) and "\nPedido:\n" in t:
        t = t.rsplit("\nPedido:\n", 1)[1]  # drop the copied main-chat lines (they include the agent's words)
    for sufixo in _SUFIXOS:
        if sufixo in t:
            t = t.split(sufixo, 1)[0]
    t = t.strip()
    return t[2:].strip() if t.startswith("🎤 ") else t


def ids_rotinas(arquivo: Path | None = None) -> set:
    """Chat ids of scheduled tasks (the scheduler runs each in a chat named by the task's id or context_id)."""
    arq = arquivo or TAREFAS
    try:
        mtime = arq.stat().st_mtime
        if _tarefas["mtime"] != (arq, mtime):
            lista = json.loads(arq.read_text(encoding="utf-8")).get("tasks", [])
            _tarefas["ids"] = {x for t in lista for x in (t.get("uuid"), t.get("context_id")) if x}
            _tarefas["mtime"] = (arq, mtime)
    except (OSError, ValueError):
        return set(_tarefas["ids"])
    return set(_tarefas["ids"])


def e_rotina(ctx_id: str, primeira: str = "", dados: dict | None = None, arquivo: Path | None = None) -> bool:
    """A scheduled round (or a trigger chat): its "user" messages are task prompts, not the person talking."""
    dados = dados or {}
    return bool(ctx_id in ids_rotinas(arquivo) or dados.get("gatilhos_de")
                or str(primeira or "").lstrip().startswith("## Task:"))


def dono(dados: dict | None) -> str:
    return str((dados or {}).get("dono") or DONO).strip().lower()


def itens(logs) -> list[dict]:
    """Log items (live LogItem objects or dicts from chat.json) as dicts, agent 0 only, user/response only."""
    saida = []
    for x in logs or []:
        get = x.get if isinstance(x, dict) else (lambda k, d=None, _x=x: getattr(_x, k, d))
        if get("agentno", 0) or get("type") not in ("user", "response"):
            continue
        kvps = get("kvps") or {}
        saida.append({"tipo": get("type"), "texto": str(get("content") or ""), "em": float(get("timestamp") or 0),
                      "no": get("no"), "pronta": get("type") == "user" or bool((kvps or {}).get("finished", True))})
    return saida


def limpar(texto: str, n: int = 0) -> str:
    t = re.sub(r"\s+", " ", str(texto or "")).strip()
    return t[:n] + "…" if n and len(t) > n else t


# tools that only read or keep memory do not make a task "of several steps"
_NAO_CONTA = {"response", "decisao", "ficha", "lembrar", "memory_save", "memory_load", "memory_delete", "memory_forget",
              "notify_user", "salvar_rotina", "me_mostre", "livro"}


def turno(logs) -> dict:
    """The last turn of a chat log: his messages in it (from the first after the previous answer), the tools used
    (any agent, helpers included, minus memory/reply tools) and the final answer."""
    lista = list(logs or [])
    get = lambda x, k, d=None: x.get(k, d) if isinstance(x, dict) else getattr(x, k, d)  # noqa: E731
    fim = next((i for i in range(len(lista) - 1, -1, -1)
                if get(lista[i], "type") == "response" and not get(lista[i], "agentno", 0)), None)
    if fim is None:
        return {"dele": [], "ferramentas": [], "resposta": ""}
    ini = fim
    while ini > 0 and not (get(lista[ini - 1], "type") == "response" and not get(lista[ini - 1], "agentno", 0)):
        ini -= 1
    dele, ferramentas = [], []
    for x in lista[ini:fim]:
        if get(x, "type") == "user" and not get(x, "agentno", 0):
            dele.append({"tipo": "user", "texto": str(get(x, "content") or ""), "em": float(get(x, "timestamp") or 0)})
        elif get(x, "type") == "tool":
            nome = str((get(x, "kvps") or {}).get("_tool_name") or "")
            if not nome:
                achado = re.search(r"Using tool '([^']+)'", str(get(x, "heading") or ""))
                nome = achado.group(1) if achado else "?"
            if nome not in _NAO_CONTA:
                ferramentas.append(nome)
    return {"dele": dele, "ferramentas": ferramentas, "resposta": str(get(lista[fim], "content") or ""),
            "em": float(get(lista[fim], "timestamp") or 0)}

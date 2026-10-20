"""The live goal of a person's chat: their current request (literal, short), the agreed steps (done / missing) and the
rule to finish the whole request. Kept per chat in the context data (CHAVE) and shown at the END of the prompt, in the
volatile place cache_prompt already keeps (loop_data.extras_persistent: written into the history only when it changes,
and again when it falls far behind), so the start of the prompt stays the same.

A new message of the person updates it: a new request replaces the goal (and clears the steps); a status question
("continua?", "e aí?", "oq tá fazendo?") or a short confirmation ("pode", "sim", "faz") keeps it - those are not new
tasks (the same reading as whatsapp/_60_conversa_whatsapp.py). Machine messages in the chat ("[Conversa externa …]",
buttons, triggers) keep it too.

Only for the chats of a person (the phone and the app, Matheus and guests): not in scheduled rounds, triggers or
helpers (agent.number > 0).

Ideas: Cline "Focus Chain" (todo list re-injected every few messages and kept after auto-compact), Claude Code todo
list, Hermes/OpenClaw /goal.
"""

import json
import re
import time
import unicodedata
from pathlib import Path

CHAVE = "objetivo_vivo"  # context data: {"pedido", "msg_id", "anterior", "passos": [{"texto", "feito"}], "em"}
EXTRA = "objetivo_vivo"  # key in loop_data.extras_persistent (cache_prompt writes it into the history)
PEDIDO_MAX = 400  # characters of the literal request in the block
PASSOS_MAX = 12
PASSO_MAX = 160
TAREFAS = Path("/a0/usr/scheduler/tasks.json")
DONO = "matheus"

# what the phone plugin wraps around his message (memoria_pessoal/helpers/conversas.py, whatsapp/api/receber.py)
_SUFIXOS = ("\n\n(Ele respondeu citando ", "\n\n(leitura automática das abreviações")
_PARALELA = "[Pedido feito pelo celular enquanto"
_CORTADO = re.compile(r"^\[Reiniciei no meio do pedido anterior[^\]]*\]\s*", re.S)
_DE_MAQUINA = ("✅ ", "✏️ ", "⚡ ", "⏰ ", "🙈 ", "[Conversa externa", "[Aviso", "## Task:")

# status questions and short confirmations: they do not change the goal (accents and punctuation removed)
_ESTADO = {
    "continua", "continue", "continuar", "segue", "seguir", "prossiga", "vai", "bora", "e ai", "e entao", "e agora",
    "oq ta fazendo", "o que ta fazendo", "o que esta fazendo", "o q ta fazendo", "oq vc ta fazendo",
    "o que voce esta fazendo", "ta fazendo o que", "como esta", "como ta", "como vai", "como anda", "ta ai", "cade",
    "kd", "terminou", "ja terminou", "acabou", "ja acabou", "ja foi", "foi", "conseguiu", "deu certo", "deu",
    "andamento", "status", "novidade", "novidades", "alguma novidade", "e ai como ta", "e ai conseguiu",
    "e ai terminou", "ta indo", "ta funcionando", "ainda ta ai", "oi", "ola", "alo",
}
_CONFIRMA = {
    "sim", "s", "ss", "ok", "okay", "pode", "pode sim", "pode ir", "pode seguir", "pode continuar", "faz", "faca",
    "faz isso", "manda", "manda ver", "isso", "isso mesmo", "beleza", "blz", "fechado", "certo", "ta", "ta bom",
    "tudo bem", "show", "perfeito", "otimo", "valeu", "vlw", "obrigado", "obg", "nao", "n", "nada", "aprovo",
    "aprovado", "confirmo", "confirmado", "segue assim", "vai la", "continua ai", "segue ai", "pode fazer",
    "👍", "👌", "🙏",
}


def _plano(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s👍👌🙏]", " ", t)
    return " ".join(t.split())


def texto_dele(mensagem: str) -> str:
    """His words in a user message (without the phone plugin's wrappers); "" for machine messages."""
    t = str(mensagem or "")
    if t.lstrip().startswith(_DE_MAQUINA):
        return ""
    t = _CORTADO.sub("", t)
    if t.startswith(_PARALELA) and "\nPedido:\n" in t:
        t = t.rsplit("\nPedido:\n", 1)[1]
    for sufixo in _SUFIXOS:
        if sufixo in t:
            t = t.split(sufixo, 1)[0]
    t = t.strip()
    return t[2:].strip() if t.startswith("🎤 ") else t


def tipo(mensagem: str) -> str:
    """"pedido" (a new request: replaces the goal), "estado" (status question / continue), "confirmacao" or "maquina"."""
    t = texto_dele(mensagem)
    if not t:
        return "maquina"
    p = _plano(t)
    if not p:
        return "estado"  # "?", "??", "…"
    if p in _ESTADO:
        return "estado"
    if p in _CONFIRMA:
        return "confirmacao"
    palavras = p.split()
    if len(palavras) <= 6:
        # "e aí, conseguiu?", "pode sim, continua", "sim pode seguir"
        restos, i = [], 0
        while i < len(palavras):
            for n in (4, 3, 2, 1):
                trecho = " ".join(palavras[i:i + n])
                if len(palavras[i:i + n]) == n and (trecho in _ESTADO or trecho in _CONFIRMA):
                    i += n
                    break
            else:
                restos.append(palavras[i])
                i += 1
        if not restos:
            return "estado" if any(w in {"continua", "segue", "ai", "terminou", "conseguiu", "cade", "kd", "status"}
                                   for w in palavras) else "confirmacao"
    return "pedido"


def _curto(texto: str, limite: int) -> str:
    t = " ".join(str(texto or "").split())
    return t if len(t) <= limite else t[: limite - 1].rstrip() + "…"


def nova_mensagem(estado: dict | None, mensagem: str, msg_id: str = "", agora: float | None = None) -> dict:
    """The state after a new message of the person."""
    estado = dict(estado or {})
    if tipo(mensagem) != "pedido":
        return estado
    pendentes = [p for p in estado.get("passos") or [] if not p.get("feito")]
    anterior = estado.get("pedido") if estado.get("pedido") and pendentes else ""
    return {"pedido": _curto(texto_dele(mensagem), PEDIDO_MAX), "msg_id": msg_id or "", "anterior": anterior or "",
            "passos": [], "em": round(agora if agora is not None else time.time())}


_FEITO = re.compile(r"^\s*(?:\[[xX✓✔]\]|✅|✔️?|✓|\(x\)|feito:)\s*")
_ABERTO = re.compile(r"^\s*(?:\[\s?\]|⬜|☐|-|\*|\d+[.)])\s*")


def ler_passos(passos) -> list[dict]:
    """Steps from the tool: strings ("[x] abrir o site", "[ ] baixar") or {texto|passo, feito}."""
    saida = []
    for p in passos if isinstance(passos, list) else []:
        if isinstance(p, dict):
            texto = p.get("texto") or p.get("passo") or p.get("step") or ""
            feito = bool(p.get("feito") or p.get("done") or str(p.get("status", "")).lower() in {"feito", "done", "ok"})
        else:
            texto, feito = str(p or ""), bool(_FEITO.match(str(p or "")))
            texto = _ABERTO.sub("", _FEITO.sub("", texto), count=1)
        texto = _curto(texto, PASSO_MAX)
        if texto:
            saida.append({"texto": texto, "feito": feito})
    return saida[:PASSOS_MAX]


def com_passos(estado: dict | None, passos=None, feitos=None) -> dict:
    """The state with the steps replaced (passos) and/or marked done (feitos: numbers from 1, or step texts)."""
    estado = dict(estado or {})
    lista = ler_passos(passos) if passos is not None else [dict(p) for p in estado.get("passos") or []]
    for f in feitos if isinstance(feitos, list) else ([feitos] if feitos not in (None, "") else []):
        try:
            i = int(f) - 1
            if 0 <= i < len(lista):
                lista[i]["feito"] = True
            continue
        except (TypeError, ValueError):
            pass
        alvo = _plano(str(f))
        for p in lista:
            if alvo and alvo in _plano(p["texto"]):
                p["feito"] = True
    estado["passos"] = lista
    return estado


def bloco(estado: dict | None, dono: str = DONO, pelo_celular: bool = False) -> str:
    """The short, stable block at the end of the prompt ("" without a request). Same state -> same text (no clock)."""
    estado = estado or {}
    pedido = estado.get("pedido")
    if not pedido:
        return ""
    quem = "do Matheus" if (dono or DONO).lower() == DONO else "da pessoa"
    linhas = ["## Objetivo vivo desta conversa", f"Pedido atual dele, literal: «{pedido}»"]
    if estado.get("anterior"):
        linhas.append(f"Pedido anterior, com passos ainda abertos (vale só se o atual o continua): «{estado['anterior']}»")
    passos = estado.get("passos") or []
    if passos:
        feitos = sum(1 for p in passos if p.get("feito"))
        linhas.append(f"Passos combinados ({feitos} de {len(passos)} feitos):")
        linhas.extend(f"{i}. [{'x' if p.get('feito') else ' '}] {p['texto']}" for i, p in enumerate(passos, 1))
    else:
        linhas.append("Passos: nenhum registrado. Se o pedido tiver mais de um passo, registre-os com `passos` antes de "
                      "começar e marque cada um quando fizer.")
    linhas.append(f"Termine o pedido inteiro antes da resposta final (aviso de andamento com `notify_user` não encerra a "
                  f"tarefa). Só pare para o que é {quem} decidir: dinheiro, envio a terceiros, apagar, captcha, credencial.")
    if not pelo_celular:  # the phone chat already has this rule (whatsapp/_60_conversa_whatsapp.py)
        linhas.append("\"continua\", \"e aí?\" e \"oq tá fazendo?\" pedem o estado: responda curto o que está pronto e o "
                      "que falta, e siga o pedido atual.")
    return "\n".join(linhas)


# ---- which chats ------------------------------------------------------------------------------------------------

_tarefas = {"chave": None, "ids": set()}


def ids_rotinas(arquivo: Path | None = None) -> set:
    arq = arquivo or TAREFAS
    try:
        chave = (str(arq), arq.stat().st_mtime)
        if _tarefas["chave"] != chave:
            lista = json.loads(arq.read_text(encoding="utf-8")).get("tasks", [])
            _tarefas["ids"] = {x for t in lista for x in (t.get("uuid"), t.get("context_id")) if x}
            _tarefas["chave"] = chave
    except (OSError, ValueError, AttributeError):
        pass
    return set(_tarefas["ids"])


def conversa_de_pessoa(agent, arquivo: Path | None = None) -> bool:
    """The main agent of a chat with a person (phone or app; Matheus or a guest); not a scheduled round, a trigger
    chat or a helper."""
    if agent is None or getattr(agent, "number", 0) != 0:
        return False
    ctx = getattr(agent, "context", None)
    if ctx is None:
        return False
    tipo_ctx = getattr(ctx, "type", None)
    if tipo_ctx is not None and str(getattr(tipo_ctx, "value", tipo_ctx)).lower() not in {"user", "agentcontexttype.user"}:
        return False  # AgentContextType.TASK / BACKGROUND
    if ctx.get_data("gatilhos_de"):
        return False
    return getattr(ctx, "id", None) not in ids_rotinas(arquivo)


def dono(agent) -> str:
    ctx = getattr(agent, "context", None)
    try:
        return str(ctx.get_data("dono") or ctx.get_data("usuario") or DONO).lower()
    except Exception:
        return DONO

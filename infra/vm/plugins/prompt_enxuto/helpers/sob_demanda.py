"""Tools on demand (21/10, Hermes Agent's tool search): the model's native tool list carries only the tools the agent
uses all the time (NUCLEO); every other tool (Google and GitHub connectors, rarely used plugin tools) leaves the list
and is reached through one bridge tool, `ferramentas_extras`: `buscar` shows a tool's full description and parameters,
`usar` runs it with the same checks as a direct call.

Measured on 20/10 (a request of Matheus's phone chat to Haiku): 83 tools = 46,585 characters in every model call, the
largest single part of the prompt (the instructions were 45,812). The hidden tools are listed in the bridge's own
description, one short line each (name, what it is for, the required arguments), so the model knows they exist and can
often call `usar` at once. The list is the same from call to call (no tool comes or goes in the middle of a chat), so
the prompt cache is kept: Hermes does the same for the same reason (tools/tool_search.py: "tool_search",
"tool_describe", "tool_call" bridges; tool list capped at a small share of the context).

Ideas from Hermes Agent (MIT, NousResearch), tools/tool_search.py and agent/agent_runtime_helpers.py (fuzzy tool name
repair, the list of valid names on an unknown one)."""

import difflib
import json
import re
from pathlib import Path

DESLIGADO = Path("/a0/usr/plugins/prompt_enxuto/sem_sob_demanda")  # exists = every tool in the list again
PONTE = "ferramentas_extras"
CHAVE = "prompt_enxuto_ocultas"  # agent data: {native name: the tool's list entry}, refreshed at every model call

# used all the time (counted on the VM over 207 chats of the last 14 days, 20/10) or needed at once without a search:
# the final answer, the safety flows (2FA code, secrets) and the agent's own memory and decisions
NUCLEO = frozenset({
    "response", "code_execution_tool", "input", "browser", "text_editor", "skills_tool", "vision_load",
    "call_subordinate", "parallel", "wait", "notify_user", "search_engine", "pesquisar", "document_query",
    "memory_load", "lembrar", "decisao", "ficha", "cerebro", "fios", "iniciativa", "celular", "whatsapp_enviar",
    "pedir_codigo", "whatsapp_guardar_token", "consultar_sol", "delegar", "prospeccao", "salvar_rotina",
    "scheduler", "tarefa_limite", "conversa_externa", "contas", "goal", "ler", PONTE,
})
LINHA_MAX = 110  # characters of each hidden tool's line in the bridge description
_PALAVRA = re.compile(r"[a-z0-9áàâãéêíóôõúç]+")


def ligado() -> bool:
    try:
        return not DESLIGADO.exists()
    except OSError:
        return True


def visivel(nome: str) -> bool:
    return nome in NUCLEO


def separar(ferramentas: list, ativadas=()) -> tuple[list, dict]:
    """(the list the model gets, {native name: entry} of the hidden ones). Entries that are not plain function
    tools stay as they are. Nothing is hidden when the bridge itself is not in the list (it would be unreachable).
    `ativadas`: native names this chat asked for (conectores' `ativar`, or a connector tool already run): they stay
    in the list, otherwise the agent would activate a tool and still not see it (21/10: it looped on Gmail)."""
    ativadas = set(ativadas or ())
    nomes = {str(f.get("name") or "") for f in ferramentas or [] if isinstance(f, dict)}
    if PONTE not in nomes:
        return list(ferramentas or []), {}
    lista, ocultas = [], {}
    for f in ferramentas or []:
        nome = str(f.get("name") or "") if isinstance(f, dict) else ""
        if not nome or visivel(nome) or nome in ativadas or f.get("type", "function") != "function":
            lista.append(f)
        else:
            ocultas[nome] = f
    return lista, ocultas


def _obrigatorios(entrada: dict) -> list[str]:
    p = entrada.get("parameters") if isinstance(entrada.get("parameters"), dict) else {}
    req = p.get("required") if isinstance(p.get("required"), list) else []
    return [str(x) for x in req][:5]


def _resumo(descricao: str) -> str:
    texto = " ".join(str(descricao or "").replace("#", " ").split())
    corte = re.split(r"(?<=[.!?])\s", texto, maxsplit=1)[0]
    return corte if len(corte) <= 70 else corte[:67].rstrip() + "…"


def _opcionais(entrada: dict, n: int = 3) -> list[str]:
    p = entrada.get("parameters") if isinstance(entrada.get("parameters"), dict) else {}
    props = p.get("properties") if isinstance(p.get("properties"), dict) else {}
    return [f"{k}?" for k in list(props)[:n]]


def linha(nome: str, entrada: dict) -> str:
    """One catalog line: the required arguments, or, when none is required, the first optional ones (with "?"), so
    the model does not guess their names (21/10: it called the calendar with start_date instead of time_min)."""
    args = ", ".join(_obrigatorios(entrada) or _opcionais(entrada))
    out = f"- {nome}({args}): {_resumo(entrada.get('description', ''))}"
    return out if len(out) <= LINHA_MAX else out[:LINHA_MAX - 1].rstrip() + "…"


def _grupo(nome: str) -> str:
    m = re.match(r"^(google|github)_", nome)
    return m.group(1) if m else ""


def catalogo(ocultas: dict) -> str:
    """The hidden tools, one line each, plain plugin tools first, then each connector together."""
    nomes = sorted(ocultas, key=lambda n: (_grupo(n), n))
    return "\n".join(linha(n, ocultas[n]) for n in nomes)


def descricao_ponte(base: str, ocultas: dict) -> str:
    if not ocultas:
        return base
    return f"{base}\nDisponíveis por aqui:\n{catalogo(ocultas)}"


def com_ponte(lista: list, ocultas: dict) -> list:
    """The visible list with the bridge's description carrying the catalog."""
    saida = []
    for f in lista:
        if isinstance(f, dict) and f.get("name") == PONTE:
            f = {**f, "description": descricao_ponte(str(f.get("description") or ""), ocultas)}
        saida.append(f)
    return saida


def _palavras(texto: str) -> set[str]:
    return set(_PALAVRA.findall(str(texto or "").lower().replace("_", " ")))


def buscar(ocultas: dict, consulta: str, limite: int = 5) -> list[str]:
    """Names of the hidden tools that best match the query: an exact or close name first, then shared words in the
    name and description (Hermes ranks the same two ways)."""
    consulta = str(consulta or "").strip()
    if not consulta or not ocultas:
        return []
    exato = resolver(ocultas, consulta)
    termos = _palavras(consulta)
    pontos = []
    for nome, entrada in ocultas.items():
        no_nome = _palavras(nome)
        na_desc = _palavras(entrada.get("description", ""))
        p = 3 * len(termos & no_nome) + len(termos & na_desc)
        if p:
            pontos.append((-p, nome))
    nomes = [n for _, n in sorted(pontos)]
    if exato:
        nomes = [exato] + [n for n in nomes if n != exato]
    return nomes[:limite]


def resolver(ocultas: dict, nome: str) -> str:
    """The hidden tool meant by `nome`: exact, then ignoring case and -/_ and the connectors' hash suffix
    (google_get_events_82f4960e is found as "google_get_events" or "google.get_events"), then the closest
    name. "" when none is close enough."""
    nome = str(nome or "").strip()
    if not nome or not ocultas:
        return ""
    if nome in ocultas:
        return nome
    chave = lambda n: re.sub(r"_[0-9a-f]{8}$", "", n.lower().replace(".", "_").replace("-", "_"))  # noqa: E731
    alvo = chave(nome)
    for n in ocultas:
        if chave(n) == alvo:
            return n
    perto = difflib.get_close_matches(alvo, {chave(n): n for n in ocultas}, n=1, cutoff=0.85)
    return {chave(n): n for n in ocultas}[perto[0]] if perto else ""


def ficha(nome: str, entrada: dict, manual: str = "") -> str:
    """What `buscar` shows of one tool: its full description (the manual, when the list carried a short one) and its
    parameters."""
    descricao = manual or str(entrada.get("description") or "")
    params = json.dumps(entrada.get("parameters") or {}, ensure_ascii=False, separators=(",", ":"))
    return f"## {nome}\n{descricao.strip()}\nParâmetros (JSON Schema): {params}"


def args_validos(entrada: dict, args) -> str:
    """"" when the arguments can go to the tool, else what is wrong (in the words the model reads)."""
    if not isinstance(args, dict):
        return "`args` precisa ser um objeto JSON com os argumentos da ferramenta."
    p = entrada.get("parameters") if isinstance(entrada.get("parameters"), dict) else {}
    faltam = [str(r) for r in (p.get("required") if isinstance(p.get("required"), list) else []) if r not in args]
    if faltam:
        return "faltam os argumentos obrigatórios: " + ", ".join(faltam)
    return ""


def ativadas_nativas(originais, mapa: dict) -> set[str]:
    """Native names (google_search_gmail_messages_ad0e4d65) of the original ones (google.search_gmail_messages)."""
    inverso = {o: n for n, o in (mapa or {}).items()}
    return {inverso[o] for o in originais or () if o in inverso}

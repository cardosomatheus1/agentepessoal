"""Short summaries, in a NEW message, while a phone request runs for a long time.

20/10, Matheus: "Sinto falta de pequenos resumos durante as tarefas longas, às vezes fica mais de 60 min e não faço
ideia do que tá acontecendo, se de fato tá executando, não sei se travou." The single progress message (ponte.py,
proximos_andamentos) is edited in place on Telegram, so the phone never buzzes, and its line was technical
("ajudante · passo 205 · browser · 8 min"). Now, from 10 minutes into a phone request and then every 15 minutes, the
person gets a new message (it notifies) of at most three lines, one message for all of their running requests:

    ⏳ Ainda em «pedido curto» (23 min)
    Feito: 1–2 concrete things since the last summary
    Agora: what it is doing now  |  ⚠️ Sem avanço há 9 min (última coisa: …) · /parar cancela · /painel mostra tudo

Everything comes from the log of the request's chat and of the chats it started (helpers, parallel workers): the
small model (Luna, the cheap one the other plugins use) only rewrites those items in plain words, and a reply that
brings a number, name or link that is not in the log, or a tool name, is thrown away for the text built here by code.
A slow tool that legitimately runs (a terminal command, a wait, a page loading, a code or approval asked of the
person) reads "esperando …", not "sem avanço". A request answered leaves the summary; one that stopped with no
answer (and not by /parar) gets one last line saying so. Quiet hours and /foco hold summaries (they are dropped, not
queued: a summary from the night is worth nothing in the morning). Plain functions, tested in tests/suite.py; the
job loop (_55_andamento_celular.py) feeds them the live chats.
"""

import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ESTADO = Path("/a0/usr/whatsapp/resumos.json")  # {login: {"em", "proc", "pedidos": {ctx id: {...}}}}
SILENCIO = Path("/a0/usr/whatsapp/silencio.json")  # the bridge's (/silencio): read only here
FOCO = Path("/a0/usr/whatsapp/foco.json")  # the bridge's (/foco): read only here
SILENCIO_PADRAO = {"inicio": "23:00", "fim": "07:00"}
ACORDADO = 30 * 60  # same rule as the bridge: wrote in the last 30 min = awake
FUSO = ZoneInfo("America/Bahia")

MOSTRAR_APOS = 5 * 60    # a request younger than this is never in a summary (the "Recebi" notice covers it)
PRIMEIRO = 10 * 60       # first summary when a request has run this long
DEPOIS = 15 * 60         # then one every 15 min
PARADO = 8 * 60          # no new log item for this long, with no slow tool running: "sem avanço"
TRAVADO = 20 * 60        # this long: "parece travado"
ESPERA_LONGA = 4 * 60   # a slow step running this long is named in the summary ("esperando … há N min")
ENCERRAR = 30 * 60       # 20/10, Matheus: "pode encerrar qd travar por 30 min" (nothing new in its chats)
ENCERRAR_LENTO = 90 * 60  # a slow step (command, page) with no sign of life: a long render is not a stall
MIN_ENTRE = 5 * 60       # a stall can bring the next summary forward, never closer than this to the last one
MAX_PEDIDOS = 3          # requests listed in one message (the rest: "e mais N")
COMANDOS = "/parar cancela · /painel mostra tudo"

URL = "http://host.docker.internal:8787/openai/v1/responses"
MODELO = "openai.gpt-6-luna"
ESPERA_S = 12
MAX_EVENTOS = 12
CORTE_EVENTO = 160
CAMPO_MAX = 110

# tool -> (done, now, what a slow run of it waits for). Plain words, no tool names (the person reads these).
ROTULOS = {
    "browser": ("abriu sites no navegador", "olhando um site no navegador", "a página do navegador carregar"),
    "search_engine": ("pesquisou na internet", "pesquisando na internet", "a pesquisa na internet"),
    "pesquisar": ("pesquisou na internet", "pesquisando na internet", "a pesquisa na internet"),
    "code_execution_tool": ("rodou comandos no computador", "rodando um comando no computador",
                            "um comando no computador terminar"),
    "code_execution_remote": ("rodou comandos no computador", "rodando um comando no computador",
                              "um comando no computador terminar"),
    "terminal_isolado": ("rodou comandos no computador", "rodando um comando no computador",
                         "um comando no computador terminar"),
    "input": ("rodou comandos no computador", "rodando um comando no computador", "um comando no computador terminar"),
    "wait": ("esperou o horário combinado", "esperando o horário combinado", "o horário combinado"),
    "pedir_codigo": ("pediu um código a você", "esperando o código que pedi a você", "o código que pedi a você"),
    "document_query": ("leu documentos", "lendo um documento", "a leitura do documento"),
    "assistir_video": ("assistiu a um vídeo", "assistindo a um vídeo", "o vídeo ser analisado"),
    "videos_em_alta": ("procurou vídeos em alta", "procurando vídeos em alta", None),
    "vision_load": ("olhou imagens", "olhando imagens", None),
    "analisar_imagens": ("olhou imagens", "olhando imagens", None),
    "call_subordinate": ("passou uma parte para um ajudante", "um ajudante cuida de uma parte", None),
    "parallel": ("dividiu o trabalho em partes", "as partes rodam ao mesmo tempo", None),
    "notify_user": ("te mandou um aviso", "te mandando um aviso", None),
    "whatsapp_enviar": ("te mandou uma mensagem", "te mandando uma mensagem", None),
    "conector": ("usou uma conta conectada", "usando uma conta conectada", None),
    "prospeccao": ("mexeu na prospecção", "trabalhando na prospecção", None),
    "conteudo": ("mexeu nos conteúdos", "trabalhando nos conteúdos", None),
    "conversa_externa": ("conversou com alguém de fora", "conversando com alguém de fora", None),
    "concorrentes": ("olhou os concorrentes", "olhando os concorrentes", None),
}
MEMORIA = {"memory_save", "memory_load", "memory_delete", "memory_forget", "lembrar", "ficha", "decisao", "livro",
           "knowledge_tool", "skills_tool", "cofre_descrever"}
ROTULO_MEMORIA = ("consultou anotações", "consultando anotações", None)
ROTULO_OUTRO = ("usou uma ferramenta interna", "usando uma ferramenta interna", None)
ROTULO_APROVACAO = "a sua aprovação"
TIPOS_FERRAMENTA = {"tool", "code_exe", "browser", "mcp", "subagent"}
CALADAS = {"response", "util", "hint", "progress", "info"}  # never an event of their own (info: own notices)
PARADO_POR_ELE = "Parado pelo usuário"
ENCERRADO_SOZINHO = "Encerrado sozinho"  # the log line of an automatic stop (the person already got the message)

# words that give away the machinery (the person reads plain Portuguese)
JARGAO = re.compile(r"_|\b(tool|tools|subordinate|subagente|subagent|agent|llm|browser|terminal|code|python|json|api|"
                    r"prompt|mcp|script|search[_ ]engine|endpoint|token|stack|traceback|log)\b", re.I)


def _rotulo(ferramenta: str) -> tuple:
    if ferramenta in ROTULOS:
        return ROTULOS[ferramenta]
    if ferramenta in MEMORIA or ferramenta.startswith("memory"):
        return ROTULO_MEMORIA
    return ROTULO_OUTRO


def _get(x, k, d=None):
    return x.get(k, d) if isinstance(x, dict) else getattr(x, k, d)


def _ferramenta(item) -> str:
    tipo = _get(item, "type")
    kvps = _get(item, "kvps") or {}
    nome = str(kvps.get("_tool_name") or "") if isinstance(kvps, dict) else ""
    if not nome:
        achado = re.search(r"Using tool '([^':]+)", str(_get(item, "heading") or ""))
        nome = achado.group(1) if achado else ""
    return nome or {"code_exe": "code_execution_tool", "browser": "browser", "subagent": "call_subordinate"}.get(tipo, "")


def _curto(texto, n: int) -> str:
    t = " ".join(str(texto or "").split())
    return t if len(t) <= n else t[:n - 1].rsplit(" ", 1)[0] + "…"


def itens(logs, agora: float | None = None) -> list[dict]:
    """Log items (live LogItem objects or dicts) as plain dicts, oldest first."""
    saida = []
    for x in logs or []:
        tipo = str(_get(x, "type") or "")
        kvps = _get(x, "kvps") or {}
        saida.append({"em": float(_get(x, "timestamp") or 0), "tipo": tipo, "agente": int(_get(x, "agentno") or 0),
                      "ferramenta": _ferramenta(x) if tipo in TIPOS_FERRAMENTA else "",
                      "titulo": str((kvps.get("headline") if isinstance(kvps, dict) else "") or ""),
                      "texto": str(_get(x, "content") or "")})
    saida.sort(key=lambda i: i["em"])
    return saida


def _pai(ctx) -> str:
    try:
        pid = ctx.get_output_data("parent_context_id") or ""
    except Exception:
        pid = ""
    return pid or ctx.get_data("_parallel_parent_context_id") or ctx.get_data("parent_context_id") or ""


def familia(raiz, contextos) -> list:
    """The request's chat and every chat it started (helpers in their own chats, parallel workers), any depth."""
    por_id = {c.id: c for c in contextos}
    saida = []
    for c in por_id.values():
        x = c
        for _ in range(8):
            if x is None:
                break
            if x.id == raiz.id:
                saida.append(c)
                break
            x = por_id.get(_pai(x))
    return saida or [raiz]


def respondido(proprios: list[dict], desde: float) -> bool:
    """The main agent already answered the person after their last message (the answer leaves the summary)."""
    return any(i["tipo"] == "response" and i["agente"] == 0 and i["em"] >= desde for i in proprios)


def parado_por_ele(proprios: list[dict], desde: float) -> bool:
    """Stopped by /parar or by a_encerrar: the person was already told, no "parou sem resposta" after it."""
    return any(i["tipo"] == "info" and (PARADO_POR_ELE in i["texto"] or ENCERRADO_SOZINHO in i["texto"])
               and i["em"] >= desde for i in proprios)


def esperando(todos: list[dict], aprovacao: bool = False) -> str:
    """What a legitimately slow step waits for ("" when nothing slow runs): the newest item is a slow tool still
    running (its result not written yet, or a terminal command printing as it goes), or an approval is pending."""
    if aprovacao:
        return ROTULO_APROVACAO
    if not todos:
        return ""
    ultimo = todos[-1]
    if ultimo["tipo"] not in TIPOS_FERRAMENTA:
        return ""
    espera = _rotulo(ultimo["ferramenta"])[2]
    if not espera:
        return ""
    lento = ultimo["tipo"] == "code_exe" or ultimo["ferramenta"] in ("code_execution_tool", "code_execution_remote",
                                                                      "terminal_isolado", "input", "wait")
    return espera if (lento or not ultimo["texto"].strip()) else ""


def eventos(todos: list[dict], desde: float, maximo: int = MAX_EVENTOS) -> list[str]:
    """The items since `desde` as short lines for the small model: what the log says, in its own words."""
    linhas = []
    for i in todos:
        if i["em"] < desde or i["tipo"] in CALADAS and not (i["tipo"] == "response" and i["agente"] > 0):
            continue
        hora = datetime.fromtimestamp(i["em"], FUSO).strftime("%H:%M") if i["em"] else "--:--"
        if i["tipo"] == "agent":
            if i["titulo"]:
                linhas.append(f"[{hora}] passo: {_curto(i['titulo'], CORTE_EVENTO)}")
        elif i["tipo"] in TIPOS_FERRAMENTA:
            r = _rotulo(i["ferramenta"])
            resultado = _curto(i["texto"], CORTE_EVENTO - 40)
            linhas.append(f"[{hora}] {r[0]} — resultado: {resultado}" if resultado else f"[{hora}] {r[1]} (ainda sem resultado)")
        elif i["tipo"] == "response":
            linhas.append(f"[{hora}] um ajudante concluiu: {_curto(i['texto'], CORTE_EVENTO)}")
        elif i["tipo"] == "user" and i["agente"] == 0 and i["em"] - desde > 5:  # not the request itself
            linhas.append(f"[{hora}] a pessoa acrescentou: {_curto(i['texto'], 120)}")
        elif i["tipo"] in ("warning", "error"):
            linhas.append(f"[{hora}] problema: {_curto(i['texto'], 120)}")
    return linhas[-maximo:]


def feito_codigo(todos: list[dict], desde: float) -> str:
    """What was done since `desde`, from the tools that finished (fixed plain words: nothing to invent)."""
    contagem: dict[str, int] = {}
    ajudante = False
    for i in todos:
        if i["em"] < desde:
            continue
        if i["tipo"] == "response" and i["agente"] > 0:
            ajudante = True
        elif i["tipo"] in TIPOS_FERRAMENTA and i["texto"].strip():
            feito = _rotulo(i["ferramenta"])[0]
            contagem[feito] = contagem.get(feito, 0) + 1
    partes = ["um ajudante terminou a parte dele"] if ajudante else []
    for feito, n in sorted(contagem.items(), key=lambda kv: -kv[1]):
        if len(partes) >= 2:
            break
        partes.append(feito + (f" ({n}×)" if n > 1 else ""))
    return " e ".join(partes)


def agora_codigo(todos: list[dict]) -> str:
    """What it is doing now, in fixed plain words."""
    for i in reversed(todos):
        if i["tipo"] in TIPOS_FERRAMENTA:
            return _rotulo(i["ferramenta"])[1] if not i["texto"].strip() or i is todos[-1] else "decidindo o próximo passo"
        if i["tipo"] == "agent":
            return "decidindo o próximo passo"
    return ""


def _palavras_marcadas(texto: str) -> set:
    """Numbers, links, @handles and capitalised names (not the first word of a sentence)."""
    marcadas = set(re.findall(r"https?://\S+|www\.\S+|@\w+|\d+(?:[.,]\d+)*", texto))
    for frase in re.split(r"(?<=[.!?:;])\s+|\n", texto):
        palavras = re.findall(r"\b[\wÀ-ÿ]+\b", frase)
        marcadas.update(p for p in palavras[1:] if p[:1].isupper())
    return marcadas


def nao_inventa(texto: str, fonte: str) -> bool:
    """No number, link, handle or name that the log (`fonte`) does not have, and no machinery word."""
    if JARGAO.search(texto or ""):
        return False
    base = re.sub(r"\[\d\d:\d\d\]", " ", fonte or "").lower()  # the hours the lines carry are not facts
    numeros = set(re.findall(r"\d+(?:[.,]\d+)*", base))
    for m in _palavras_marcadas(texto or ""):
        if re.fullmatch(r"\d+(?:[.,]\d+)*", m):
            if m not in numeros:
                return False
        elif m.lower() not in base:
            return False
    return True


def pergunta(pedidos: list[dict]) -> str:
    blocos = []
    for n, p in enumerate(pedidos, 1):
        linhas = "\n".join(p.get("eventos") or []) or "(nada novo no registro)"
        blocos.append(f"Pedido {n}: «{_curto(p.get('pedido'), 200)}»\nRegistro desde o último resumo:\n{linhas}")
    return ("Uma pessoa pediu tarefas a um assistente pelo celular e quer saber, em linguagem de gente, como elas "
            "andam. Para cada pedido abaixo, a partir SÓ do registro dele, escreva:\n"
            "- feito: 1 ou 2 coisas concretas que o registro mostra feitas (vazio se não houver nada concreto);\n"
            "- agora: o que está sendo feito agora (o último item do registro).\n"
            f"Cada campo com no máximo {CAMPO_MAX - 20} caracteres, em português simples, sem nome de ferramenta, "
            "sem palavras técnicas (nada de navegador headless, terminal, script, agente, subordinado, API, JSON) e "
            "sem inventar: nenhum número, nome, loja, preço ou link que não esteja no registro. Comece com verbo "
            "(\"comparou preços em 3 lojas\", \"lendo as avaliações do modelo X\").\n\n"
            + "\n\n".join(blocos) +
            '\n\nResponda só JSON: {"pedidos": [{"feito": "...", "agora": "..."}, ...]} na mesma ordem.')


def _chamar(texto: str) -> str:
    body = {"model": MODELO, "reasoning": {"effort": "low"}, "input": [{"role": "user", "content": texto}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=ESPERA_S) as r:
        data = json.loads(r.read())
    return "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []) if c.get("type") == "output_text")


def _campo(valor) -> str:
    t = _curto(str(valor or "").strip().rstrip("."), CAMPO_MAX)
    return t[:1].lower() + t[1:] if t[:2] != t[:2].upper() else t  # "Comparou" -> "comparou" (not "PDF")


def redigir(pedidos: list[dict], chamar=None) -> list[dict]:
    """{"feito", "agora"} per request: the small model's words when they pass nao_inventa, else the code's."""
    saida = [{"feito": p.get("feito_codigo") or "", "agora": p.get("agora_codigo") or "", "fonte": "codigo"}
             for p in pedidos]
    if not any(p.get("eventos") for p in pedidos):
        return saida
    try:
        resposta = (chamar or _chamar)(pergunta(pedidos))
        achado = re.search(r"\{.*\}", resposta or "", re.S)
        lista = json.loads(achado.group(0)).get("pedidos") if achado else None
    except Exception:
        lista = None
    if not isinstance(lista, list):
        return saida
    for n, (p, r) in enumerate(zip(pedidos, lista)):
        if not isinstance(r, dict):
            continue
        fonte = p.get("pedido", "") + "\n" + "\n".join(p.get("eventos") or [])
        feito, agora = _campo(r.get("feito")), _campo(r.get("agora"))
        if all(nao_inventa(c, fonte) for c in (feito, agora)) and (feito or agora):
            saida[n] = {"feito": feito, "agora": agora or saida[n]["agora"], "fonte": "modelo"}
    return saida


def _minutos(s: float) -> int:
    return max(1, round(s / 60))


def _estado_linha(p: dict) -> str:
    """The "Agora" part: waiting for a slow step, no progress, or what it is doing."""
    parado = float(p.get("parado_s") or 0)
    if p.get("esperando") and parado >= ESPERA_LONGA:
        espera = f"esperando {p['esperando']} há {_minutos(parado)} min"
        return f"Agora: {p['agora']} — {espera}" if p.get("agora") else f"Agora: {espera}"
    if p.get("esperando"):
        return f"Agora: {p['agora']}" if p.get("agora") else f"Agora: esperando {p['esperando']}"
    if parado >= PARADO:
        ultima = f" (última coisa: {p['agora']})" if p.get("agora") else ""
        if parado >= TRAVADO:
            return f"⚠️ Parado há {_minutos(parado)} min{ultima}: parece travado. /parar e mande de novo · /painel mostra tudo"
        return f"⚠️ Sem avanço há {_minutos(parado)} min{ultima} · {COMANDOS}"
    return f"Agora: {p['agora']}" if p.get("agora") else ""


def texto_resumo(pedidos: list[dict], agora: float) -> str:
    """The summary message. pedidos: [{"pedido", "inicio", "feito", "agora", "parado_s", "esperando"}]."""
    pedidos = sorted(pedidos, key=lambda p: float(p.get("inicio") or 0))
    if len(pedidos) == 1:
        p = pedidos[0]
        linhas = [f"⏳ Ainda em «{_curto(p.get('pedido'), 60) or 'seu pedido'}» ({_minutos(agora - p['inicio'])} min)"]
        if p.get("feito"):
            linhas.append(f"Feito: {p['feito']}")
        estado = _estado_linha(p)
        if estado:
            linhas.append(estado)
        return "\n".join(linhas)
    linhas = [f"⏳ Ainda em {len(pedidos)} pedidos:"]
    aviso = False
    for p in pedidos[:MAX_PEDIDOS]:
        partes = [f"feito: {p['feito']}"] if p.get("feito") else []
        estado = _estado_linha(p)
        if estado.startswith("⚠️"):
            aviso = True
            estado = estado.split(" · /parar")[0].split(". /parar")[0]
        if estado:
            partes.append(estado[0].lower() + estado[1:] if estado.startswith("Agora") else estado)
        linhas.append(f"• «{_curto(p.get('pedido'), 45) or 'pedido'}» ({_minutos(agora - p['inicio'])} min)"
                      + (" — " + "; ".join(partes) if partes else ""))
    if len(pedidos) > MAX_PEDIDOS:
        linhas.append(f"• e mais {len(pedidos) - MAX_PEDIDOS}")
    if aviso:
        linhas.append("/parar para todos · /painel mostra tudo")
    return "\n".join(linhas)


def texto_sem_resposta(pedidos: list[dict], agora: float) -> str:
    """A request that stopped with no answer (ended by the clean-up, a crash, an error)."""
    nomes = ", ".join(f"«{_curto(p.get('pedido'), 45) or 'pedido'}»" for p in pedidos[:MAX_PEDIDOS])
    return (f"⏹️ {nomes} parou sem me dar a resposta" + (f" (depois de {_minutos(agora - pedidos[0]['inicio'])} min)"
                                                           if len(pedidos) == 1 else "")
            + ". Se ainda precisar, mande de novo; /painel mostra o que ficou.")


def em_silencio(login: str, agora: float, ultima_entrada: float, silencio: dict | None = None,
                foco: dict | None = None) -> bool:
    """The bridge's quiet hours (/silencio) and /foco for progress notices: a /foco running, or quiet hours and the
    person did not write in the last 30 min."""
    foco = _ler(FOCO) if foco is None else foco
    try:
        if agora < float(foco.get(login) or 0):
            return True
    except (TypeError, ValueError):
        pass
    silencio = _ler(SILENCIO) if silencio is None else silencio
    regra = silencio.get(login) or SILENCIO_PADRAO
    if regra.get("desligado") or agora - float(ultima_entrada or 0) < ACORDADO:
        return False
    hora = datetime.fromtimestamp(agora, FUSO).strftime("%H:%M")
    inicio, fim = regra.get("inicio", "23:00"), regra.get("fim", "07:00")
    return (inicio <= hora or hora < fim) if inicio > fim else (inicio <= hora < fim)


def _ler(arq: Path) -> dict:
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def estado() -> dict:
    return _ler(ESTADO)


def guardar(dados: dict) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ESTADO)


def planejar(por_pessoa: dict, est: dict, agora: float, proc: str, silencio=None) -> list[dict]:
    """What to send now, and the state updated in place (`est`). por_pessoa: {login: [request]}, request = {"id",
    "pedido", "desde" (his last message), "rodando", "respondido", "parado_por_ele", "ultimo_item" (newest log item
    of its chats), "esperando", "ultima_entrada" (his newest message in any chat)}. silencio(login, ultima_entrada) ->
    bool. Returns [{"login", "tipo": "resumo"|"sem_resposta", "pedidos": [{... "inicio", "visto", "parado_s"}]}]."""
    silencio = silencio or (lambda login, ultima: em_silencio(login, agora, ultima))
    saida = []
    for login in sorted(set(por_pessoa) | set(est)):
        reg = est.get(login) or {}
        if reg.get("proc") != proc:  # a restart: those requests are resumed and told by _56_retomar_pedido
            reg = {"em": 0, "proc": proc, "pedidos": {}}
        vistos = reg.setdefault("pedidos", {})
        ativos, sem_resposta = [], []
        pedidos = {p["id"]: p for p in por_pessoa.get(login, [])}
        for cid in list(vistos):
            p = pedidos.get(cid)
            if p is not None and p["rodando"] and not p["respondido"]:
                continue
            antigo = vistos.pop(cid)
            if (p is not None and not p["rodando"] and not p["respondido"] and not p.get("parado_por_ele")
                    and antigo.get("resumido")):
                sem_resposta.append({**antigo, "pedido": p.get("pedido") or antigo.get("pedido")})
        for cid, p in pedidos.items():
            if not p["rodando"] or p["respondido"]:
                continue
            v = vistos.setdefault(cid, {"inicio": float(p["desde"]), "visto": float(p["desde"]), "pedido": p["pedido"]})
            v["pedido"] = p["pedido"] or v.get("pedido", "")
            if agora - v["inicio"] >= MOSTRAR_APOS:
                ativos.append({**p, **v, "id": cid, "parado_s": max(0.0, agora - float(p.get("ultimo_item") or agora))})
        ultima = max([float(p.get("ultima_entrada") or 0) for p in pedidos.values()] or [0.0])
        if not vistos and not sem_resposta:
            est.pop(login, None)
            continue
        est[login] = reg
        if sem_resposta and not silencio(login, ultima):
            saida.append({"login": login, "tipo": "sem_resposta", "pedidos": sem_resposta})
        if not ativos or not any(agora - a["inicio"] >= PRIMEIRO for a in ativos):
            continue
        desde_ultimo = agora - float(reg.get("em") or 0)
        parada_nova = any(a["parado_s"] >= PARADO and not a.get("esperando")
                          and vistos[a["id"]].get("parada_avisada") != a.get("ultimo_item") for a in ativos)
        if not (desde_ultimo >= DEPOIS or (parada_nova and desde_ultimo >= MIN_ENTRE)):
            continue
        if silencio(login, ultima):
            continue
        saida.append({"login": login, "tipo": "resumo", "pedidos": ativos})
    return saida


def espera_dele(esperando_: str) -> bool:
    """Waiting on the person or on an agreed time: never a stall, however long."""
    return esperando_ in (ROTULO_APROVACAO, ROTULOS["pedir_codigo"][2], ROTULOS["wait"][2])


def a_encerrar(por_pessoa: dict, agora: float) -> list[tuple[str, dict]]:
    """(login, request) of the requests to stop now: running, unanswered, and nothing new in their chats for 30 min
    (90 min while a slow step runs). Waiting for the person (approval, a code) or an agreed time never counts."""
    saida = []
    for login in sorted(por_pessoa):
        for p in por_pessoa[login]:
            if not p["rodando"] or p["respondido"] or p.get("parado_por_ele") or espera_dele(p.get("esperando") or ""):
                continue
            limite = ENCERRAR_LENTO if p.get("esperando") else ENCERRAR
            parado = agora - float(p.get("ultimo_item") or agora)
            if parado >= limite:
                p["parado_s"] = parado  # the same dict: the caller marks it stopped for this pass's summaries
                saida.append((login, p))
    return saida


def texto_encerrado(p: dict, agora: float) -> str:
    ultima = agora_codigo(p.get("_itens") or [])
    return (f"⏹️ Encerrei «{_curto(p.get('pedido'), 60) or 'seu pedido'}»: {_minutos(p['parado_s'])} min sem avanço"
            + (f" (última coisa: {ultima})" if ultima else "")
            + ". Se ainda precisar, mande de novo; /painel mostra o que ficou.")


def marcar_enviado(est: dict, envio: dict, agora: float) -> None:
    """After a summary reached the phone: the next one counts from now and tells only what came after."""
    if envio["tipo"] != "resumo":
        return
    reg = est.setdefault(envio["login"], {"pedidos": {}})
    reg["em"] = agora
    for a in envio["pedidos"]:
        v = reg["pedidos"].get(a["id"])
        if v is None:
            continue
        v.update(visto=agora, resumido=True)
        if a["parado_s"] >= PARADO and not a.get("esperando"):
            v["parada_avisada"] = a.get("ultimo_item")


def resumindo(est: dict) -> set:
    """People who already get summaries (on WhatsApp their editable progress message then stops: see ponte.py)."""
    return {login for login, reg in est.items() if any(v.get("resumido") for v in (reg.get("pedidos") or {}).values())}


def processo() -> str:
    """This Agent Zero process (pid + start time): a restart drops the state instead of reporting "stopped"."""
    import os

    try:
        with open("/proc/self/stat") as f:
            return f"{os.getpid()}:{f.read().rsplit(')', 1)[1].split()[19]}"
    except Exception:
        return str(os.getpid())


RECENTES = 400  # log items read per chat (a long chat has thousands; a request's own are at the end)


def _recentes(ctx) -> list:
    try:
        return list(ctx.log.logs[-RECENTES:])
    except Exception:
        return []


def basico(contexto) -> dict:
    """A phone chat that is not running and not in any summary: nothing to read in its log."""
    desde = float(contexto.get_data("whatsapp_ultima_entrada") or 0)
    return {"id": contexto.id, "pedido": "", "desde": desde, "rodando": False, "respondido": True,
            "parado_por_ele": False, "ultimo_item": desde, "esperando": "", "ultima_entrada": desde}


def montar(contexto, contextos, aprovacoes=None) -> dict:
    """One phone request from Agent Zero's chats (used by the job loop; the rest of this file is plain data)."""
    proprios = itens(_recentes(contexto))
    chats = familia(contexto, contextos)
    todos = list(proprios)
    for c in chats:
        if c is contexto:
            continue
        for i in itens(_recentes(c)):
            i["agente"] += 1  # a helper's own chat: its "user" is the main agent, its answers a helper's
            todos.append(i)
    todos.sort(key=lambda i: i["em"])
    desde = float(contexto.get_data("whatsapp_ultima_entrada") or 0)
    pendente = bool(aprovacoes) and any(c.id in aprovacoes for c in chats)
    # a model call that does not come back is a stall, not a slow tool (api/destravar.py redoes that step at 6 min)
    modelo = any("Calling LLM" in str(getattr(getattr(c, "log", None), "progress", "") or "") for c in chats)
    return {"id": contexto.id, "pedido": str(contexto.get_data("whatsapp_ultimo_pedido") or ""), "desde": desde,
            "rodando": bool(contexto.is_running()), "respondido": respondido(proprios, desde),
            "parado_por_ele": parado_por_ele(proprios, desde), "ultimo_item": max([i["em"] for i in todos] or [desde]),
            "esperando": "" if modelo and not pendente else esperando(todos, pendente), "ultima_entrada": desde,
            "_itens": todos}


def completar(envio: dict) -> dict:
    """Adds, per request, the log lines since the last summary and the code's own words (for redigir)."""
    for p in envio["pedidos"]:
        todos = p.pop("_itens", None) or []
        p["eventos"] = eventos(todos, float(p.get("visto") or 0))
        p["feito_codigo"] = feito_codigo(todos, float(p.get("visto") or 0))
        p["agora_codigo"] = agora_codigo(todos)
    return envio


def texto_do_envio(envio: dict, agora: float, chamar=None) -> str:
    if envio["tipo"] == "sem_resposta":
        return texto_sem_resposta(envio["pedidos"], agora)
    completar(envio)
    for p, r in zip(envio["pedidos"], redigir(envio["pedidos"], chamar)):
        p.update(feito=r["feito"], agora=r["agora"])
    return texto_resumo(envio["pedidos"], agora)


if __name__ == "__main__":  # quick look at a made-up summary
    t = time.time()
    print(texto_resumo([{"pedido": "pesquisa lava e seca", "inicio": t - 23 * 60, "feito": "comparou preços",
                         "agora": "lendo avaliações", "parado_s": 30}], t))

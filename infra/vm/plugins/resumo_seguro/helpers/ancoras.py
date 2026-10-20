"""What a history summary must not lose: anchors (ids, @handles, paths, URLs) and the person's own words.

Agent Zero summarizes old history with the utility model ("~100 words, one paragraph"). Lead @handles, acao_id,
routine uuids and the /a0/usr/chats/<chat>/saidas/NNNN files written by resultados_grandes vanished in the
summary, and with them the way back to the full text. Here a short block, taken from the summarized text by
regex (no model), is appended to the summary: the anchors, the person's last messages verbatim and where the
full text is. Same input -> same block (no clock), so the prompt prefix stays stable for cache_prompt.

Idea from Hermes Agent (MIT), agent/context_compressor.py: _build_anchor_index, _build_verbatim_user_section,
_build_recovery_footer.
"""

import ast
import json
import re

LIMITE = 3_500  # characters of the whole block (20/10: more of his words, for focus)
MINIMO = 160  # below this budget the block is left out
FALAS = 8  # last messages of the person, verbatim
FALA_MAX = 400  # characters per message (longer ones are cut with "…")
POR_TIPO = 40  # candidates of each kind (the budget fits far fewer)
CABECALHO = "[resumo_seguro] Copiado literalmente do trecho resumido:"
RODAPE = "Texto completo:"
FALAS_TITULO = "## Falas dele literais (as mais novas por último)"

_SAIDA = re.compile(r"(?:/opt)?/a0/usr/chats/[\w.-]+/saidas/[\w.-]*\w")
_ARQUIVO = re.compile(r"(?<![\w/.~-])/(?:opt|a0|tmp|home|root|mnt|srv|workspace|var/lib)/[^\s\"'`<>\\|,;()\[\]{}]+")
_URL = re.compile(r"https?://[^\s\"'`<>\\|()\[\]{}]+")
_HANDLE = re.compile(r"(?<![\w@./:+-])@([A-Za-z0-9_](?:[A-Za-z0-9_.]{0,28}[A-Za-z0-9_])?)")
_ACAO = re.compile(r"\b(?:acao_id|id_acao|action_id)[\\\"']{0,3}\s*[:=]?\s*[\\\"']{0,3}([0-9a-f]{6,32})\b")
_ACAO_TEXTO = re.compile(r"\ba[cç][aã]o\s+([0-9a-f]{6})\b", re.IGNORECASE)
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_UUID_CHAVE = re.compile(r"\b(?i:uuid|task_uuid|task_id)[\\\"']{0,3}\s*[:=]\s*[\\\"']{0,3}([A-Za-z0-9_-]{6,40})")
_ROTINA = re.compile(r"\b(?i:rotina|tarefa|task)\s*[\"'(]?([A-Za-z0-9]{8})\b")
_FALA_JSON = re.compile(r'"(?:user_message|user_intervention)"\s*:\s*"((?:[^"\\]|\\.)*)"')
_RESUMO_JSON = re.compile(r'"messages_summary"\s*:\s*"((?:[^"\\]|\\.)*)"')
# code words that look like @handles in tool output
_NAO_HANDLE = {"property", "staticmethod", "classmethod", "dataclass", "abstractmethod", "wraps", "extensible",
               "param", "returns", "return", "override", "media", "import", "keyframes", "font-face", "type"}
_QUERY_SECRETA = re.compile(r"(?i)[?&](?:[\w-]*(?:token|key|secret|senha|password|sig|signature|auth|code))=")


class ResumoVazio(RuntimeError):
    """The summary model answered nothing: replacing the messages with it would lose them."""


def entrada_texto(mensagem: str) -> str:
    """The summarized text, as Agent Zero rendered it ("user: …" / "ai: …" lines).

    The topic summary passes a Python list of strings into the prompt template (its repr): undo that."""
    texto = mensagem or ""
    if texto.startswith("#"):
        texto = texto.split("\n", 1)[1] if "\n" in texto else ""
    bruto = texto.strip()
    if bruto.startswith("[") and bruto.endswith("]"):
        try:
            itens = ast.literal_eval(bruto)
            if isinstance(itens, list) and all(isinstance(i, str) for i in itens):
                return "\n".join(itens)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            pass
    return texto


def _plano(texto: str) -> str:
    # escaped JSON inside JSON (a summary of a summary): turn \n, \t and \" back into separators
    return re.sub(r'\\+"', '"', re.sub(r"\\+[nrt]", " ", texto))


def _rotina_ok(valor: str) -> bool:
    return any(c.isdigit() for c in valor) or (any(c.isupper() for c in valor[1:]) and any(c.islower() for c in valor))


def _valor(rotulo: str) -> str:
    return rotulo.split("=", 1)[1] if rotulo.startswith(("acao_id=", "uuid=")) else rotulo


def _url_ok(url: str) -> bool:
    return len(url) > 10 and not _QUERY_SECRETA.search(url)


def _por_tipo(texto: str, ctx_id: str = "") -> list[list[str]]:
    """Anchors by kind, in priority order (saidas files, acao_id, uuids, @handles, URLs, other paths); newest first."""
    plano = _plano(texto)
    proprios = {f"/a0/usr/chats/{ctx_id}/saidas/", f"/a0/usr/chats/{ctx_id}/chat.json"} if ctx_id else set()

    def ultimos(achados):
        vistos, saida = set(), []
        for valor, rotulo in reversed(achados):
            if valor not in vistos:
                vistos.add(valor)
                saida.append(rotulo)
        return saida

    saidas = [(m.group(0), m.group(0)) for m in _SAIDA.finditer(plano)]
    acoes = sorted([(m.start(), m.group(1)) for m in _ACAO.finditer(plano)]
                   + [(m.start(), m.group(1).lower()) for m in _ACAO_TEXTO.finditer(plano)
                      if any(c.isdigit() for c in m.group(1))])
    uuids = sorted([(m.start(), m.group(0).lower()) for m in _UUID.finditer(plano)]
                   + [(m.start(), m.group(1)) for m in _UUID_CHAVE.finditer(plano)]
                   + [(m.start(), m.group(1)) for m in _ROTINA.finditer(plano) if _rotina_ok(m.group(1))])
    handles = [(m.group(1).lower(), "@" + m.group(1)) for m in _HANDLE.finditer(plano)
               if m.group(1).lower() not in _NAO_HANDLE and not m.group(1).lower().startswith("extension")]
    urls = [(u, u) for u in (m.group(0).rstrip(".,;:!?'\"") for m in _URL.finditer(plano)) if _url_ok(u)]
    arquivos = [(a, a) for a in (m.group(0).rstrip(".,;:!?'\"") for m in _ARQUIVO.finditer(plano))
                if len(a) > 6 and a not in proprios and not _SAIDA.fullmatch(a) and a.count("/") >= 2]

    grupos, vistos = [], set()
    for grupo in (ultimos(saidas),
                  ultimos([(v, f"acao_id={v}") for _, v in acoes]),
                  ultimos([(v, f"uuid={v}") for _, v in uuids]),
                  ultimos(handles), ultimos(urls), ultimos(arquivos)):
        novos = []
        for rotulo in grupo:
            chave = _valor(rotulo).lower()
            if chave not in vistos:
                vistos.add(chave)
                novos.append(rotulo)
        grupos.append(novos)
    return grupos


def ancoras(texto: str, ctx_id: str = "") -> list[str]:
    """All anchors, in priority order of kind and newest first within a kind."""
    return [a for grupo in _por_tipo(texto, ctx_id) for a in grupo]


def _json_str(bruto: str) -> str | None:
    try:
        valor = json.loads(f'"{bruto}"')
    except ValueError:
        return None
    return valor if isinstance(valor, str) else None


def _falas_de_blocos(texto: str, base: int) -> list[tuple[int, str]]:
    # messages kept by an earlier block (the summary of a summary): keep them alive
    saida = []
    for m in re.finditer(re.escape(CABECALHO), texto):
        fim = texto.find(RODAPE, m.end())
        trecho = texto[m.end(): fim if fim >= 0 else len(texto)]
        for n, linha in enumerate(trecho.split("\n")):
            if linha.startswith("» ") and linha[2:].strip():
                saida.append((base + m.start() + n, linha[2:].strip()))
    return saida


def falas(texto: str) -> list[str]:
    """The person's messages in the summarized text, oldest first (verbatim, whitespace collapsed)."""
    achadas = []
    for m in _FALA_JSON.finditer(texto):
        valor = _json_str(m.group(1))
        if valor and valor.strip():
            achadas.append((m.start(), valor))
    for m in _RESUMO_JSON.finditer(texto):
        valor = _json_str(m.group(1))
        if valor:
            achadas.extend(_falas_de_blocos(valor, m.start()))
    achadas.extend(_falas_de_blocos(texto, 0))
    saida = []
    for _, valor in sorted(achadas, key=lambda x: x[0]):
        linha = " ".join(valor.split())
        if len(linha) > FALA_MAX:
            linha = linha[: FALA_MAX - 1].rstrip() + "…"
        if linha in saida:
            saida.remove(linha)
        saida.append(linha)
    return saida


def bloco(texto: str, resumo: str = "", ctx_id: str = "", teto: int | None = None,
          com_falas: bool = True) -> str:
    """The block appended to a summary; "" when nothing fits or nothing is worth keeping.

    teto defaults to min(LIMITE, half of what the summary saved), so the summary always stays shorter than
    the text it replaced (otherwise Agent Zero stops with "History compression stalled")."""
    if teto is None:
        teto = min(LIMITE, (len(texto) - len(resumo or "")) // 2)
    teto = min(teto, LIMITE)
    if teto < MINIMO:
        return ""
    rodape = (f"{RODAPE} os resultados longos ficam em /a0/usr/chats/{ctx_id}/saidas/ (leia só o trecho, com grep "
              f"ou sed); as mensagens recentes, inteiras, no registro /a0/usr/chats/{ctx_id}/chat.json.") if ctx_id \
        else f"{RODAPE} os arquivos citados acima (leia só o trecho, com grep ou sed)."
    resumo = resumo or ""
    grupos = [[a for a in g if _valor(a) not in resumo][:POR_TIPO] for g in _por_tipo(texto, ctx_id)]
    ditas = falas(texto)[-FALAS:] if com_falas else []
    if not any(grupos) and not ditas:
        return ""

    def montar(escolhidas, falas_escolhidas):
        partes = [CABECALHO]
        if falas_escolhidas:
            partes.append(FALAS_TITULO)
            partes.extend(f"» {f}" for f in falas_escolhidas)
        if escolhidas:
            partes.append("Âncoras: " + " · ".join(escolhidas))
        partes.append(rodape)
        return "\n".join(partes)

    if len(montar([], [])) > teto:
        return ""
    # one of each kind per round (saidas, acao_id, uuid, @, a message, URL, path), newest first, until the
    # budget ends: a long list of one kind never pushes out the others
    ordem = [a for g in grupos for a in g]
    filas = [list(g) for g in grupos[:4]] + [list(reversed(ditas))] + [list(g) for g in grupos[4:]]
    escolhidas, falas_escolhidas, abertas = [], [], set(range(len(filas)))
    while abertas:
        for i in sorted(abertas):
            if not filas[i]:
                abertas.discard(i)
                continue
            item = filas[i].pop(0)
            if i == 4:
                tentativa = montar(escolhidas, [item] + falas_escolhidas)
            else:
                tentativa = montar(escolhidas + [item], falas_escolhidas)
            if len(tentativa) > teto:
                abertas.discard(i)
            elif i == 4:
                falas_escolhidas.insert(0, item)
            else:
                escolhidas.append(item)
    if not escolhidas and not falas_escolhidas:
        return ""
    return montar(sorted(escolhidas, key=ordem.index), falas_escolhidas)


def depois_do_resumo(data: dict, mensagem: str, ctx_id: str = "") -> None:
    """End of Agent.call_utility_model for a history summary: append the block, or keep the history whole.

    A failed call stays an exception: Agent Zero calls the model before it replaces any message, so nothing is
    lost. An empty answer would replace the messages with nothing: it becomes an exception too."""
    if isinstance(data.get("exception"), BaseException):
        return
    resumo = data.get("result")
    if not isinstance(resumo, str) or not resumo.strip():
        data["exception"] = ResumoVazio("o modelo de resumo não devolveu texto; o histórico ficou inteiro, "
                                        "nada foi resumido")
        return
    try:
        extra = bloco(entrada_texto(mensagem), resumo, ctx_id)
    except Exception:
        return  # never break the summary itself
    if extra:
        data["result"] = resumo.rstrip() + "\n\n" + extra


def bloco_do_registro(itens, ctx_id: str = "") -> str:
    """Anchors of a whole chat log (Agent Zero log items), e.g. for the _herdado of a phone chat that starts
    fresh: the @handles, ids and saidas files of the old chat, and where its full text is."""
    texto = "\n".join(str(getattr(i, "content", "") or "") for i in itens or [])
    return bloco(texto, "", ctx_id, teto=LIMITE, com_falas=False)

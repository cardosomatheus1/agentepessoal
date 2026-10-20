"""History compression that summarizes less often and deeper, and never the task in progress.

Agent Zero (helpers/history.py) compresses as soon as the history passes its limit (ctx_length x ctx_history:
200.000 x 0,25 = 50 mil tokens on the VM) and only down to 80% of it (COMPRESSION_TARGET_RATIO): about every 10 mil
tokens a new summary, and each one rewrites the prompt from that point (cache lost). The current topic goes first
when it is the biggest part: Topic.compress_attention (CURRENT_TOPIC_ATTENTION_COMPRESSION 0,65) turns the middle of
the task being done into a paragraph - "perde contexto", "dá passos pequenos".

Here, when the history passes the same limit:
1. podar: old tool results (all but the newest MANTER_RESULTADOS) longer than PODA_MIN become one line - tool, size,
   the start, the anchors and where the full text is. Only now, when the cache is lost anyway (never between steps).
2. the task in progress stays whole: from the person's current request (objetivo_vivo's "msg_id": a "continua" or
   "e aí?" does not move it) or, without it, from the last user message, up to the end;
3. everything before it goes into ONE summary (Bulk) with the fixed sections of prompts/fw.topic_summary.sys.md; the
   next compression UPDATES that summary with the new messages instead of summarizing a summary of summaries;
4. down to ALVO (45%) of the limit at once: as many recent whole topics as fit are kept, the rest is summarized.
Only if the task in progress alone is bigger than TETO_CAUDA of the limit are its oldest topics summarized too, and
only if the last topic alone still does not fit does Agent Zero's own compression run (its large-message cut and
attention summary): the context never grows past the limit.

Hook: Agent Zero's message_loop_end/_10_organize_history.py and message_loop_prompts_before/_90_organize_history_wait.py
are overridden by files with the same names in this plugin (a plugin extension with the same file name replaces the
core one); both call compress_history() below. /a0 is not edited. Switch: the file DESLIGADO makes compress_history
call Agent Zero's own History.compress again (no deploy needed).

Ideas from Hermes Agent (MIT), agent/context_compressor.py (structured iterative summary, tool-output pruning
first, protected tail) and the OpenClaw docs (compaction / session pruning).
"""

import importlib.util
import json
import sys
from pathlib import Path

ALVO = 0.45  # history size after a compression, as a fraction of the limit
TETO_CAUDA = 0.8  # the task in progress is summarized only when, already pruned, it passes this fraction
MANTER_RESULTADOS = 3  # newest tool results never pruned
PODA_MIN = 1_500  # characters: shorter tool results are left as they are
PODA_TRECHO = 400  # characters of the start kept in a pruned result
PODA_ANCORAS = 6
MSG_MAX = 6_000  # characters of each message given to the summarizer (start + end)
ENTRADA_MAX = 120_000  # characters of the whole summarizer input
RESUMO_TOKENS = 2_000  # room reserved for the summary when choosing what to keep
CABECA = "## Resumo da conversa até aqui"
NOTA = ("(O que vem depois deste resumo está inteiro. O que vale agora é o pedido em andamento, a partir da última "
        "mensagem da pessoa; o resumo é só referência.)")
PODADO = "[resultado antigo encurtado"
CHAVE_PEDIDO = "objetivo_vivo"  # context data written by the objetivo_vivo plugin: {"msg_id": ...}
DESLIGADO = Path("/a0/usr/plugins/resumo_seguro/compressao_a0")
SISTEMA = "fw.topic_summary.sys.md"

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
# set by the tests (fake history module); inside the container helpers.history is imported
_h = None


def _history():
    if _h is not None:
        return _h
    from helpers import history

    return history


def _ancoras():
    nome = "resumo_seguro_ancoras"
    caminho = _RAIZ / "helpers" / "ancoras.py"
    mtime = caminho.stat().st_mtime
    antigo = sys.modules.get(nome)
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def desligado() -> bool:
    try:
        return DESLIGADO.exists()
    except OSError:
        return False


# ---- pruning ---------------------------------------------------------------------------------------------------

def _e_resultado(msg) -> bool:
    c = getattr(msg, "content", None)
    return (isinstance(c, dict) and "tool_name" in c and isinstance(c.get("tool_result"), str)
            and not getattr(msg, "summary", ""))


def linha_podada(content: dict, ctx_id: str = "") -> str:
    """The one line an old tool result becomes (JSON, like Agent Zero's own large-message cut)."""
    resultado = content.get("tool_result") or ""
    nome = str(content.get("tool_name") or "ferramenta")
    inicio = " ".join(resultado[:PODA_TRECHO * 2].split())[:PODA_TRECHO].rstrip()
    try:
        achadas = _ancoras().ancoras(resultado, ctx_id)[:PODA_ANCORAS]
    except Exception:
        achadas = []
    saida = next((a for a in achadas if "/saidas/" in a), "")
    onde = (f"texto inteiro em {saida} (leia só o trecho, com grep ou sed)" if saida
            else "texto inteiro no registro da conversa; se precisar, rode a ferramenta de novo")
    partes = [f"{PODADO} para caber o contexto: {len(resultado):,} caracteres. Começo: «{inicio}…»".replace(",", ".")]
    outras = [a for a in achadas if a != saida]
    if outras:
        partes.append("Âncoras: " + " · ".join(outras))
    partes.append(onde + "]")
    return json.dumps({"tool_name": nome, "tool_result": " ".join(partes)}, ensure_ascii=False, separators=(",", ":"))


def podar(mensagens, manter: int = MANTER_RESULTADOS, ctx_id: str = "") -> int:
    """Old tool results (all but the newest `manter`) longer than PODA_MIN become one line. Returns how many."""
    resultados = [m for m in mensagens if _e_resultado(m)]
    velhos = resultados[:-manter] if manter > 0 else resultados
    n = 0
    for m in velhos:
        if len(m.content.get("tool_result") or "") >= PODA_MIN:
            m.set_summary(linha_podada(m.content, ctx_id))
            n += 1
    return n


# ---- what to keep ------------------------------------------------------------------------------------------------

def _tokens(registros) -> int:
    return sum(r.get_tokens() for r in registros)


def inicio_da_tarefa(agent, topicos) -> int:
    """Index (in topicos = history.topics + [history.current]) of the topic where the task in progress starts."""
    ultimo = len(topicos) - 1
    while ultimo > 0 and not topicos[ultimo].messages:
        ultimo -= 1
    try:
        dados = agent.context.get_data(CHAVE_PEDIDO) if getattr(agent, "number", 0) == 0 else None
        mid = (dados or {}).get("msg_id") if isinstance(dados, dict) else None
    except Exception:
        mid = None
    if mid:
        for i in range(ultimo, -1, -1):
            if any(getattr(m, "id", None) == mid for m in topicos[i].messages):
                return i
    return ultimo


def _cortar(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    cabeca = int(limite * 0.7)
    return texto[:cabeca] + f"\n[… {len(texto) - limite:,} caracteres cortados …]\n".replace(",", ".") + texto[-(limite - cabeca):]


def _texto_registros(registros, limite_msg: int) -> str:
    h = _history()
    linhas = []
    for r in registros:
        for o in r.output():
            linhas.append(_cortar(h.output_text([o], ai_label="ai", human_label="user"), limite_msg))
    return "\n".join(linhas)


def entrada_do_resumo(anterior: str, novos) -> str:
    limite = MSG_MAX
    texto = _texto_registros(novos, limite)
    while len(texto) + len(anterior) > ENTRADA_MAX and limite > 800:
        limite //= 2
        texto = _texto_registros(novos, limite)
    texto = _cortar(texto, max(ENTRADA_MAX - len(anterior), 10_000))
    if anterior:
        return ("# Resumo anterior (atualize com as mensagens novas):\n" + anterior
                + "\n\n# Mensagens novas para incorporar:\n" + texto)
    return "# Mensagens para resumir:\n" + texto


def _resumo_anterior(registro) -> str:
    resumo = getattr(registro, "summary", "") or ""
    return resumo if resumo.startswith(CABECA) else ""


# ---- the compression ---------------------------------------------------------------------------------------------

async def comprimir(agent) -> bool:
    """Compress agent.history when it is over its limit (see the module doc). True when anything changed."""
    hist = agent.history
    limite = hist._get_ctx_size_for_history()
    if hist.get_tokens() <= limite:
        return False
    if desligado():
        return bool(await hist.compress())
    h = _history()
    ctx_id = str(getattr(getattr(agent, "context", None), "id", "") or "")
    alvo = int(limite * ALVO)
    topicos = list(hist.topics) + [hist.current]
    inicio = inicio_da_tarefa(agent, topicos)
    podadas = podar([m for t in topicos for m in t.messages], ctx_id=ctx_id)

    # keep the task in progress and, before it, as many recent whole topics as fit in ALVO
    k = inicio
    while k > 0 and _tokens(topicos[k - 1:]) + RESUMO_TOKENS <= alvo:
        k -= 1
    # the task in progress itself too big (already pruned): its oldest topics are summarized as well
    # (never past the last topic with messages: one topic too big is cut inside by Agent Zero, below)
    ultimo = max([i for i, t in enumerate(topicos) if t.messages] or [0])
    if _tokens(topicos[k:]) + RESUMO_TOKENS > limite * TETO_CAUDA:
        while k < ultimo and _tokens(topicos[k:]) + RESUMO_TOKENS > alvo:
            k += 1

    sair = topicos[:k]
    if not sair:
        if hist.get_tokens() <= limite:
            return podadas > 0
        return await _cortar_dentro(hist, topicos[ultimo], limite) or podadas > 0

    registros = list(hist.bulks) + sair
    anterior = _resumo_anterior(registros[0]) if registros else ""
    novos = registros[1:] if anterior else registros
    sistema = agent.read_prompt(SISTEMA)
    try:
        resumo = await agent.call_utility_model(system=sistema, message=entrada_do_resumo(anterior, novos))
    except Exception:
        if podadas and hist.get_tokens() <= limite:
            return True  # pruning alone was enough; the summary is tried again at the next compression
        raise
    if not isinstance(resumo, str) or not resumo.strip():
        if podadas and hist.get_tokens() <= limite:
            return True
        raise _ancoras().ResumoVazio("o modelo de resumo não devolveu texto; nada foi resumido")

    bloco = h.Bulk(history=hist)
    bloco.records = registros
    bloco.summary = f"{CABECA}\n{NOTA}\n\n{resumo.strip()}"
    # by identity, on the live lists: compression runs in a background thread and the person may have written in
    # the meantime (a new topic); nothing added during the model call is lost
    hist.bulks = [bloco] + [b for b in hist.bulks if not any(b is r for r in registros)]
    hist.topics = [t for t in hist.topics if not any(t is s for s in sair)]
    if hist.get_tokens() > limite:
        await _cortar_dentro(hist, topicos[ultimo], limite)
    return True


async def _cortar_dentro(hist, topico, limite: int) -> bool:
    """The task in progress alone is bigger than the limit: Agent Zero's own cut, but inside its topic only (its
    large messages first, then the summary of the middle, keeping the request and the last messages); Agent Zero's
    whole compression only if even that is not enough."""
    mudou = False
    for _ in range(64):
        if hist.get_tokens() <= limite or not await topico.compress():
            break
        mudou = True
    if hist.get_tokens() > limite:
        mudou = bool(await hist.compress()) or mudou
    return mudou


async def compress_history(agent) -> bool:
    """What Agent Zero's message_loop_end/_10_organize_history.compress_history does, with comprimir()."""
    compressed = bool(await comprimir(agent))
    if compressed:
        try:
            from helpers.history import clear_responses_provider_state

            clear_responses_provider_state(agent)
        except ImportError:
            pass
    return compressed

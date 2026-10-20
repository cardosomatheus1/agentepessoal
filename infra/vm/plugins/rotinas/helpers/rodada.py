"""A scheduled round starts with only the previous round in its chat's history (20/10, prompt enxuto).

A routine's dedicated chat kept every past round: the prospecting chat sat at the history ceiling (~50k tokens,
"History compression stalled" at every step), so each call of a 7-step round carried ~35-50k tokens of old rounds,
and the compression itself cost model calls and broke the provider cache. What a round needs from the past is in its
checkpoint (contexto.md, the tool's own state, the gate) and in the previous round, which stays when it is small.

Only whole rounds (topics) and old summaries (bulks) leave; the current round's message is never touched. The chat
window (log) keeps everything."""

ANTERIOR_MAX = 12_000  # tokens: the previous round stays when it is at most this big
MINIMO = 15_000        # tokens of old history below which nothing is done


def enxugar(historico, anterior_max: int = ANTERIOR_MAX, minimo: int = MINIMO) -> int:
    """Drop old rounds from `historico` (an Agent Zero History). Returns how many records (topics + bulks) left."""
    topicos, blocos = list(historico.topics), list(historico.bulks)
    velhos = sum(t.get_tokens() for t in topicos) + sum(b.get_tokens() for b in blocos)
    if velhos <= minimo or (not topicos and not blocos):
        return 0
    manter = topicos[-1:] if topicos and topicos[-1].get_tokens() <= anterior_max else []
    saem = len(blocos) + len(topicos) - len(manter)
    historico.bulks = []
    historico.topics = manter
    return saem

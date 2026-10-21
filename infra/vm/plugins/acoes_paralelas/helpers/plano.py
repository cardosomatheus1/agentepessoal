"""Which of the tool calls in one model answer may run at the same time (21/10, Hermes Agent's batch planner).

Matheus (21/10): "Quero que consiga fazer isso, mexer no coração e usar o do hermes". Port of Hermes Agent's
agent/tool_dispatch_helpers.py (MIT, NousResearch): _PARALLEL_SAFE_TOOLS, _PATH_SCOPED_READERS/_WRITERS and
_plan_tool_batch_segments. A batch is cut into segments, in order:
- read-only calls with no shared state (searches, reading documents, memory, remote reads of the connectors) join the
  current parallel segment;
- file reads and writes join it too, unless a write overlaps a path another call of the segment reads or writes;
- everything else (browser, phone, terminal, messages, the final answer, unknown tools) is a barrier: it runs alone,
  in order, exactly as Agent Zero runs it.
Agent Zero's own tools are named here, plus this repository's read-only ones. A tool missing from the list is a
barrier (the safe default: Hermes does the same with tools it does not know)."""

import os
import re

# always read-only, no shared session (the browser, the phone and the terminal have one screen/shell each)
SEGURAS = frozenset({"search_engine", "document_query", "memory_load", "lembrar", "consultar_sol"})
# read-only only for some actions
ACOES_SEGURAS = {
    "skills_tool": ("action", {"search", "list", "load", "read_file"}),
    "cerebro": ("acao", {"consultar", "assuntos"}),
    "fios": ("acao", {"listar"}),
    "decisao": ("acao", {"listar"}),
    "ferramentas_extras": ("acao", {"buscar"}),
}
# connector tools behind ferramentas_extras that only read (Google, GitHub)
LEITURA_REMOTA = re.compile(r"^(google|github)[._](get|list|search|read|query)_", re.I)
LEITORES = {"text_editor": {"read"}}
ESCRITORES = {"text_editor": {"write", "patch"}}


def _caminho(args: dict) -> str:
    p = args.get("path") if isinstance(args, dict) else None
    if not isinstance(p, str) or not p.strip():
        return ""
    return os.path.normpath(os.path.join("/a0/usr/workdir", p.strip()))


def admissao(nome: str, args) -> tuple[list[str], bool] | None:
    """(paths reserved, writes?) when the call may join a parallel segment; None = barrier."""
    args = args if isinstance(args, dict) else {}
    if nome in SEGURAS:
        return [], False
    if nome in ACOES_SEGURAS:
        chave, ok = ACOES_SEGURAS[nome]
        if str(args.get(chave) or "").strip().lower() in ok:
            return [], False
        if nome == "ferramentas_extras" and str(args.get("acao") or "").lower() == "usar" \
                and LEITURA_REMOTA.match(str(args.get("nome") or "")):
            return [], False
        return None
    acao = str(args.get("action") or "").strip().lower()
    for tabela, escreve in ((LEITORES, False), (ESCRITORES, True)):
        if acao in tabela.get(nome, ()):
            caminho = _caminho(args)
            return ([caminho], escreve) if caminho else None
    return None


def _sobrepoe(a: str, b: str) -> bool:
    return a == b or a.startswith(b.rstrip("/") + "/") or b.startswith(a.rstrip("/") + "/")


def planejar(chamadas: list[tuple[str, dict]]) -> list[tuple[str, list[int]]]:
    """[("paralelo" | "fila", [indexes])], in the order of the calls. A parallel segment of one call is a "fila"."""
    segmentos: list[tuple[str, list[int]]] = []
    atual: list[int] = []
    reservas: list[tuple[str, bool]] = []

    def fechar():
        nonlocal atual, reservas
        if atual:
            segmentos.append(("paralelo" if len(atual) > 1 else "fila", atual))
        atual, reservas = [], []

    for i, (nome, args) in enumerate(chamadas):
        adm = admissao(nome, args)
        if adm is None:
            fechar()
            segmentos.append(("fila", [i]))
            continue
        caminhos, escreve = adm
        if any((escreve or e) and _sobrepoe(c, r) for c in caminhos for r, e in reservas):
            fechar()
        reservas.extend((c, escreve) for c in caminhos)
        atual.append(i)
    fechar()
    return segmentos


# Hermes Agent's PARALLEL_TOOL_CALL_GUIDANCE (agent/prompt_builder.py), in Portuguese
ORIENTACAO = (
    "## Ações em paralelo\n"
    "Quando precisar de várias informações que não dependem umas das outras, peça todas na MESMA resposta (várias "
    "chamadas de ferramenta juntas) em vez de uma por vez: buscas, leituras de documento ou arquivo, memória, "
    "consultas à Pasta e leituras do Gmail/Agenda/Drive/GitHub rodam ao mesmo tempo. Só faça uma por vez quando a "
    "próxima depende do resultado da anterior. Navegador, celular, terminal e mensagens continuam um de cada vez. "
    "Para isso, ponha as chamadas direto na resposta; não use a ferramenta `parallel` (ela roda cada ação numa conversa "
    "separada, sem o seu contexto). `parallel` fica para tarefas longas em segundo plano."
)

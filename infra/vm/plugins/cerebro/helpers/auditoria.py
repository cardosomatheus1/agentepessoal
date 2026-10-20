"""Auditoria da Pasta (20/10, Q14): the checks of the Playbook Lab "OS Optimizer" that can be measured without a model,
with a 0-100 score (100 minus a capped deduction per check) and one line per finding (file, check, fix). Written to
Documentos/auditoria-AAAA-MM-DD.md. Run once after the structure exists, then monthly (job loop) or on request."""

import re
import time

CHECAGENS = {  # check -> (max deduction, what it measures)
    "claude-md": (10, "CLAUDE.md na raiz, até 200 linhas (falha acima de 300)"),
    "mapa": (10, "o mapa do CLAUDE.md cita todas as pastas de primeiro nível, e só pastas que existem"),
    "indices": (10, "toda pasta com 2+ notas tem indice.md citando cada nota"),
    "links-mortos": (15, "nenhum [[link]] para nota que não existe"),
    "orfas": (10, "toda nota é alcançável por um índice ou link"),
    "tamanho": (10, "notas até 10 KB (falha acima de 100 KB); nota do dia até ~2k tokens"),
    "cabecalho": (10, "cada nota com status e 2+ tags no cabeçalho"),
    "contexto": (15, "os 6 arquivos de Contexto preenchidos e validados (sem PENDENTE)"),
    "pendencias-velhas": (10, "pendências abertas há mais de 30 dias revistas (fechar, adiar ou reafirmar)"),
}
_LINK = re.compile(r"\[\[([^\]|#]+)")


def rodar(p, agora: float | None = None) -> dict:
    agora = agora or time.time()
    raiz = p.RAIZ
    notas = [f for f in raiz.rglob("*.md") if not any(x.startswith(".") for x in f.relative_to(raiz).parts)
             and f.relative_to(raiz).parts[0] != "Arquivo-morto"]
    nomes = {str(f.relative_to(raiz).with_suffix("")) for f in notas}
    achados = []

    def achar(checagem, arquivo, motivo, correcao, peso=1):
        achados.append({"checagem": checagem, "arquivo": arquivo, "motivo": motivo, "correcao": correcao, "peso": peso})

    claude = raiz / "CLAUDE.md"
    if not claude.exists():
        achar("claude-md", "CLAUDE.md", "não existe", "criar com as regras e o mapa", 10)
    else:
        n = len(claude.read_text(encoding="utf-8").splitlines())
        if n > 200:
            achar("claude-md", "CLAUDE.md", f"{n} linhas", "enxugar para até 200", 10 if n > 300 else 4)
        texto = claude.read_text(encoding="utf-8")
        for d in sorted(x.name for x in raiz.iterdir() if x.is_dir() and not x.name.startswith(".")):
            if f"{d}/" not in texto:
                achar("mapa", "CLAUDE.md", f"o mapa não cita {d}/", f"incluir {d}/ no mapa", 3)
    links = {}
    for f in notas:
        conteudo = f.read_text(encoding="utf-8", errors="ignore")
        rel = str(f.relative_to(raiz))
        for alvo in _LINK.findall(conteudo):
            links.setdefault(alvo.strip(), set()).add(rel)
            if alvo.strip() not in nomes:
                achar("links-mortos", rel, f"link para [[{alvo}]] que não existe", "corrigir ou tirar o link", 3)
        tam = len(conteudo.encode())
        if tam > 10 * 1024:
            achar("tamanho", rel, f"{tam // 1024} KB", "dividir em notas menores", 10 if tam > 100 * 1024 else 2)
        if rel.startswith("Notas-do-dia/") and len(conteudo) > 8000:
            achar("tamanho", rel, "nota do dia longa", "resumir", 2)
        if f.name not in ("CLAUDE.md", "indice.md"):
            cab = conteudo.split("\n---\n", 1)[0] if conteudo.startswith("---\n") else ""
            tags = re.search(r"^tags: (\[.*\])$", cab, re.M)
            if "status:" not in cab or not tags or tags.group(1).count(",") < 1:
                achar("cabecalho", rel, "sem status ou com menos de 2 tags", "completar o cabeçalho", 1)
    for d in [x for x in raiz.iterdir() if x.is_dir() and not x.name.startswith(".") and x.name != "Arquivo-morto"]:
        dentro = [f for f in d.glob("*.md") if f.name != "indice.md"]
        if len(dentro) >= 2:
            idx = d / "indice.md"
            texto = idx.read_text(encoding="utf-8") if idx.exists() else ""
            if not texto:
                achar("indices", f"{d.name}/", "sem indice.md", "gerar o índice", 4)
            else:
                faltam = [f.stem for f in dentro if f.stem not in texto]
                if faltam:
                    achar("indices", f"{d.name}/indice.md", f"{len(faltam)} nota(s) fora do índice", "regerar o índice", 3)
    for f in notas:
        rel = str(f.relative_to(raiz).with_suffix(""))
        if f.name in ("CLAUDE.md", "indice.md") or "/" not in rel:
            continue
        pasta_idx = f.parent / "indice.md"
        if rel not in links and not (pasta_idx.exists() and f.stem in pasta_idx.read_text(encoding="utf-8")):
            achar("orfas", rel, "nenhum índice ou link chega nela", "incluir no índice ou ligar a outra nota", 1)
    for nome in p.contexto_pendente():
        achar("contexto", f"Contexto/{nome}", "ainda pendente de validação", "fazer essa parte da entrevista", 3)
    for f in p.ler("pendencias"):
        if f.get("estado", "aberto") == "aberto" and agora - float(f.get("criado") or agora) > 30 * 86400:
            achar("pendencias-velhas", p.link(f"pendencia:{f.get('id')}"), "aberta há mais de 30 dias",
                  "fechar, adiar ou reafirmar com ele", 1)
    descontos = {c: min(m, sum(a["peso"] for a in achados if a["checagem"] == c)) for c, (m, _d) in CHECAGENS.items()}
    nota = max(0, 100 - sum(descontos.values()))
    return {"nota": nota, "descontos": descontos, "achados": achados, "notas": len(notas)}


def relatorio(p, r: dict, agora: float | None = None) -> str:
    agora = agora or time.time()
    linhas = [p.frontmatter({"status": "fechada", "tags": ["auditoria", "documento"]}).rstrip(),
              f"# Auditoria da Pasta — {time.strftime('%d/%m/%Y', p.agora_local(agora))}", "",
              f"**Nota: {r['nota']}/100** ({r['notas']} notas)", "", "| Checagem | O que mede | Desconto |", "|---|---|---|"]
    linhas += [f"| {c} | {d} | {r['descontos'][c]}/{m} |" for c, (m, d) in CHECAGENS.items()]
    linhas += ["", "## Achados"] + ([f"- **{a['checagem']}** · {a['arquivo']}: {a['motivo']} → {a['correcao']}"
                                     for a in r["achados"][:80]] or ["- nenhum"])
    return "\n".join(linhas) + "\n"


def gravar(p, agora: float | None = None) -> dict:
    r = rodar(p, agora)
    destino = p.RAIZ / "Documentos" / f"auditoria-{p.data(agora)}.md"
    p.escrever(destino, relatorio(p, r, agora))
    docs = p.RAIZ / "Documentos"
    p.escrever(docs / "indice.md", "# Documentos\n\n" + "\n".join(
        f"- [[Documentos/{f.stem}]]" for f in sorted(docs.glob("*.md"), reverse=True) if f.name != "indice.md") + "\n")
    p.versionar(f"auditoria {p.data(agora)}: {r['nota']}/100")
    return {**r, "arquivo": str(destino)}

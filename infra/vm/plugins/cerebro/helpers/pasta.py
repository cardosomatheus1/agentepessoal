"""The Segundo Cérebro's Pasta (20/10, ADR 0001): Matheus's decisions, pendências, assuntos, context, meetings and notas
do dia as Markdown files in one folder, the only source. Written only through this module (and the helpers that use
it: decisoes.py, fios.py, ficha.py, assuntos.py); the site and the agent read it.

Layout (from the Playbook Lab guides "Setup inicial do OS" and "OS Optimizer", with the glossary's words):
  CLAUDE.md            rules and the map of the folders (read first)
  Contexto/            organizacao, marca, estrategia, cliente-ideal, pessoas-chave, perfil (the interview fills them)
  Decisoes/ Pendencias/ Assuntos/   one file per item; frontmatter = the data, body = the readable note
  Reunioes/ Notas-do-dia/ Projetos/ Documentos/
  Arquivo-morto/       what left (undone, replaced files, the old stores): kept, never deleted
Each item file: a frontmatter of `chave: <JSON value>` lines (what the code reads) and a body rendered from it (what a
person or Obsidian reads; rewritten on every save). Links between items are [[Pasta/arquivo]] wiki links.
An unreadable item is an error, never "nothing there" (the next save would lose it). Every write is atomic."""

import json
import os
import re
import subprocess
import tempfile
import time
import unicodedata
from pathlib import Path

RAIZ = Path("/a0/usr/segundo_cerebro/pasta")
DONO = "matheus"
FUSO = "America/Bahia"
COLECOES = {"decisoes": "Decisoes", "pendencias": "Pendencias", "assuntos": "Assuntos"}
PASTAS = ("Contexto", "Decisoes", "Pendencias", "Assuntos", "Reunioes", "Notas-do-dia", "Projetos", "Documentos",
          "Arquivo-morto")
CONTEXTO = {  # file -> (title, what goes in it), the guide's six context files
    "organizacao.md": ("Organização", "o que são os negócios (Raiz, NEXOS, Orbyte…), o que vendem, como operam, ferramentas"),
    "marca.md": ("Marca e voz", "como cada marca fala, posicionamento, o que nunca dizer"),
    "estrategia.md": ("Estratégia", "metas, prioridades do trimestre, o que está fora de foco"),
    "cliente-ideal.md": ("Cliente ideal", "quem compra, dores, objeções, onde estão"),
    "pessoas-chave.md": ("Pessoas-chave", "sócios, clientes, parceiros e fornecedores que importam, e o papel de cada um"),
    "perfil.md": ("Perfil do Matheus", "quem ele é, jeito de trabalhar, como o agente deve trabalhar com ele"),
}
PENDENTE = "[PENDENTE DE VALIDAÇÃO]"
DERIVADOS = ("status", "tags")  # written for people/Obsidian (and the audit), recomputed on save, never read back
MARCA_MIGRADO = ".migrado"


class Ilegivel(RuntimeError):
    pass


def ativa(login: str) -> bool:
    """The Pasta is the store for this person (only the owner, and only after the one-time migration)."""
    return re.sub(r"[^a-z0-9_.-]", "", str(login or "").lower()) == DONO and (RAIZ / MARCA_MIGRADO).exists()


def agora_local(ts: float | None = None) -> time.struct_time:
    os.environ.setdefault("TZ", FUSO)
    try:
        time.tzset()
    except AttributeError:
        pass
    return time.localtime(ts if ts is not None else time.time())


def data(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", agora_local(ts))


def slug(texto: str, n: int = 50) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return (t[:n].rstrip("-") or "item")


# ---------------------------------------------------------------- files
def escrever(caminho: Path, texto: str) -> bool:
    """Atomic write; False when the content was already the same (nothing changes, no new version)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if caminho.exists() and caminho.read_text(encoding="utf-8") == texto:
        return False
    fd, tmp = tempfile.mkstemp(dir=caminho.parent, prefix=f".{caminho.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, caminho)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return True


def frontmatter(campos: dict) -> str:
    linhas = [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in campos.items() if not str(k).startswith("_")]
    return "---\n" + "\n".join(linhas) + "\n---\n"


def ler_frontmatter(texto: str, nome: str = "") -> dict:
    if not texto.startswith("---\n"):
        raise Ilegivel(f"{nome}: sem cabeçalho")
    fim = texto.find("\n---\n", 4)
    if fim < 0:
        raise Ilegivel(f"{nome}: cabeçalho sem fim")
    campos = {}
    for linha in texto[4:fim].splitlines():
        if not linha.strip():
            continue
        chave, sep, valor = linha.partition(": ")
        if not sep:
            raise Ilegivel(f"{nome}: linha sem valor ({linha[:40]!r})")
        try:
            campos[chave.strip()] = json.loads(valor)
        except ValueError:
            raise Ilegivel(f"{nome}: valor ilegível em {chave!r}") from None
    for k in DERIVADOS:
        campos.pop(k, None)
    return campos


def _arquivos(colecao: str) -> dict:
    """id -> file of a collection's items (the id is in each file's frontmatter)."""
    pasta = RAIZ / COLECOES[colecao]
    achados = {}
    for f in sorted(pasta.glob("*.md")) if pasta.exists() else []:
        if f.name == "indice.md":
            continue
        campos = ler_frontmatter(f.read_text(encoding="utf-8"), f.name)
        achados[str(campos.get("id"))] = (f, campos)
    return achados


def ler(colecao: str) -> list[dict]:
    try:
        return [campos for _f, campos in _arquivos(colecao).values()]
    except OSError as exc:
        raise Ilegivel(f"a pasta {COLECOES[colecao]} não pôde ser lida ({str(exc)[:60]})") from None


def prefixo(ident) -> str:
    """The file-name prefix of an item: its number padded, or its id made safe (an old loose end had brackets and spaces
    in its id, which broke file globs and links)."""
    ident = str(ident)
    return ident.zfill(4) if ident.isdigit() else slug(ident, 40)


def _nome_arquivo(colecao: str, item: dict) -> str:
    return f"{prefixo(item.get('id'))}-{slug(titulo(colecao, item))}.md"


def gravar(colecao: str, itens: list[dict]) -> dict:
    """Write the collection: every item to its file (kept name, so links stay), items no longer in the list moved to
    Arquivo-morto/ (never deleted), the folder's index rewritten. {escritos, arquivados}."""
    existentes = _arquivos(colecao)
    pasta = RAIZ / COLECOES[colecao]
    escritos = arquivados = 0
    vivos = set()
    for item in itens:
        ident = str(item.get("id"))
        vivos.add(ident)
        f = existentes.get(ident, (None,))[0]
        if f is None:
            f = pasta / _nome_arquivo(colecao, item)
        elif not f.name.startswith(prefixo(ident) + "-"):  # an unsafe name from before: give it the safe one
            novo = pasta / _nome_arquivo(colecao, item)
            os.replace(f, novo)
            f = novo
        campos = {k: v for k, v in item.items() if not str(k).startswith("_") and k not in DERIVADOS}
        campos["status"] = str(item.get("estado") or "aberto")
        campos["tags"] = [colecao[:-1] if colecao != "decisoes" else "decisao", slug(item.get("area") or "geral")]
        if escrever(f, frontmatter(campos) + corpo(colecao, item)):
            escritos += 1
    for ident, (f, _c) in existentes.items():
        if ident not in vivos:
            destino = RAIZ / "Arquivo-morto" / COLECOES[colecao] / f.name
            destino.parent.mkdir(parents=True, exist_ok=True)
            os.replace(f, destino)
            arquivados += 1
    escrever(pasta / "indice.md", indice(colecao, itens))
    return {"escritos": escritos, "arquivados": arquivados}


# ---------------------------------------------------------------- rendering
def titulo(colecao: str, item: dict) -> str:
    t = item.get("titulo") or item.get("valor") or item.get("tema") or str(item.get("id"))
    t = re.sub(r"\s+", " ", str(t)).strip()
    return t if len(t) <= 90 else t[:89] + "…"


def _quando(ts) -> str:
    try:
        return time.strftime("%d/%m/%Y", agora_local(float(ts)))
    except (TypeError, ValueError):
        return ""


def link(ref: str) -> str:
    """'decisao:35' / 'pendencia:7eed8c' / 'assunto:a1b2c3' -> [[Decisoes/0035-…]] (plain text when not found)."""
    tipo, _, ident = str(ref or "").partition(":")
    colecao = {"decisao": "decisoes", "pendencia": "pendencias", "assunto": "assuntos"}.get(tipo)
    if not colecao:
        return str(ref)
    pasta = RAIZ / COLECOES[colecao]
    inicio = prefixo(ident) + "-"
    achado = next((f for f in sorted(pasta.iterdir()) if f.name.startswith(inicio) and f.suffix == ".md"),
                  None) if pasta.exists() else None
    return f"[[{COLECOES[colecao]}/{achado.stem}]]" if achado else str(ref)


def _ligacoes(item: dict) -> list[str]:
    refs = item.get("liga") or []
    linhas = [f"- {link(r)}" for r in refs if r]
    if item.get("ligacoes"):  # free text kept from the old loose-ends register
        linhas.append(f"- {item['ligacoes']}")
    return linhas


def corpo(colecao: str, item: dict) -> str:
    partes = [f"# {titulo(colecao, item)}", ""]
    area = item.get("area") or "geral"
    if colecao == "decisoes":
        partes += [str(item.get("valor") or ""), ""]
        if item.get("citacao"):
            partes += [f"> \"{item['citacao']}\" (Matheus)", ""]
        partes.append(f"- Tipo: {item.get('tipo', 'decisao')} · Área: {area} · Estado: {item.get('estado', 'ativa')}"
                      f" · Desde {_quando(item.get('em'))}")
        if item.get("substitui"):
            partes.append(f"- Substitui: {link('decisao:' + str(item['substitui']))}")
        if item.get("substituida_por"):
            partes.append(f"- Substituída por: {link('decisao:' + str(item['substituida_por']))}")
    elif colecao == "pendencias":
        if item.get("detalhe"):
            partes += [str(item["detalhe"]), ""]
        extras = [f"Estado: {item.get('estado', 'aberto')}", f"Área: {area}"]
        extras += [f"{rotulo}: {item[k]}" for k, rotulo in (("prazo", "Prazo"), ("dono", "De quem"),
                                                             ("prioridade", "Prioridade")) if item.get(k)]
        partes.append("- " + " · ".join(extras) + f" · Desde {_quando(item.get('criado'))}")
        if item.get("proximo_passo"):
            partes.append(f"- Próximo passo: {item['proximo_passo']}")
        if item.get("prova"):
            partes.append(f"- Feita: {item['prova']}")
    else:
        partes += [f"**Onde parou:** {item.get('onde_parou') or '(ainda nada)'}", "",
                   f"- Estado: {item.get('estado', 'andamento')} · Área: {area} · Desde {_quando(item.get('criado'))}", ""]
        historico = item.get("historico") or []
        if historico:
            partes += ["## Histórico"] + [f"- {_quando(h.get('em'))}: {h.get('nota', '')}" for h in historico[-30:]]
    ligacoes = _ligacoes(item)
    if ligacoes:
        partes += ["", "## Ligações"] + ligacoes
    if item.get("origem"):
        partes += ["", f"_Origem: {item['origem']}_"]
    return "\n".join(partes).rstrip() + "\n"


def indice(colecao: str, itens: list[dict]) -> str:
    nome = COLECOES[colecao]
    linhas = [f"# {nome.replace('-', ' ')}", "", f"{len(itens)} itens. Cada um é um arquivo desta pasta.", ""]
    for item in sorted(itens, key=lambda x: (str(x.get("estado")) not in ("ativa", "aberto", "andamento"),
                                             str(x.get("id")).zfill(8))):
        ref = {"decisoes": "decisao", "pendencias": "pendencia", "assuntos": "assunto"}[colecao]
        linhas.append(f"- {link(ref + ':' + str(item.get('id')))} — {item.get('estado', '')}"
                      f" · {item.get('area') or 'geral'}")
    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------- the folder itself
CLAUDE_MD = """# Segundo Cérebro do Matheus

Leia isto antes de usar a Pasta. Ela é a única fonte: o que não está aqui não foi registrado.

## Regras
1. Leia `Contexto/` antes de trabalhar em qualquer coisa de negócio; `perfil.md` diz como trabalhar com o Matheus.
2. Nunca invente: o que falta fica marcado [PENDENTE DE VALIDAÇÃO] até ele confirmar.
3. Quem escreve é o agente, pelas ferramentas (decisao, fios, cerebro, ficha); ninguém edita estes arquivos à mão.
4. Decisão = escolha feita que vale daqui para a frente. Pendência = o que falta ele fazer. Assunto = tema em discussão,
   com onde parou. Cada item tem a área (Raiz, NEXOS, Orbyte, pessoal…).
5. Nada se apaga: o que sai vai para `Arquivo-morto/`.

## Mapa
| Pasta | O que tem |
|---|---|
| Contexto/ | organização, marca, estratégia, cliente ideal, pessoas-chave, perfil |
| Decisoes/ | uma decisão por arquivo, com a citação dele e o que substituiu |
| Pendencias/ | o que falta fazer, com prazo e de onde veio |
| Assuntos/ | temas em andamento e onde pararam |
| Reunioes/ | resumo de cada reunião com decisões e próximos passos |
| Notas-do-dia/ | uma nota por dia, escrita às 20h |
| Projetos/ | uma pasta por projeto real, quando precisar |
| Documentos/ | documentos de referência e relatórios (ex.: auditorias) |
| Arquivo-morto/ | o que saiu (desfeito, substituído, os registros antigos) |
"""


def estrutura() -> list[str]:
    """Create what is missing (folders, CLAUDE.md, the six context files as pending). Never overwrites content."""
    criados = []
    RAIZ.mkdir(parents=True, exist_ok=True)
    for p in PASTAS:
        if not (RAIZ / p).exists():
            (RAIZ / p).mkdir(parents=True)
            criados.append(p + "/")
    if not (RAIZ / "CLAUDE.md").exists():
        escrever(RAIZ / "CLAUDE.md", CLAUDE_MD)
        criados.append("CLAUDE.md")
    for nome, (tit, oque) in CONTEXTO.items():
        f = RAIZ / "Contexto" / nome
        if not f.exists():
            escrever(f, frontmatter({"status": "pendente", "tags": ["contexto", slug(tit)]}) +
                     f"# {tit}\n\n{PENDENTE}\n\nO que vai aqui: {oque}.\n")
            criados.append(f"Contexto/{nome}")
    escrever(RAIZ / "Contexto" / "indice.md", "# Contexto\n\n" + "\n".join(
        f"- [[Contexto/{n[:-3]}]] — {t}" for n, (t, _o) in CONTEXTO.items()) + "\n")
    return criados


def contexto_pendente() -> list[str]:
    """Context files the interview has not filled yet, in the guide's order."""
    faltam = []
    for nome in CONTEXTO:
        f = RAIZ / "Contexto" / nome
        if not f.exists() or PENDENTE in f.read_text(encoding="utf-8"):
            faltam.append(nome)
    return faltam


def gravar_contexto(nome: str, conteudo: str, aprovado_por: str) -> str:
    """One context section, only after Matheus approved the summary (the interview). perfil.md belongs to `ficha`."""
    if nome not in CONTEXTO or nome == "perfil.md":
        raise ValueError(f"seção desconhecida ou da ficha: {nome}")
    if not str(aprovado_por or "").strip():
        raise ValueError("só grava depois do ok dele (aprovado_por com as palavras dele)")
    texto = str(conteudo or "").strip()
    if len(texto) < 20:
        raise ValueError("conteúdo curto demais")
    tit = CONTEXTO[nome][0]
    corpo_ = texto if texto.startswith("#") else f"# {tit}\n\n{texto}"
    escrever(RAIZ / "Contexto" / nome, frontmatter({"status": "validado", "tags": ["contexto", slug(tit)],
                                                     "aprovado": str(aprovado_por)[:200], "em": time.time()})
             + corpo_.rstrip() + "\n")
    return f"Contexto/{nome}"


def versionar(motivo: str = "atualização") -> bool:
    """A git commit of the Pasta (its history: any version can come back). False when there was nothing new."""
    if not (RAIZ / ".git").exists():
        subprocess.run(["git", "init", "-q", str(RAIZ)], capture_output=True, timeout=30)
        subprocess.run(["git", "-C", str(RAIZ), "config", "user.name", "Agente do Matheus"], capture_output=True)
        subprocess.run(["git", "-C", str(RAIZ), "config", "user.email", "agente@raizconnect.com.br"], capture_output=True)
        escrever(RAIZ / ".gitignore", "*.lock\n.*.tmp\n")
    subprocess.run(["git", "-C", str(RAIZ), "add", "-A"], capture_output=True, timeout=60)
    r = subprocess.run(["git", "-C", str(RAIZ), "commit", "-q", "-m", str(motivo)[:200]], capture_output=True, timeout=60)
    return r.returncode == 0


def enviar_copia(token: str) -> str:
    """Push the Pasta's history to its private GitHub repository (remote "origin", set once by the operator). The token
    goes only in this one command's header, never into .git/config (the Pasta is also backed up to S3). '' when ok."""
    if not token:
        return "sem token do GitHub no cofre"
    if subprocess.run(["git", "-C", str(RAIZ), "remote", "get-url", "origin"], capture_output=True).returncode:
        return "a Pasta ainda não tem repositório no GitHub (operador: cerebro.py copia-github)"
    versionar("cópia diária")
    import base64
    basico = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    r = subprocess.run(["git", "-C", str(RAIZ), "-c", f"http.extraHeader=Authorization: Basic {basico}", "push", "-q",
                        "origin", "HEAD:main"], capture_output=True, timeout=300)
    return "" if r.returncode == 0 else f"push falhou ({r.returncode})"


# ---------------------------------------------------------------- reading
def buscar(texto: str, limite: int = 12) -> list[dict]:
    """Notes whose text has every word searched (accents ignored), Arquivo-morto left out; best titles first."""
    palavras = [p for p in slug(texto, 200).split("-") if len(p) > 1]
    achados = []
    for f in RAIZ.rglob("*.md"):
        rel = f.relative_to(RAIZ)
        if rel.parts[0] in ("Arquivo-morto",) or f.name == "indice.md" or rel.parts[0].startswith("."):
            continue
        conteudo = f.read_text(encoding="utf-8", errors="ignore")
        alvo = slug(conteudo, 10 ** 7)
        if all(p in alvo for p in palavras):
            linha_tit = next((l[2:] for l in conteudo.splitlines() if l.startswith("# ")), f.stem)
            nota = slug(linha_tit, 300)
            achados.append({"nota": str(rel.with_suffix("")), "titulo": linha_tit,
                            "pontos": sum(p in nota for p in palavras), "trecho": _trecho(conteudo, palavras)})
    achados.sort(key=lambda a: -a["pontos"])
    return achados[:limite]


def _trecho(conteudo: str, palavras: list) -> str:
    corpo_ = conteudo.split("\n---\n", 1)[-1]
    for l in corpo_.splitlines():
        if any(p in slug(l, 10 ** 4) for p in palavras) and not l.startswith("#"):
            return l.strip()[:240]
    return corpo_.strip().splitlines()[0][:240] if corpo_.strip() else ""

"""Cérebro da Raiz (20/10, glossary): the part of the Pasta that is only about the company Raiz, in Raiz/ (mapa, oferta,
cliente-ideal, marca, concorrentes, playbook), read by the prospecção, the posts and the especialistas. One file per
subject; this module is the only writer.

- estrutura(): creates what is missing (the folder, the map, the other files as [PENDENTE DE VALIDAÇÃO], the index and
  the Raiz/ line of CLAUDE.md's map). Never overwrites a file.
- semear(por): fills the files ONCE from what the repository already knows (the prospecção playbook, the competitor
  list); what has no source stays PENDENTE for the interview. Refuses a second time (marker Raiz/.semeado).
- gravar(nome, conteudo, aprovado_por): a file rewritten only with Matheus's ok, versioned (pasta.versionar).
- ler(nome) / contexto(nomes, limite): compact text for prompts and especialistas (contexto never passes `limite`)."""

import importlib.util
import json
import re
import sys
import time
from pathlib import Path

PASTA = "Raiz"
ARQUIVOS = {  # file -> (title, what goes in it); the interface other plugins rely on: <Pasta>/Raiz/<nome>.md
    "mapa.md": ("Mapa da Raiz", "o que é a Raiz e onde mora cada coisa"),
    "oferta.md": ("Oferta", "o Lucro na Mão em 30 Dias: promessa, o que entra, preço, garantia, vagas, links"),
    "cliente-ideal.md": ("Cliente ideal", "quem compra, perfil, sinais, quem está fora"),
    "marca.md": ("Marca", "posicionamento, voz, identidade visual, o que nunca dizer"),
    "concorrentes.md": ("Concorrentes", "quem a Raiz vigia, por grupo"),
    "playbook.md": ("Playbook de prospecção", "resumo do playbook e onde está o inteiro"),
}
ORDEM_CONTEXTO = ("oferta.md", "cliente-ideal.md", "marca.md", "concorrentes.md", "playbook.md", "mapa.md")
MARCA_SEMEADO = ".semeado"
PLAYBOOK_REPO = "plugins/prospeccao/playbook.md"
_AQUI = Path(__file__).resolve().parents[1]
# next to this plugin (repository, live install); a staging copy alone in /tmp reads the installed ones
PLUGINS = _AQUI.parent if (_AQUI.parent / "prospeccao").exists() else Path("/a0/usr/plugins")
LINHA_MAPA = "| Raiz/ | Cérebro da Raiz: mapa, oferta, cliente ideal, marca, concorrentes, playbook (leia `mapa.md`) |"

MAPA = """# Mapa da Raiz

A **Raiz Connect** é a empresa do Matheus que faz o sistema de custo, preço e estoque para quem produz comida (ficha
técnica, custo, CMV, estoque, vendas, nota fiscal e a assistente Fernanda). A porta de entrada que ela vende é o
**Lucro na Mão em 30 Dias**: em 30 dias o produtor sabe quanto sobra em cada produto e onde o dinheiro escapa, com a
implementação feita pela Raiz e o Raiz Connect como ferramenta. Esta pasta é o **Cérebro da Raiz**: só a empresa Raiz, lida pela prospecção,
pelos posts e pelos especialistas. O resto da vida do Matheus está no restante da Pasta.

## Onde mora cada coisa
| Arquivo | O que tem | Quem usa |
|---|---|---|
| [[Raiz/oferta]] | a oferta, preço, garantia, vagas e links | prospecção (respostas), posts (`conteudo`), especialistas |
| [[Raiz/cliente-ideal]] | quem compra, sinais, quem está fora | prospecção (busca e nota do lead), posts |
| [[Raiz/marca]] | posicionamento, voz e identidade visual | posts, carrosséis e vídeos, Designer e Crítico |
| [[Raiz/concorrentes]] | quem a Raiz vigia, por grupo | plugin `concorrentes`, rotina semanal "Concorrentes — semana" |
| [[Raiz/playbook]] | resumo do playbook de prospecção | prospecção, revisor das mensagens |

## Fontes (onde está o inteiro)
- Playbook inteiro: `plugins/prospeccao/playbook.md` (na VM, `/a0/usr/plugins/prospeccao/playbook.md`), lido pela
  ferramenta `prospeccao` e pelo revisor de cada mensagem.
- Lista viva de concorrentes: `/a0/usr/concorrentes/lista.json` (ferramenta `concorrentes`; rotina semanal de quarta).
- Posts da @raiz.connect: plugin `conteudo` (agenda e desempenho); rotinas do marketing: números da semana (segunda),
  revisão do mês (dia 1).
- Decisões da Raiz: `Decisoes/` com área raiz (`cerebro` acao=consultar "raiz …").

## Regras
- Para qualquer coisa da Raiz (prospecção, posts, oferta), leia antes `cerebro` acao=raiz.
- O que está marcado como pendente de validação ainda não foi confirmado pelo Matheus: não afirme como fato.
- Mudança num arquivo daqui só com o ok dele (`cerebro` acao=raiz secao=… conteudo=… aprovado=…).
"""


def pasta():
    nome = "cerebro_pasta"
    caminho = Path(__file__).resolve().parent / "pasta.py"
    antigo = sys.modules.get(nome)
    if antigo is None or getattr(antigo, "_mtime", None) != caminho.stat().st_mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = caminho.stat().st_mtime
        if antigo is not None and hasattr(antigo, "RAIZ"):
            modulo.RAIZ = antigo.RAIZ
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _concorrentes():
    """The concorrentes plugin's helper (read only: carregar() is its live list, or its SEMENTE before any change)."""
    nome = "cerebro_concorrentes"
    if nome not in sys.modules:
        caminho = PLUGINS / "concorrentes" / "helpers" / "concorrentes.py"
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _nome(nome: str) -> str:
    n = str(nome or "").strip().lower()
    n = n if n.endswith(".md") else f"{n}.md"
    if n not in ARQUIVOS:
        raise ValueError(f"arquivo da Raiz desconhecido: {nome} (são {', '.join(a[:-3] for a in ARQUIVOS)})")
    return n


def _dir() -> Path:
    return pasta().RAIZ / PASTA


def _cabecalho(nome: str, **campos) -> str:
    p = pasta()
    return p.frontmatter({"tags": ["raiz", p.slug(ARQUIVOS[nome][0])], **campos})


# ---------------------------------------------------------------- the folder
def estrutura() -> list[str]:
    """Create what is missing; never overwrites a file (CLAUDE.md only gains the Raiz/ line of its map)."""
    p = pasta()
    p.RAIZ.mkdir(parents=True, exist_ok=True)
    criados = []
    if not _dir().exists():
        _dir().mkdir(parents=True)
        criados.append(f"{PASTA}/")
    for nome, (tit, oque) in ARQUIVOS.items():
        f = _dir() / nome
        if f.exists():
            continue
        if nome == "mapa.md":
            p.escrever(f, _cabecalho(nome, status="validado") + MAPA)
        else:
            p.escrever(f, _cabecalho(nome, status="pendente") + f"# {tit}\n\n{p.PENDENTE}\n\nO que vai aqui: {oque}.\n")
        criados.append(f"{PASTA}/{nome}")
    p.escrever(_dir() / "indice.md", f"# {PASTA}\n\nO Cérebro da Raiz. Comece pelo mapa.\n\n" + "\n".join(
        f"- [[{PASTA}/{n[:-3]}]] — {t}" for n, (t, _o) in ARQUIVOS.items()) + "\n")
    claude = p.RAIZ / "CLAUDE.md"
    if claude.exists():
        texto = claude.read_text(encoding="utf-8")
        if f"| {PASTA}/ |" not in texto:  # the map row (the rules may cite Raiz/ too)
            linhas = texto.rstrip("\n").split("\n")
            depois = max((i for i, l in enumerate(linhas) if l.startswith("| Contexto/")), default=len(linhas) - 1)
            linhas.insert(depois + 1, LINHA_MAPA)
            p.escrever(claude, "\n".join(linhas) + "\n")
            criados.append("CLAUDE.md (linha Raiz/ no mapa)")
    return criados


def pendentes() -> list[str]:
    """Files still waiting for Matheus (missing or with the PENDENTE marker)."""
    p = pasta()
    return [n for n in ARQUIVOS if not (_dir() / n).exists() or p.PENDENTE in (_dir() / n).read_text(encoding="utf-8")]


# ---------------------------------------------------------------- reading
def _corpo(texto: str) -> str:
    if texto.startswith("---\n"):
        fim = texto.find("\n---\n", 4)
        texto = texto[fim + 5:] if fim >= 0 else texto
    return texto.strip()


def ler(nome: str) -> str:
    """The body of one file (no header); '' when it does not exist yet."""
    f = _dir() / _nome(nome)
    return _corpo(f.read_text(encoding="utf-8")) if f.exists() else ""


def _compacto(texto: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", "\n".join(l.rstrip() for l in texto.splitlines())).strip()


def contexto(nomes: list | None = None, limite: int = 6000) -> str:
    """Compact text of the Raiz files for a prompt or an especialista, never longer than `limite` characters. Each file
    gets a fair share; a short one leaves its share to the others; a cut one says where the whole is."""
    lista = [_nome(n) for n in nomes] if nomes else list(ORDEM_CONTEXTO)
    limite = max(200, int(limite))
    partes = []
    for n in lista:
        corpo = _compacto(ler(n)) or f"{pasta().PENDENTE} (ainda não criado)"
        partes.append((n, f"### {PASTA}/{n}\n{corpo}"))
    sep = "\n\n"
    folga = limite - len(sep) * max(0, len(partes) - 1)
    cotas = {}
    restantes = sorted(partes, key=lambda x: len(x[1]))
    while restantes:
        cota = folga // len(restantes)
        n, t = restantes.pop(0)
        cotas[n] = min(len(t), cota)
        folga -= cotas[n]
    saida = []
    for n, t in partes:
        if len(t) > cotas[n]:
            aviso = f"\n…(cortado; o inteiro em {PASTA}/{n})"
            t = t[:max(0, cotas[n] - len(aviso))].rstrip() + aviso
            t = t[:cotas[n]]
        saida.append(t)
    return sep.join(saida)[:limite]


# ---------------------------------------------------------------- writing
def gravar(nome: str, conteudo: str, aprovado_por: str) -> str:
    """One file, only after Matheus approved it (his words in aprovado_por); the old version stays in the history."""
    p = pasta()
    nome = _nome(nome)
    if not str(aprovado_por or "").strip():
        raise ValueError("só grava depois do ok dele (aprovado_por com as palavras dele)")
    texto = str(conteudo or "").strip()
    if len(texto) < 20:
        raise ValueError("conteúdo curto demais")
    estrutura()
    tit = ARQUIVOS[nome][0]
    corpo = texto if texto.startswith("#") else f"# {tit}\n\n{texto}"
    p.escrever(_dir() / nome, _cabecalho(nome, status="validado", aprovado=str(aprovado_por)[:200], em=time.time())
               + corpo.rstrip() + "\n")
    p.versionar(f"raiz: {PASTA}/{nome} (com o ok dele)")
    return f"{PASTA}/{nome}"


def _secoes(texto: str) -> dict:
    """'## 2. Oferta e links' -> {'2': (title, body)} of a playbook-like Markdown."""
    achados = {}
    blocos = re.split(r"^## ", texto, flags=re.M)
    for b in blocos[1:]:
        cab, _, corpo = b.partition("\n")
        m = re.match(r"(\d+)\.\s*(.*)", cab.strip())
        if m:
            achados[m.group(1)] = (m.group(2).strip(), corpo.strip())
    return achados


def _item(corpo: str, comeco: str) -> str:
    """One '- **…' bullet (with its continuation lines) of a section."""
    linhas, dentro = [], False
    for l in corpo.splitlines():
        if l.startswith("- "):
            dentro = l.startswith(comeco)
        if dentro:
            linhas.append(l)
    return "\n".join(linhas)


def _de_playbook(pb: str) -> dict:
    """oferta, cliente-ideal, playbook and the voice part of marca, from the prospecção playbook."""
    s = _secoes(pb)
    fonte = f"`{PLAYBOOK_REPO}`"
    out = {}
    if "2" in s:
        extra = "\n".join(x for x in (_item(s.get("7", ("", ""))[1], "- **Planos"),
                                      _item(s.get("7", ("", ""))[1], "- **Lucro na Mão")) if x)
        out["oferta.md"] = (f"# Oferta: Lucro na Mão em 30 Dias\n\n_Do playbook de prospecção ({fonte}, seção 2"
                            f"{' e 7' if extra else ''}); o inteiro manda._\n\n" + s["2"][1]
                            + (f"\n\n## Fatos da seção 7\n{extra}" if extra else ""))
    if "1" in s:
        out["cliente-ideal.md"] = f"# Cliente ideal\n\n_Do playbook de prospecção ({fonte}, seção 1)._\n\n{s['1'][1]}"
    intro = pb.split("\n## ", 1)[0].split("\n", 1)[-1].strip()
    indice = "\n".join(f"{k}. {t}" for k, (t, _c) in s.items())
    out["playbook.md"] = (f"# Playbook de prospecção\n\nO inteiro: {fonte} (na VM, `/a0/usr/plugins/prospeccao/playbook.md`); "
                          "a ferramenta `prospeccao` acao \"playbook\" lê ele, e o revisor confere cada mensagem contra ele."
                          f"\n\n## Resumo\n{intro}\n\n## Seções\n{indice}"
                          + (f"\n\n## O que conta como resultado\n{s['8'][1]}" if "8" in s else ""))
    if "3" in s:
        out["_voz"] = s["3"][1]
    return out


def _lista_concorrentes() -> tuple[str, str]:
    """(markdown list by group, source) from the concorrentes plugin; ('', why) when it cannot be read."""
    try:
        c = _concorrentes()
        lista = c.carregar().get("concorrentes") or []
        grupos = getattr(c, "GRUPOS", {})
        viva = (Path(c.PASTA) / "lista.json").exists()
    except Exception as exc:  # noqa: BLE001 - an unreadable source is PENDENTE, never an invented list
        return "", f"lista do plugin concorrentes ilegível ({type(exc).__name__})"
    if not lista:
        return "", "lista do plugin concorrentes vazia"
    linhas = []
    for g in list(grupos) + sorted({x.get("grupo") or "?" for x in lista} - set(grupos)):
        dele = [x for x in lista if (x.get("grupo") or "?") == g]
        if not dele:
            continue
        linhas += ["", f"## {grupos.get(g, g)}"]
        for x in dele:
            seg = re.sub(r"\s+", " ", str(x.get("segmento") or "")).strip()
            linhas.append(f"- **{x.get('nome') or x.get('id')}**" + (f": {seg[:160]}{'…' if len(seg) > 160 else ''}" if seg else ""))
    fonte = ("lista viva do plugin concorrentes (/a0/usr/concorrentes/lista.json)" if viva
             else "lista inicial do plugin concorrentes (SEMENTE de plugins/concorrentes/helpers/concorrentes.py)")
    return "\n".join(linhas).strip(), fonte


def semear(por: str, marca_visual: str = "", playbook: str | None = None) -> dict:
    """Fill the Raiz files ONCE from the repository's sources; a file Matheus already approved is left alone; what has
    no source keeps the PENDENTE marker. `marca_visual` is the brand identity notes the operator reads from the
    repository (infra/reels), which are not on the VM. Refuses a second time."""
    p = pasta()
    if not str(por or "").strip():
        raise ValueError("diga quem semeia (por=\"operador: <motivo>\")")
    marca_arq = _dir() / MARCA_SEMEADO
    if marca_arq.exists():
        raise RuntimeError(f"o Cérebro da Raiz já foi semeado ({marca_arq.read_text(encoding='utf-8')[:200]})")
    estrutura()
    if playbook is None:
        arq = PLUGINS / "prospeccao" / "playbook.md"
        playbook = arq.read_text(encoding="utf-8") if arq.exists() else ""
    textos = _de_playbook(playbook) if playbook.strip() else {}
    fontes = {n: PLAYBOOK_REPO for n in ("oferta.md", "cliente-ideal.md", "playbook.md") if n in textos}
    lista, fonte_lista = _lista_concorrentes()
    if lista:
        textos["concorrentes.md"] = (f"# Concorrentes\n\n_Fonte: {fonte_lista}; quem muda a lista é a ferramenta "
                                     "`concorrentes`, e a vigia semanal (quarta) traz o que mudou._\n\n" + lista)
        fontes["concorrentes.md"] = fonte_lista
    voz, visual = textos.pop("_voz", ""), str(marca_visual or "").strip()
    if voz or visual:
        textos["marca.md"] = "\n\n".join([
            "# Marca",
            f"## Posicionamento\n{p.PENDENTE}\n\nComo a Raiz quer ser vista e o que nunca dizer, nas palavras dele "
            "(a entrevista preenche).",
            f"## Voz nas mensagens (playbook, seção 3)\n{voz}" if voz else f"## Voz nas mensagens\n{p.PENDENTE}",
            f"## Identidade visual (posts, carrosséis e vídeos)\n{visual}" if visual else
            f"## Identidade visual (posts, carrosséis e vídeos)\n{p.PENDENTE}"])
        fontes["marca.md"] = ", ".join(x for x in (PLAYBOOK_REPO + " §3" if voz else "",
                                                   "infra/reels (operador)" if visual else "") if x)
    feitos, pulados = [], []
    for nome, texto in textos.items():
        f = _dir() / nome
        atual = f.read_text(encoding="utf-8") if f.exists() else ""
        if atual and 'status: "validado"' in atual.split("\n---\n", 1)[0]:
            pulados.append(nome)  # his approved version wins
            continue
        estado = "pendente" if p.PENDENTE in texto else "semeado"
        p.escrever(f, _cabecalho(nome, status=estado, fonte=fontes.get(nome, ""), por=str(por)[:200], em=time.time())
                   + texto.rstrip() + "\n")
        feitos.append(nome)
    resumo = {"semeados": feitos, "pulados": pulados, "pendentes": pendentes()}
    p.escrever(marca_arq, json.dumps({"em": time.time(), "por": por, **resumo}, ensure_ascii=False))
    p.versionar(f"Cérebro da Raiz semeado ({por})")
    return resumo

"""Competitor watch (14/10, from Hermes Agent's competitor-news-monitor skill, MIT): a list of competitors with their
sources (site, pricing page, blog/RSS, press), a collection that finds and reads the feeds, compares with the last
round, groups what came from several sources into one fact and returns only what is new.

Rules that are code, not text:
- a source that failed is "sem cobertura" (unknown), never "sem notícia": its state does not move, so what appeared in
  the meantime still shows up as new on the next round that reads it;
- the first good read of a source is the baseline (nothing in it is "new");
- the list only changes through this file (validated, written whole, logged in diario.jsonl).
State in /a0/usr/concorrentes/: lista.json (the list), estado.json (what each source showed), rodadas.jsonl (results)."""

import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path

PASTA = Path(os.environ.get("CONCORRENTES_PASTA", "/a0/usr/concorrentes"))
TIPOS = ("site", "precos", "blog", "rss", "imprensa")
AUTOR = {"quem": "agente"}  # operator scripts set "operador: <why>"
NAVEGADOR = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
MAX_VISTOS = 400            # item keys kept per source
IDADE_MAX = 30 * 86400      # a feed entry older than this is never "new" (feeds re-list old posts)
MAX_ITENS = 40              # entries read per source and round
PRECO = re.compile(r"R\$\s?\d{1,3}(?:\.\d{3})*(?:,\d{2})?")


def _feed():
    nome = "concorrentes_feed"
    caminho = Path(__file__).resolve().parent / "feed.py"
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        sys.modules[nome] = m
    return sys.modules[nome]


def imprensa(termo: str) -> str:
    """Google News search as RSS (no key; answers from the VM), in Portuguese, Brazil."""
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": termo, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"})


# The starting list (14/10/2026): management and pricing systems for food producers, confectioners and lunchbox
# kitchens in Brazil. Each one with where it was found ("pesquisa"); prices as seen that day.
SEMENTE = [
    {"id": "saipos", "nome": "Saipos", "segmento": "sistema para restaurante, delivery e marmitaria: CMV teórico x real, "
     "estoque, DRE; plano mensal a partir de R$ 240,79 (14/10/2026)",
     "fontes": [{"tipo": "site", "url": "https://saipos.com/sistema/marmitaria"},
                {"tipo": "precos", "url": "https://saipos.com/planos-e-precos"},
                {"tipo": "blog", "url": "https://saipos.com/gestao"},
                {"tipo": "imprensa", "url": imprensa('"Saipos"')}],
     "pesquisa": ["https://saipos.com/sistema/marmitaria", "https://saipos.com/planos-e-precos"]},
    {"id": "chefpro", "nome": "ChefPro", "segmento": "ficha técnica e custo de receitas (restaurante, confeitaria, "
     "marmitaria, padaria); assinatura anual de R$ 69 a R$ 249 (07/2024)",
     "fontes": [{"tipo": "site", "url": "https://chefproapp.com/"},
                {"tipo": "blog", "url": "https://app.chefproapp.com/blog"},
                {"tipo": "imprensa", "url": imprensa('"ChefPro" ficha técnica')}],
     "pesquisa": ["https://chefproapp.com/",
                  "https://startups.com.br/alem-da-faria-lima/chefpro-se-prepara-para-escalar-com-app-que-cria-fichas-tecnicas-de-receitas/"]},
    {"id": "lucro_na_confeitaria", "nome": "Lucro na Confeitaria", "segmento": "app de precificação para confeiteiras "
     "(receitas, orçamento em PDF, agenda de pedidos); premium R$ 20,90/mês ou R$ 199,90/ano (14/10/2026)",
     "fontes": [{"tipo": "site", "url": "https://www.lucronaconfeitaria.com"},
                {"tipo": "precos", "url": "https://www.lucronaconfeitaria.com/planos"},
                {"tipo": "precos", "url": "https://apps.apple.com/br/app/lucro-na-confeitaria/id1571185374"},
                {"tipo": "imprensa", "url": imprensa('"Lucro na Confeitaria"')}],
     "pesquisa": ["https://www.lucronaconfeitaria.com", "https://apps.apple.com/BR/app/id1571185374"]},
    {"id": "viver_de_confeitaria", "nome": "Gestão Viver de Confeitaria", "segmento": "app de precificação da AEF "
     "Digital, com o blog Viver de Confeitaria (que indica o Gestly ERP); R$ 14,90/mês ou R$ 99,90/ano (14/10/2026)",
     "fontes": [{"tipo": "blog", "url": "https://viverdeconfeitaria.com.br"},
                {"tipo": "precos", "url": "https://apps.apple.com/br/app/id1636351373"},
                {"tipo": "imprensa", "url": imprensa('"Viver de Confeitaria"')}],
     "pesquisa": ["https://apps.apple.com/BR/app/id1636351373", "https://viverdeconfeitaria.com.br"]},
    {"id": "precifica", "nome": "Precifica: Preço e Lucro", "segmento": "app de precificação de bolos, doces e salgados "
     "(ingrediente, embalagem, gás, energia, mão de obra; orçamento em PDF), da PediPedi",
     "fontes": [{"tipo": "site", "url": "https://www.pedipedi.com.br"},
                {"tipo": "precos", "url": "https://apps.apple.com/br/app/precifica/id6756502357"}],
     "pesquisa": ["https://apps.apple.com/br/app/precifica/id6756502357"]},
    {"id": "docepreco", "nome": "DocePreço", "segmento": "app de precificação para confeiteiras (lançado em 2026); "
     "premium R$ 19,90/mês, master R$ 39,90/mês (14/10/2026)",
     "fontes": [{"tipo": "site", "url": "https://docepreco.site/"},
                {"tipo": "precos", "url": "https://apps.apple.com/br/app/id6761034172"}],
     "pesquisa": ["https://apps.apple.com/br/app/id6761034172", "https://mwm.ai/apps/docepreo/6761034172"]},
]


# ------------------------------------------------------------------ files

@contextmanager
def _exclusivo():
    PASTA.mkdir(parents=True, exist_ok=True)
    with open(PASTA / "concorrentes.lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _ler(nome: str, vazio: dict) -> dict:
    arq = PASTA / nome
    if not arq.exists():
        return vazio
    d = json.loads(arq.read_text(encoding="utf-8"))  # unreadable: raise, never start empty
    if not isinstance(d, dict):
        raise ValueError(f"{nome} ilegível")
    return d


def _gravar(nome: str, d: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    tmp = PASTA / f"{nome}.{os.getpid()}.{time.time_ns()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, PASTA / nome)


def _diario(evento: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    with open(PASTA / "diario.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"em": time.time(), "quem": AUTOR["quem"], **evento}, ensure_ascii=False) + "\n")


def carregar() -> dict:
    """The list; the starting one until it is first changed."""
    d = _ler("lista.json", {"concorrentes": json.loads(json.dumps(SEMENTE))})
    if not isinstance(d.get("concorrentes"), list):
        raise ValueError("lista.json ilegível")
    d.setdefault("removidos", [])
    return d


# ------------------------------------------------------------------ editing the list (the agent's tool)

def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:40]


def _validar_fonte(fonte: dict) -> dict:
    tipo = str((fonte or {}).get("tipo") or "").strip().lower()
    url = str((fonte or {}).get("url") or "").strip()
    if tipo not in TIPOS:
        raise ValueError(f"tipo de fonte '{tipo}' não existe (use {', '.join(TIPOS)})")
    if tipo == "imprensa" and url and not url.startswith(("http://", "https://")):
        url = imprensa(url)  # a search term: Google News for it
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or "." not in p.hostname:
        raise ValueError(f"endereço inválido: {url!r}")
    return {"tipo": tipo, "url": url}


def _achar(d: dict, cid: str) -> dict:
    for c in d["concorrentes"]:
        if c["id"] == cid:
            return c
    raise ValueError(f"concorrente '{cid}' não está na lista")


def adicionar(nome: str, segmento: str = "", fontes: list | None = None, pesquisa: list | None = None) -> dict:
    nome = " ".join(str(nome or "").split())[:80]
    cid = _slug(nome)
    if not cid:
        raise ValueError("informe o nome do concorrente")
    validas = [_validar_fonte(f) for f in fontes or []]
    if not validas:
        raise ValueError("informe ao menos uma fonte (tipo e url)")
    with _exclusivo():
        d = carregar()
        if any(c["id"] == cid for c in d["concorrentes"]):
            raise ValueError(f"'{nome}' já está na lista (id {cid})")
        novo = {"id": cid, "nome": nome, "segmento": str(segmento or "")[:300], "fontes": validas,
                "pesquisa": [str(u) for u in pesquisa or []][:10]}
        d["concorrentes"].append(novo)
        _gravar("lista.json", d)
        _diario({"acao": "adicionar", "id": cid, "novo": novo})
    return novo


def mudar_fonte(cid: str, fonte: dict, tirar: bool = False) -> dict:
    with _exclusivo():
        d = carregar()
        c = _achar(d, cid)
        f = _validar_fonte(fonte) if not tirar else {"url": str((fonte or {}).get("url") or "").strip()}
        if tirar:
            antes = len(c["fontes"])
            c["fontes"] = [x for x in c["fontes"] if x["url"] != f["url"]]
            if len(c["fontes"]) == antes:
                raise ValueError("essa fonte não está no concorrente")
            if not c["fontes"]:
                raise ValueError("o concorrente ficaria sem fonte; tire o concorrente em vez disso")
        elif any(x["url"] == f["url"] for x in c["fontes"]):
            raise ValueError("essa fonte já está no concorrente")
        else:
            c["fontes"].append(f)
        _gravar("lista.json", d)
        _diario({"acao": "tirar_fonte" if tirar else "fonte", "id": cid, "fonte": f})
    return c


def remover(cid: str, motivo: str = "") -> dict:
    """Out of the watch (kept under "removidos", so it can be looked up and put back)."""
    with _exclusivo():
        d = carregar()
        c = _achar(d, cid)
        d["concorrentes"] = [x for x in d["concorrentes"] if x["id"] != cid]
        d["removidos"].append({**c, "removido_em": time.time(), "motivo": str(motivo or "")[:200]})
        _gravar("lista.json", d)
        _diario({"acao": "remover", "id": cid, "motivo": motivo})
    return c


# ------------------------------------------------------------------ reading a source

def buscar(url: str, timeout: int = 20) -> tuple:
    """(status, body, content type); status 0 when it did not go through."""
    req = urllib.request.Request(url, headers={"User-Agent": NAVEGADOR, "Accept": "*/*",
                                               "Accept-Language": "pt-BR,pt;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(3_000_000), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, b"", ""
    except (urllib.error.URLError, OSError, ValueError):
        return 0, b"", ""


def _texto_visivel(html_bytes: bytes) -> str:
    t = html_bytes.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style|noscript|svg|template)\b.*?</\1>", " ", t)
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    return " ".join(_feed().strip_html(t).split())


def _links(url: str, html_bytes: bytes) -> list:
    """Links of the page to pages of the same site with a real title (a blog list without a feed)."""
    host = (urllib.parse.urlsplit(url).hostname or "").removeprefix("www.")
    vistos, saida = set(), []
    for m in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html_bytes.decode("utf-8", "replace")):
        link = urllib.parse.urljoin(url, m.group(1).strip())
        p = urllib.parse.urlsplit(link)
        titulo = _feed().strip_html(m.group(2))
        if (p.hostname or "").removeprefix("www.") != host or len(titulo) < 20 or p.path.rstrip("/") in ("", urllib.parse.urlsplit(url).path.rstrip("/")):
            continue
        chave = link.split("?")[0].rstrip("/")
        if chave not in vistos:
            vistos.add(chave)
            saida.append({"titulo": titulo[:200], "link": chave, "data": None, "resumo": ""})
    return saida[:MAX_ITENS]


def _de_feed(feed: dict) -> list:
    return [{"titulo": e.get("title") or "", "link": e.get("link") or "", "data": e.get("published"),
             "resumo": (e.get("summary") or "")[:400]} for e in (feed.get("entries") or [])[:MAX_ITENS]
            if e.get("title") or e.get("link")]


def ler_fonte(fonte: dict, busca=buscar) -> dict:
    """{"ok", "modo": feed|links|precos|pagina, "itens"|"precos"|"assinatura", "erro"}; never raises."""
    fd = _feed()
    tipo, url = fonte["tipo"], fonte["url"]
    try:
        status, corpo, ctype = busca(url)
        if status != 200 or not corpo:
            return {"ok": False, "erro": f"HTTP {status}" if status else "sem resposta"}
        if tipo == "precos":
            precos = sorted(set(p.replace(" ", "").replace("\xa0", "") for p in PRECO.findall(_texto_visivel(corpo))))
            if precos:
                return {"ok": True, "modo": "precos", "precos": precos}
            texto = _texto_visivel(corpo)
            if len(texto) < 200:
                return {"ok": False, "erro": "página sem texto legível (só carrega no navegador?)"}
            return {"ok": True, "modo": "pagina", "assinatura": hashlib.sha256(texto.encode()).hexdigest()[:16]}
        if fd.looks_like_feed(corpo, ctype):
            return {"ok": True, "modo": "feed", "itens": _de_feed(fd.parse_feed(corpo, ctype))}
        # a page: the feed it advertises (blog/rss/press also try the usual paths), else the links of its posts
        for cand in fd.discover(url, corpo, common_paths=tipo in ("blog", "rss")):
            cs, cc, ct = busca(cand)
            if cs == 200 and fd.looks_like_feed(cc, ct):
                try:
                    return {"ok": True, "modo": "feed", "itens": _de_feed(fd.parse_feed(cc, ct)), "feed": cand}
                except Exception:
                    continue
        if tipo == "site":
            return {"ok": True, "modo": "pagina", "itens": []}  # no feed: the site answered (coverage), nothing to list
        itens = _links(url, corpo)
        if not itens:
            return {"ok": False, "erro": "não achei feed nem lista de posts na página"}
        return {"ok": True, "modo": "links", "itens": itens}
    except Exception as exc:
        return {"ok": False, "erro": f"{type(exc).__name__}: {str(exc)[:120]}"}


# ------------------------------------------------------------------ comparing and grouping

PARADAS = set("a o as os de da do das dos e em no na nos nas um uma para por com sem que se ao seu sua the of and to in "
              "for on with is are como mais novo nova".split())


def _chave_item(it: dict) -> str:
    link = str(it.get("link") or "").split("#")[0].rstrip("/")
    return link or "t:" + _normal(it.get("titulo"))


def _normal(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", t))


def _palavras(texto) -> set:
    return {p for p in _normal(texto).split() if p not in PARADAS and len(p) > 2}


def _velho(it: dict, agora: float) -> bool:
    try:
        return agora - dt.datetime.fromisoformat(str(it.get("data"))).timestamp() > IDADE_MAX
    except (TypeError, ValueError):
        return False


CATEGORIAS = (
    ("preço", re.compile(r"pre[cç]o|plano|assinatura|mensalidade|desconto|gr[aá]tis|promo", re.I)),
    ("investimento", re.compile(r"aporte|investimento|rodada|capta|s[eé]rie [abc]|seed|levanta", re.I)),
    ("aquisição", re.compile(r"aquisi[cç]|adquir|compra (a|o) |fus[aã]o|incorpora", re.I)),
    ("parceria", re.compile(r"parceria|integra[cç]|integra |parceir", re.I)),
    ("produto", re.compile(r"lan[cç]a|novidade|nova (fun|vers)|novo (recurso|m[oó]dulo)|recurso|atualiza", re.I)),
)


def categoria(texto: str) -> str:
    for nome, rx in CATEGORIAS:
        if rx.search(texto or ""):
            return nome
    return "outro"


def agrupar(novos: list) -> list:
    """One fact per event: the same link, or titles that share most of their words (a launch on the blog and three
    press articles about it are one fact with four sources)."""
    fatos: list = []
    for it in novos:
        pal = _palavras(it["titulo"])
        alvo = None
        for f in fatos:
            if f["concorrente"] != it["concorrente"]:
                continue
            if _chave_item(it) in f["_chaves"]:
                alvo = f
                break
            inter, uniao = len(pal & f["_palavras"]), len(pal | f["_palavras"]) or 1
            if pal and inter / uniao >= 0.5:
                alvo = f
                break
        if alvo is None:
            alvo = {"concorrente": it["concorrente"], "nome": it["nome"], "titulo": it["titulo"],
                    "categoria": categoria(f"{it['titulo']} {it.get('resumo', '')}"), "data": it.get("data"),
                    "fontes": [], "_chaves": set(), "_palavras": set(pal)}
            fatos.append(alvo)
        elif it["fonte_tipo"] in ("blog", "site", "precos") and alvo["fontes"] and \
                all(x["tipo"] == "imprensa" for x in alvo["fontes"]):
            alvo["titulo"] = it["titulo"]  # the company's own words over a press headline
        alvo["_chaves"].add(_chave_item(it))
        alvo["_palavras"] |= pal
        alvo["fontes"].append({"tipo": it["fonte_tipo"], "link": it.get("link") or it.get("url_fonte"), "titulo": it["titulo"]})
    for f in fatos:
        f.pop("_chaves")
        f.pop("_palavras")
    return fatos


# ------------------------------------------------------------------ one round

def coletar(busca=buscar, agora: float | None = None) -> dict:
    """Read every source, compare with the last round, group by fact. Only what is new comes back. A source that
    failed goes to "sem_cobertura" and keeps its state, so nothing published meanwhile is lost."""
    agora = agora or time.time()
    lista = carregar()["concorrentes"]
    leituras = [(c, f, ler_fonte(f, busca)) for c in lista for f in c["fontes"]]  # network outside the lock
    novos, sem_cobertura, primeira, lidas = [], [], [], 0
    with _exclusivo():
        estado = _ler("estado.json", {"fontes": {}})
        fontes = estado.setdefault("fontes", {})
        for c, f, r in leituras:
            chave = f"{c['id']}|{f['url']}"
            antes = fontes.get(chave)
            if not r["ok"]:
                sem_cobertura.append({"concorrente": c["id"], "nome": c["nome"], "tipo": f["tipo"], "url": f["url"],
                                      "erro": r["erro"], "ultima_leitura": (antes or {}).get("lido_em")})
                if antes is not None:
                    antes["falhou_em"], antes["erro"] = agora, r["erro"]
                continue
            lidas += 1
            novo_estado = {"lido_em": agora, "modo": r["modo"]}
            if not antes or not antes.get("lido_em") or antes.get("modo") != r["modo"]:
                # first good read (or the source changed how it is read, e.g. it got a feed): the baseline
                primeira.append({"concorrente": c["id"], "tipo": f["tipo"], "url": f["url"], "modo": r["modo"]})
                antes = None
            if r["modo"] == "precos":
                novo_estado["precos"] = r["precos"]
                if antes and antes.get("precos") is not None and antes["precos"] != r["precos"]:
                    saiu = [p for p in antes["precos"] if p not in r["precos"]]
                    entrou = [p for p in r["precos"] if p not in antes["precos"]]
                    novos.append({"concorrente": c["id"], "nome": c["nome"], "fonte_tipo": "precos", "link": f["url"],
                                  "data": None, "titulo": f"Preços mudaram em {urllib.parse.urlsplit(f['url']).hostname}: "
                                  f"saiu {', '.join(saiu) or 'nada'}; entrou {', '.join(entrou) or 'nada'}"})
            elif "assinatura" in r:
                novo_estado["assinatura"] = r["assinatura"]
                if antes and antes.get("assinatura") and antes["assinatura"] != r["assinatura"]:
                    novos.append({"concorrente": c["id"], "nome": c["nome"], "fonte_tipo": f["tipo"], "link": f["url"],
                                  "data": None, "titulo": f"A página de preços de {c['nome']} mudou (sem preço legível)"})
            else:
                itens = r["itens"]
                chaves = [_chave_item(i) for i in itens]
                vistos = set((antes or {}).get("vistos") or [])
                if antes is not None:
                    for it, k in zip(itens, chaves):
                        if k not in vistos and not _velho(it, agora):
                            novos.append({**it, "concorrente": c["id"], "nome": c["nome"], "fonte_tipo": f["tipo"]})
                novo_estado["vistos"] = (chaves + [k for k in (antes or {}).get("vistos") or [] if k not in chaves])[:MAX_VISTOS]
            fontes[chave] = novo_estado
        estado["ultima_rodada"] = agora
        _gravar("estado.json", estado)
        resultado = {"em": agora, "fatos": agrupar(novos), "sem_cobertura": sem_cobertura, "fontes_lidas": lidas,
                     "primeira_leitura": primeira}
        with open(PASTA / "rodadas.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(resultado, ensure_ascii=False) + "\n")
    return resultado


def ultima() -> dict | None:
    arq = PASTA / "rodadas.jsonl"
    if not arq.exists():
        return None
    linhas = [l for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(linhas[-1]) if linhas else None


def texto(resultado: dict) -> str:
    """For the routine and the chat: the new facts, then what could not be read (never as "no news")."""
    linhas = []
    for f in resultado.get("fatos") or []:
        quando = f" ({str(f['data'])[:10]})" if f.get("data") else ""
        linhas.append(f"- {f['nome']} [{f['categoria']}]{quando}: {f['titulo']}")
        linhas += [f"    {x['tipo']}: {x['link']}" for x in f["fontes"][:4]]
    if not linhas:
        linhas.append("Nada novo nas fontes que consegui ler.")
    if resultado.get("sem_cobertura"):
        linhas.append("Sem cobertura (não deu para ler; não quer dizer que não houve novidade):")
        linhas += [f"- {s['nome']} ({s['tipo']}): {s['erro']} — {s['url']}" for s in resultado["sem_cobertura"]]
    if resultado.get("primeira_leitura"):
        linhas.append(f"Primeira leitura de {len(resultado['primeira_leitura'])} fonte(s): viram a base da comparação.")
    return "\n".join(linhas)

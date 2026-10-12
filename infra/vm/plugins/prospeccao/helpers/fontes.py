"""Lead sources that never touch Instagram (11/10: the Instagram search hit 429 two days running, and the Grok SDR
built a 4,342-company base from public directories without Apify).

- GuiaPJ: public CNPJ pages by activity (CNAE) and municipality — company, CNPJ, phone, e-mail, address, opening date.
- The agent's own search engine (SearXNG, localhost:55510) finds the company's Instagram and reads followers and bio
  from the result snippet, so Instagram itself is not queried.
- An imported list (the Grok SDR spreadsheet) as one more queue of companies.

A company only becomes a lead with an Instagram profile that matches it (same phone, or same name and city); contact
stays in the existing Instagram flow. The date of the last post is not in the snippet: those leads carry
`conferir_atividade` and the warm-up visit (which opens the profile anyway) checks it before following.
"""

import difflib
import html
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PASTA = Path("/a0/usr/prospeccao")
GUIAPJ = "https://guiapj.com.br"
SEARX = "http://localhost:55510/search"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
PAUSA_GUIAPJ = 1.5   # seconds between directory pages (polite)
PAUSA_BUSCA = 1.0    # seconds between search queries
BUSCAS_DIA = 100     # search API calls per day (config "buscas_dia" in the fontes file): Tavily is billed per call

# activity code -> rubric segment used when the bio says nothing better (order = priority)
CNAES = (("5620104", "marmitaria"),      # alimentos preparados para consumo domiciliar
         ("1096100", "cozinha_producao"),  # fabricação de alimentos e pratos prontos
         ("1091102", "confeitaria"),     # fabricação de produtos de padaria e confeitaria
         ("4721102", "padaria"),         # padaria e confeitaria (revenda)
         ("1092900", "outro_alimento"))  # massas alimentícias
# cities walked in the directory, in order (uf, name): Bahia first (where it started), then the capitals and big
# cities of Brazil (Matheus, 12/10: "é Brasil mesmo")
CIDADES = (("BA", "salvador"), ("BA", "lauro de freitas"), ("BA", "camacari"), ("BA", "simoes filho"), ("BA", "candeias"),
           ("BA", "dias d'avila"), ("SP", "sao paulo"), ("SP", "campinas"), ("RJ", "rio de janeiro"),
           ("MG", "belo horizonte"), ("PR", "curitiba"), ("RS", "porto alegre"), ("PE", "recife"), ("CE", "fortaleza"),
           ("DF", "brasilia"), ("GO", "goiania"), ("SC", "florianopolis"), ("ES", "vitoria"), ("BA", "feira de santana"),
           ("AM", "manaus"), ("PA", "belem"), ("MA", "sao luis"), ("PB", "joao pessoa"), ("RN", "natal"),
           ("AL", "maceio"), ("SE", "aracaju"), ("PI", "teresina"), ("MT", "cuiaba"), ("MS", "campo grande"),
           ("SP", "ribeirao preto"), ("SP", "sorocaba"), ("SP", "santos"), ("PR", "londrina"), ("SC", "joinville"))
# names that are clearly not a food producer: not worth a search query
FORA = re.compile(r"\b(bar|bares|boteco|lanchonete|pizzari|espetinho|a[cç]a[ií]|sorvet|mercad|mercearia|dep[oó]sito|"
                  r"distribuidora|churrascaria|pastelaria|hamburg|burger|cervej|adega|conveni[eê]ncia)", re.I)


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(c) != "Mn").lower()


def _digitos(t: str) -> str:
    return re.sub(r"\D", "", str(t or ""))


# ------------------------------------------------------------------ state

def _arquivo(login: str) -> Path:
    return PASTA / f"{re.sub(r'[^a-z0-9_]', '', login.lower())}_fontes.json"


def carregar(login: str) -> dict:
    try:
        d = json.loads(_arquivo(login).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("cursores", {})     # "cnae:municipio" -> next page (0 = done)
    d.setdefault("municipios", {})   # cnae -> {city name: municipality code}
    d.setdefault("empresas", {})     # key (cnpj or name|city) -> company + estado
    return d


def salvar(login: str, d: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    tmp = _arquivo(login).with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_arquivo(login))


def _chave(e: dict) -> str:
    return _digitos(e.get("cnpj")) or f"{_sem_acento(e.get('nome'))}|{_sem_acento(e.get('cidade'))}"


# ------------------------------------------------------------------ GuiaPJ

def _baixar(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def _texto(fragmento: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


def ler_listagem(pagina_html: str) -> list[dict]:
    """Company cards of a GuiaPJ activity/municipality page."""
    empresas = []
    for card in re.findall(r"<article[^>]*result-card[^>]*>(.*?)</article>", pagina_html, re.S):
        titulo = re.search(r'<h3[^>]*result-card-title[^>]*>(.*?)</h3>', card, re.S)
        razao = re.search(r'advanced-result-legal-name"[^>]*>(.*?)</span>', card, re.S)
        cnpj = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", card)
        local = re.search(r'pill light">([^<]+)</span>', card)
        campos = {}
        for rotulo, valor in re.findall(r"<strong>([^<]+):</strong>\s*(?:<!-- -->)?(.*?)</span>", card, re.S):
            campos[_sem_acento(rotulo).strip()] = _texto(valor)
        cidade, _, uf = (_texto(local.group(1)) if local else "").partition("/")
        situacao = "Ativa" if re.search(r'<span class="pill">Ativa</span>', card) else ""
        if not cnpj:
            continue
        empresas.append({
            "nome": _texto(titulo.group(1)) if titulo else "", "razao": _texto(razao.group(1)) if razao else "",
            "cnpj": cnpj.group(0), "cidade": cidade.title(), "uf": uf.upper(), "situacao": situacao,
            "telefone": campos.get("tel", ""), "email": campos.get("e-mail", ""), "bairro": campos.get("bairro", "").title(),
            "abertura": campos.get("abertura", ""), "cnae": campos.get("cnae", ""), "capital": campos.get("capital social", ""),
            "fonte": "GuiaPJ",
        })
    return empresas


def _municipios(d: dict, cnae: str, uf: str = "BA") -> dict:
    """City name -> municipality code for this activity in this state (read once from the state page)."""
    chave = cnae if uf == "BA" else f"{uf}:{cnae}"  # Bahia keeps the old key (already cached on the VM)
    if not d["municipios"].get(chave):
        pagina = _baixar(f"{GUIAPJ}/uf/{uf}/cnae/{cnae}")
        achados = {}
        for codigo, nome in re.findall(rf'href="/cnae/{cnae}/municipio/(\d+)"[^>]*>(.*?)</a>', pagina, re.S):
            achados[_sem_acento(_texto(nome)).split("/")[0].strip()] = codigo
        d["municipios"][chave] = achados
    return d["municipios"][chave]


def coletar(login: str, paginas: int = 4) -> dict:
    """Walk the next directory pages (activity x city, in priority order) into the company queue."""
    d = carregar(login)
    novas, lidas, erros = 0, 0, []
    for cnae, _seg in CNAES:
        if lidas >= paginas:
            break
        for uf, cidade in CIDADES:
            try:
                mapa = _municipios(d, cnae, uf)
            except Exception as exc:
                erros.append(f"{cnae}/{uf}: {exc}")
                continue
            codigo = next((c for nome, c in mapa.items() if nome == cidade or nome.startswith(cidade)), "")
            if cidade == "salvador" and not codigo:
                codigo = "3849"  # Salvador's code is stable; the state page may list it under a variant
            if not codigo:
                continue
            chave = f"{cnae}:{codigo}"
            proxima = d["cursores"].get(chave, 1)
            while proxima and lidas < paginas:
                url = f"{GUIAPJ}/cnae/{cnae}/municipio/{codigo}" + (f"/page/{proxima}" if proxima > 1 else "")
                try:
                    empresas = ler_listagem(_baixar(url))
                except urllib.error.HTTPError as exc:
                    empresas = [] if exc.code == 404 else None
                    if empresas is None:
                        erros.append(f"{url}: {exc}")
                        break
                except Exception as exc:
                    erros.append(f"{url}: {exc}")
                    break
                lidas += 1
                if not empresas:
                    proxima = 0
                else:
                    for e in empresas:
                        k = _chave(e)
                        if k not in d["empresas"]:
                            d["empresas"][k] = {**e, "estado": "fila", "em": time.time()}
                            novas += 1
                    proxima += 1
                d["cursores"][chave] = proxima
                time.sleep(PAUSA_GUIAPJ)
            if lidas >= paginas:
                break
    salvar(login, d)
    fila = sum(1 for e in d["empresas"].values() if e["estado"] == "fila")
    return {"paginas_lidas": lidas, "empresas_novas": novas, "na_fila": fila, "erros": erros[:3]}


# ------------------------------------------------------------------ imported list (Grok SDR spreadsheet)

TIERS = {"A+": 0, "A": 1, "B": 2, "C": 3}  # the Grok SDR sheet's priority (score of the evidence it found)


def origem_empresa(e: dict) -> str:
    """Which source a queued company came from: the Grok SDR sheet or the CNPJ catalog (prospeccao.ORIGENS)."""
    return "planilha" if re.search(r"grok|planilha|sdr", str(e.get("fonte") or ""), re.I) else "catalogo"


def importar(login: str, linhas: list) -> dict:
    """Rows {nome, cidade, uf, segmento, telefone, instagram, site, evidencia, fonte, tier, score, fonte_original,
    ja_contatado} into the queue (dedupe by key). A company already queued gets the fields it lacked (12/10: the first
    import of the sheet had no tier). Companies already contacted by WhatsApp (the sheet's own test, 17/09) are kept
    out: no second approach by another channel."""
    d = carregar(login)
    novas = atualizadas = 0
    for r in linhas if isinstance(linhas, list) else []:
        if not isinstance(r, dict) or not r.get("nome"):
            continue
        e = {"nome": str(r["nome"])[:80], "razao": "", "cnpj": str(r.get("cnpj") or ""), "cidade": str(r.get("cidade") or "").title(),
             "uf": str(r.get("uf") or "").upper(), "situacao": "", "telefone": str(r.get("telefone") or ""),
             "instagram": str(r.get("instagram") or "").strip(), "site": str(r.get("site") or ""),
             "segmento_fonte": str(r.get("segmento") or ""), "evidencia": str(r.get("evidencia") or "")[:400],
             "fonte": str(r.get("fonte") or "lista importada")[:60], "tier": str(r.get("tier") or "")[:3],
             "score": int(r.get("score") or 0) if str(r.get("score") or "").isdigit() else 0,
             "fonte_original": str(r.get("fonte_original") or "")[:120]}
        k = _chave(e)
        if k in d["empresas"]:
            atual = d["empresas"][k]
            faltavam = {c: v for c, v in e.items() if v and not atual.get(c)}
            if faltavam:
                atual.update(faltavam)
                atualizadas += 1
            continue
        estado = {"estado": "fila"}
        if r.get("ja_contatado"):
            estado = {"estado": "pulada", "motivo": "já contatada pelo WhatsApp (teste da planilha em 17/09)"}
        d["empresas"][k] = {**e, **estado, "em": time.time()}
        novas += 1
    salvar(login, d)
    return {"importadas": novas, "atualizadas": atualizadas,
            "na_fila": sum(1 for e in d["empresas"].values() if e["estado"] == "fila")}


# ------------------------------------------------------------------ search engine: the company's Instagram

CHAVE_TAVILY = Path("/a0/usr/prospeccao/.tavily_key")  # optional: a search API that is not degraded for AWS IPs
# (also read from the person's vault, TAVILY_API_KEY)


COFRE = Path("/a0/usr/segredos")  # the person's vault (/senha TAVILY_API_KEY <chave> in the phone chat)
_QUEM = {"login": ""}


def _tavily_key() -> str:
    import os

    if os.environ.get("TAVILY_API_KEY"):
        return os.environ["TAVILY_API_KEY"]
    try:
        return CHAVE_TAVILY.read_text().strip()
    except OSError:
        pass
    try:
        return str(json.loads((COFRE / f"{_QUEM['login']}.json").read_text(encoding="utf-8")).get("TAVILY_API_KEY") or "")
    except (OSError, ValueError):
        return ""


def _buscar(consulta: str) -> list[dict]:
    """Results as [{url, title, content}]: Tavily (Instagram only) when a key is set, else the local SearXNG (free, but
    Bing/DuckDuckGo degrade results for AWS addresses: 11/10 most queries came back without the profile)."""
    chave = _tavily_key()
    if chave:
        corpo = json.dumps({"query": consulta, "max_results": 8, "include_domains": ["instagram.com"]}).encode()
        req = urllib.request.Request("https://api.tavily.com/search", data=corpo,
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {chave}"})
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read() or b"{}").get("results") or []
    url = SEARX + "?" + urllib.parse.urlencode({"q": consulta, "format": "json", "language": "pt-BR"})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        return (json.loads(r.read() or b"{}").get("results") or [])[:15]


RX_PERFIL = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})/?(?:[?#~].*)?$", re.I)
NAO_PERFIL = {"p", "reel", "reels", "explore", "stories", "accounts", "tv", "about", "developer", "legal", "direct"}
PALAVRAS_VAZIAS = {"de", "da", "do", "das", "dos", "e", "ltda", "me", "eireli", "comercio", "alimentos", "alimentacao",
                   "servicos", "industria", "restaurante", "cia", "epp", "sa", "s", "a"}


def _palavras(t: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]{3,}", _sem_acento(t)) if w not in PALAVRAS_VAZIAS}


def _seguidores(texto: str) -> str:
    m = re.search(r"([\d.,]+\s*(?:mil|k|m)?\+?)\s*(?:seguidores|followers)", texto, re.I)
    return m.group(1).strip() if m else ""


def _bio(texto: str) -> str:
    texto = re.sub(r"\s*Follow\.?\s*$", "", texto)
    m = re.search(r"no Instagram:\s*[\"“](.*?)[\"”]?\s*$", texto, re.S) or re.search(r"on Instagram:\s*[\"“](.*?)[\"”]?\s*$", texto, re.S)
    return " ".join((m.group(1) if m else texto).split())[:300]


def achar_instagram(e: dict, conta: dict | None = None) -> dict | None:
    """The company's Instagram from search results, only when it matches: same phone, the handle the source already
    gave, or the same name (and city). Returns {handle, seguidores, bio, titulo, confianca} or None."""
    dado = str(e.get("instagram") or "").strip().lstrip("@").rstrip("/").rsplit("/", 1)[-1]
    nome = _nome_busca(e.get("nome") or e.get("razao") or "")
    cidade = str(e.get("cidade") or "").title()
    consultas = [f"instagram.com/{dado}", f"@{dado} instagram"] if dado else []
    consultas += [f'"{nome}" {cidade} instagram', f"{nome} {cidade} instagram"]  # engines vary run to run
    fone = _digitos(e.get("telefone"))[-8:]
    falhas = 0
    for consulta in consultas:
        if conta is not None:
            conta["n"] = conta.get("n", 0) + 1
        try:
            resultados = _buscar(consulta)
        except Exception:
            falhas += 1
            continue
        time.sleep(PAUSA_BUSCA)
        for r in resultados:
            m = RX_PERFIL.search(str(r.get("url") or ""))
            if not m or m.group(1).lower() in NAO_PERFIL:
                continue
            handle = m.group(1).lower()
            texto = f"{r.get('title', '')} {r.get('content', '')}"
            if dado and handle == dado.lower():
                confianca = "fonte"
            elif fone and len(fone) == 8 and fone in _digitos(texto):
                confianca = "telefone"
            else:
                titulo = re.sub(r"\(@[^)]*\).*$", "", str(r.get("title") or ""))
                ps_nome, ps_titulo = _palavras(nome), _palavras(f"{titulo} {handle}")
                comum = len(ps_nome & ps_titulo) / max(1, len(ps_nome))
                parecido = difflib.SequenceMatcher(None, _sem_acento(nome), _sem_acento(titulo)).ratio()
                na_cidade = _sem_acento(e.get("cidade", "")) in _sem_acento(texto)
                if not ps_nome or not ((comum >= 0.67 and na_cidade) or parecido >= 0.9 or (comum == 1 and len(ps_nome) >= 2)):
                    continue
                confianca = "nome"
            return {"handle": handle, "seguidores": _seguidores(texto), "bio": _bio(str(r.get("content") or "")),
                    "titulo": str(r.get("title") or "")[:120], "confianca": confianca}
    if falhas == len(consultas):
        raise RuntimeError("buscador indisponível")
    return None


# Platforms that link their own Instagram from the pages they host (site builders, ordering systems, marketplaces):
# a handle like these on a company's site is not the company's profile.
PLATAFORMAS = re.compile(r"^(ueni|ueniweb|ifood|ifoodbrasil|wix|wordpress|goomer|goomerapp|anotaai|anota\.ai|cardapioweb|"
                         r"linktree|linktr\.ee|instagram|meta|facebook|whatsapp|lojaintegrada|nuvemshop|shopify|hotmart|"
                         r"solutudo|guiapj|google|youtube|tiktok|rappi|aiqfome|99food|deliverymuch|saipos|consumer|menudino)$", re.I)
RX_LINK_IG = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})", re.I)


def instagram_do_site(e: dict) -> dict | None:
    """The company's own site usually links its Instagram: read the home page (no paid search). 12/10: 531 rows of
    the sheet have a site. Only a handle that is not a platform's; with several, the one that shares a word with the
    company name. Returns {handle, seguidores, bio, titulo, confianca: "site"} or None."""
    site = str(e.get("site") or "").strip()
    if not site:
        return None
    url = site if re.match(r"https?://", site, re.I) else "https://" + site
    try:
        pagina = _baixar(url, 12)
    except Exception:
        return None
    vistos = []
    for m in RX_LINK_IG.finditer(pagina):
        h = m.group(1).strip(".").lower()
        if h in NAO_PERFIL or PLATAFORMAS.match(h) or h in vistos:
            continue
        vistos.append(h)
    if not vistos:
        return None
    nome = _palavras(e.get("nome") or "")
    melhor = next((h for h in vistos if any(w in h for w in nome)), None)
    if not melhor and len(vistos) > 1:
        return None
    return {"handle": melhor or vistos[0], "seguidores": "", "bio": "", "titulo": "", "confianca": "site"}


def _nome_busca(nome: str) -> str:
    """"COZINHA DE CHEF" -> "Cozinha de Chef" (all-caps queries bring noise); drops the CNPJ/CPF prefix of MEIs."""
    nome = re.sub(r"^[\d.\s/-]+", "", str(nome or "")).strip()
    return " ".join(w.lower() if w.lower() in ("de", "da", "do", "das", "dos", "e") else w.capitalize() for w in nome.split())


# ------------------------------------------------------------------ queue -> leads

def _item_lead(e: dict, ig: dict, segmento_cnae: str, rx_canais: dict, rx_exclusoes: dict, segmento_rubrica) -> dict:
    bio = ig.get("bio") or ""
    texto = f"{e.get('nome', '')} {ig.get('titulo', '')} {bio} {e.get('segmento_fonte', '')}"
    # unknown activity/size count as the median (12 + 12) until the warm-up visit checks them; what the bio or the
    # source's evidence says about sales channels still counts
    sinais_texto = f"{bio} {e.get('evidencia', '')}".lower()
    segmento = segmento_rubrica(texto) or segmento_cnae or "outro_alimento"
    anos = ""
    m = re.search(r"(\d{4})$", e.get("abertura", ""))
    if m:
        anos = f", aberta em {m.group(1)}"
    rotulo = f"CNPJ {e['cnpj']}{anos}" if e.get("cnpj") else e.get("fonte", "lista")
    detalhe = e.get("fonte_original") or (e.get("fonte", "") if e.get("cnpj") else "")
    como = {"site": "no site da empresa", "fonte": "pela fonte"}.get(ig["confianca"], f"pela busca ({ig['confianca']})")
    return {
        "handle": ig["handle"], "canal": "instagram", "nome": (e.get("nome") or ig["handle"])[:80], "segmento": segmento,
        "cidade": e.get("cidade") or "", "seguidores": ig.get("seguidores") or "",
        "canais": [c for c, rx in rx_canais.items() if re.search(rx, sinais_texto)],
        "cardapio": bool(re.search(r"card[aá]pio|menu", sinais_texto)),
        "exclusoes": [c for c, rx in rx_exclusoes.items() if re.search(rx, bio.lower())],
        "atividade_pendente": True, "fonte": e.get("fonte", ""), "origem": origem_empresa(e),
        "motivo": (f"{rotulo}" + (f" ({detalhe[:60]})" if detalhe else "") + f"; Instagram achado {como}: "
                   f"{ig.get('seguidores') or '?'} seguidores; bio: {bio[:140]}")[:300],
        "sinal": (e.get("evidencia") or "")[:300],
    }


def _ordem(e: dict) -> tuple:
    """@ already known first (no search), then a site to read (no search), then the sheet by tier and score, then
    the raw directory by activity."""
    return (0 if e.get("instagram") else 1 if e.get("site") and not e.get("site_sem_ig") else 2, TIERS.get(e.get("tier") or "", 4),
            -(e.get("score") or 0), 0 if origem_empresa(e) == "planilha" else 1,
            next((i for i, (c, _) in enumerate(CNAES) if c == e.get("cnae")), 9))


def enriquecer(login: str, p, limite: int = 20, origens: list | None = None) -> dict:
    """Find the Instagram of the next queued companies and register the ones that fit (p = prospeccao helper).
    `origens`: only these sources (the ones whose share of the stock is missing)."""
    _QUEM["login"] = re.sub(r"[^a-z0-9_.-]", "", login.lower())
    d = carregar(login)
    conhecidos = {l["handle"] for l in p.carregar(login)["leads"]} | set((p.carregar(login).get("rejeitados") or {}).keys())
    fila = [k for k, e in d["empresas"].items() if e["estado"] == "fila" and (not origens or origem_empresa(e) in origens)]
    fila.sort(key=lambda k: _ordem(d["empresas"][k]))
    out = {"examinadas": 0, "criados": [], "sem_instagram": 0, "recusados": [], "pulados": 0}
    segmentos = dict(CNAES)
    itens = []
    hoje = time.strftime("%Y-%m-%d")
    conta = d.setdefault("buscas", {})
    if conta.get("dia") != hoje:
        conta.update({"dia": hoje, "n": 0})
    teto = int(d.get("buscas_dia") or BUSCAS_DIA)
    for k in fila[:limite]:
        e = d["empresas"][k]
        if (e.get("situacao") and e["situacao"] != "Ativa") or FORA.search(f"{e.get('nome', '')} {e.get('razao', '')}"):
            e["estado"], e["motivo"] = "pulada", "inativa ou fora do segmento pelo nome"
            out["pulados"] += 1
            out["examinadas"] += 1
            continue
        if re.match(r"^\s*\d", e.get("nome", "")) and not e.get("instagram"):
            e["estado"], e["motivo"] = "pulada", "MEI com nome de pessoa (sem marca para buscar)"
            out["pulados"] += 1
            out["examinadas"] += 1
            continue
        dado = str(e.get("instagram") or "").strip().lstrip("@").rstrip("/").rsplit("/", 1)[-1].lower()
        ig = {"handle": dado, "seguidores": "", "bio": "", "titulo": "", "confianca": "fonte"} if dado else None
        if not ig and e.get("site") and not e.get("site_sem_ig"):
            ig = instagram_do_site(e)  # free: no paid search
            if not ig:
                e["site_sem_ig"] = True
        if not ig:
            if conta["n"] >= teto:  # only a paid search stops at the daily cap; @ and sites above go on
                out["erro_busca"] = f"limite diário de {teto} buscas atingido; a fila continua amanhã"
                break
            try:
                ig = achar_instagram(e, conta)
            except RuntimeError:
                out["erro_busca"] = "buscador indisponível agora; a empresa continua na fila"
                break
        out["examinadas"] += 1
        if not ig:
            e["estado"] = "sem_instagram"
            out["sem_instagram"] += 1
            continue
        e["instagram_achado"] = ig
        if ig["handle"] in conhecidos:
            e["estado"], e["motivo"] = "repetido", "perfil já no registro"
            continue
        itens.append((k, _item_lead(e, ig, segmentos.get(e.get("cnae"), ""), p.RX_CANAIS, p.RX_EXCLUSOES, p.segmento_rubrica)))
        conhecidos.add(ig["handle"])
    if itens:
        r = p.registrar(login, [i for _, i in itens])
        criados = {c["handle"] for c in r["criados"]}
        for k, item in itens:
            if item["handle"] in criados:
                d["empresas"][k]["estado"] = "lead"
            else:
                motivo = next((x["motivo"] for x in r["recusados"] if x["handle"] == item["handle"]), "repetido")
                d["empresas"][k]["estado"], d["empresas"][k]["motivo"] = "recusado", motivo[:160]
        out["criados"] = r["criados"]
        out["recusados"] = [{"handle": x["handle"], "motivo": x["motivo"][:100]} for x in r["recusados"]]
    salvar(login, d)
    out["na_fila"] = sum(1 for e in d["empresas"].values() if e["estado"] == "fila")
    return out


# ------------------------------------------------------------------ Apify: Instagram without our account
# 12/10 pilot: 6 searches (word + city) brought 38 profiles in 2 min for ~US$ 0.10; 20 fit the rubric (active, the
# right size, in the city), 14 were stale or tiny, 3 already known. The leads found on Instagram itself are the ones
# that answer; Apify finds them without touching @raiz.connect (no 429, no block). The same data also checks the
# sheet's profiles before their turn (instagram-profile-scraper). Every call has a cost cap and counts toward a
# monthly budget (config "apify_usd_mes" in the fontes file, default the free plan's US$ 5).

APIFY = "https://api.apify.com/v2/acts"
APIFY_USD_MES = 5.0
PAUSA_APIFY = 30  # seconds before the second try
PRECO_APIFY = {"apify~instagram-search-scraper": 0.0027, "apify~instagram-profile-scraper": 0.0026}  # per item, free plan
PALAVRAS_INSTAGRAM = ("marmita fit", "marmitaria", "marmitas congeladas", "confeitaria", "bolo caseiro", "salgados",
                      "doces gourmet", "comida congelada")


def _apify_token() -> str:
    try:
        s = json.loads((COFRE / f"{_QUEM['login']}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(s.get("APIFY_API") or s.get("APIFY_TOKEN") or s.get("APIFY_API_TOKEN") or "")


def _apify(ator: str, entrada: dict, max_usd: float) -> list:
    """Runs an actor and returns its items (synchronous call: Apify waits up to 300 s). One more try after a refusal
    (12/10: a 400 right after three runs in a row; the same call went through a minute later)."""
    url = f"{APIFY}/{ator}/run-sync-get-dataset-items?timeout=280&format=json&clean=true&maxTotalChargeUsd={max_usd:.2f}"
    for tentativa in (1, 2):
        req = urllib.request.Request(url, data=json.dumps(entrada).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {_apify_token()}"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                itens = json.loads(r.read() or b"[]")
            return itens if isinstance(itens, list) else []
        except urllib.error.HTTPError as exc:
            corpo = exc.read()[:200].decode("utf-8", "ignore")
            if tentativa == 2 or exc.code in (401, 403):
                raise RuntimeError(f"HTTP {exc.code}: {corpo}") from None
            time.sleep(PAUSA_APIFY)
    return []


def apify_pronto(login: str) -> bool:
    _QUEM["login"] = re.sub(r"[^a-z0-9_.-]", "", login.lower())
    return bool(_apify_token())


def _verba(d: dict) -> dict:
    """This month's Apify spending (estimated from items x price) and the cap."""
    mes = time.strftime("%Y-%m")
    v = d.setdefault("apify", {})
    if v.get("mes") != mes:
        v.update({"mes": mes, "usd": 0.0})
    v.setdefault("cursor", 0)
    return {"gasto": v["usd"], "teto": float(d.get("apify_usd_mes") or APIFY_USD_MES)}


def _gastar(d: dict, ator: str, n: int) -> float:
    custo = round(n * PRECO_APIFY.get(ator, 0.003), 4)
    d["apify"]["usd"] = round(d["apify"]["usd"] + custo, 4)
    return custo


def _termos(d: dict, n: int) -> list:
    """Next search terms (word + city), in rotation over every city of the catalog list: Brazil-wide, no repeats
    until the list wraps."""
    todos = [(f"{palavra} {nome}", nome) for _, nome in CIDADES for palavra in PALAVRAS_INSTAGRAM]
    i = d["apify"]["cursor"] % len(todos)
    escolhidos = (todos[i:] + todos[:i])[:n]
    d["apify"]["cursor"] = i + n
    return escolhidos


def buscar_instagram(login: str, p, termos: int = 3, por_termo: int = 20) -> dict:
    """The Instagram share of the stock through Apify: search profiles by word + city, keep what fits the rubric
    (registered already checked: last post, followers, private), note what does not (60 days), skip what is known."""
    _QUEM["login"] = re.sub(r"[^a-z0-9_.-]", "", login.lower())
    if not _apify_token():
        return {"erro": "sem Apify (APIFY_API no cofre)"}
    d = carregar(login)
    v = _verba(d)
    custo_max = termos * por_termo * PRECO_APIFY["apify~instagram-search-scraper"]
    if v["gasto"] + custo_max > v["teto"]:
        salvar(login, d)
        return {"erro": f"verba do Apify do mês atingida (US$ {v['gasto']:.2f} de {v['teto']:.2f}); volta no mês que vem"}
    escolhidos = _termos(d, termos)
    salvar(login, d)  # the cursor moves even if the call fails: a bad term is not retried forever
    try:
        itens = _apify("apify~instagram-search-scraper",
                       {"search": ",".join(t for t, _ in escolhidos), "searchType": "user", "searchLimit": por_termo},
                       custo_max + 0.05)
    except Exception as exc:
        return {"erro": f"Apify não respondeu ({str(exc)[:80]}); tente na próxima rodada", "termos": [t for t, _ in escolhidos]}
    d = carregar(login)
    _verba(d)
    custo = _gastar(d, "apify~instagram-search-scraper", len(itens))
    salvar(login, d)
    cidade_do_termo = {t: _nome_busca(c) for t, c in escolhidos}
    dados = p.carregar(login)
    conhecidos = {l["handle"] for l in dados["leads"]} | set((dados.get("rejeitados") or {}).keys())
    out = {"termos": [t for t, _ in escolhidos], "perfis": len(itens), "criados": [], "recusados": 0, "ja_conhecidos": 0,
           "custo_usd": custo, "mes_usd": d["apify"]["usd"]}
    novos, rejeitar = [], []
    for it in itens:
        perfil = p._perfil_padrao(it) if isinstance(it, dict) else {}
        h = p.normalizar(str(perfil.get("handle") or ""))
        if not h or perfil.get("erro"):
            continue
        if h in conhecidos:
            out["ja_conhecidos"] += 1
            continue
        conhecidos.add(h)
        ev = p._evidencia(perfil)
        termo = str(it.get("searchTerm") or "")
        item = {**ev, "segmento": ev["segmento"] or p.segmento_rubrica(termo),
                "cidade": ev["cidade"] or cidade_do_termo.get(termo, ""), "origem": "instagram", "fonte": "Apify",
                "motivo": (f"Apify, busca no Instagram «{termo}»" + ("" if ev["cidade"] else " (cidade da busca)") + f"; {ev['motivo']}")[:300]}
        r = p.pontuar(item)
        if r.get("rejeitado") or r.get("nota", 0) < p.NOTA_MINIMA:
            rejeitar.append({"handle": h, "motivo": r.get("rejeitado") or f"nota {r.get('nota')}"})
            continue
        novos.append(item)
    if rejeitar:
        p.rejeitar(login, rejeitar)
    out["recusados"] = len(rejeitar)
    if novos:
        r = p.registrar(login, novos)
        out["criados"] = r["criados"]
        out["recusados"] += len(r["recusados"])
    return out


def conferir_apify(login: str, p, handles: list) -> dict:
    """The sheet's profiles checked in one go by Apify's profile scraper (then the same rules as the browser script)."""
    _QUEM["login"] = re.sub(r"[^a-z0-9_.-]", "", login.lower())
    handles = [h for h in handles if h][:25]
    if not handles or not _apify_token():
        return {"erro": "nada a conferir ou sem Apify"}
    d = carregar(login)
    v = _verba(d)
    custo_max = len(handles) * PRECO_APIFY["apify~instagram-profile-scraper"]
    if v["gasto"] + custo_max > v["teto"]:
        salvar(login, d)
        return {"erro": f"verba do Apify do mês atingida (US$ {v['gasto']:.2f} de {v['teto']:.2f})"}
    try:
        itens = _apify("apify~instagram-profile-scraper", {"usernames": handles}, custo_max + 0.05)
    except Exception as exc:
        salvar(login, d)
        return {"erro": f"Apify não respondeu ({str(exc)[:80]})"}
    _gastar(d, "apify~instagram-profile-scraper", len(itens))
    salvar(login, d)
    # a profile Apify did not return is left for the next check (never discarded for a missing answer)
    return p.conferir_perfis(login, itens, "apify")


def resumo(login: str) -> str:
    d = carregar(login)
    from collections import Counter

    partes = []
    for o in ("planilha", "catalogo"):
        c = Counter(e["estado"] for e in d["empresas"].values() if origem_empresa(e) == o)
        if c:
            partes.append(f"{o} {sum(c.values())} ({', '.join(f'{k} {v}' for k, v in c.most_common())})")
    return "Fila das fontes fora do Instagram: " + ("; ".join(partes) or "vazia")

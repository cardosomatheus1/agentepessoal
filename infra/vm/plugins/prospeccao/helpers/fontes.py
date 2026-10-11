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

# activity code -> rubric segment used when the bio says nothing better (order = priority)
CNAES = (("5620104", "marmitaria"),      # alimentos preparados para consumo domiciliar
         ("1096100", "cozinha_producao"),  # fabricação de alimentos e pratos prontos
         ("1091102", "confeitaria"),     # fabricação de produtos de padaria e confeitaria
         ("4721102", "padaria"),         # padaria e confeitaria (revenda)
         ("1092900", "outro_alimento"))  # massas alimentícias
# region of the playbook, in the order the directory is walked (the rubric's REGIOES decides what scores)
CIDADES = ("salvador", "lauro de freitas", "camacari", "simoes filho", "candeias", "dias d'avila")
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

def _baixar(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
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


def _municipios(d: dict, cnae: str) -> dict:
    """City name -> municipality code for this activity in Bahia (read once from the state page)."""
    if not d["municipios"].get(cnae):
        pagina = _baixar(f"{GUIAPJ}/uf/BA/cnae/{cnae}")
        achados = {}
        for codigo, nome in re.findall(rf'href="/cnae/{cnae}/municipio/(\d+)"[^>]*>(.*?)</a>', pagina, re.S):
            achados[_sem_acento(_texto(nome)).split("/")[0].strip()] = codigo
        d["municipios"][cnae] = achados
    return d["municipios"][cnae]


def coletar(login: str, paginas: int = 4) -> dict:
    """Walk the next directory pages (activity x city, in priority order) into the company queue."""
    d = carregar(login)
    novas, lidas, erros = 0, 0, []
    for cnae, _seg in CNAES:
        if lidas >= paginas:
            break
        try:
            mapa = _municipios(d, cnae)
        except Exception as exc:
            erros.append(f"{cnae}: {exc}")
            continue
        for cidade in CIDADES:
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

def importar(login: str, linhas: list) -> dict:
    """Rows {nome, cidade, uf, segmento, telefone, instagram, site, evidencia, fonte} into the queue (dedupe by key)."""
    d = carregar(login)
    novas = 0
    for r in linhas if isinstance(linhas, list) else []:
        if not isinstance(r, dict) or not r.get("nome"):
            continue
        e = {"nome": str(r["nome"])[:80], "razao": "", "cnpj": str(r.get("cnpj") or ""), "cidade": str(r.get("cidade") or "").title(),
             "uf": str(r.get("uf") or "").upper(), "situacao": "", "telefone": str(r.get("telefone") or ""),
             "instagram": str(r.get("instagram") or "").strip(), "site": str(r.get("site") or ""),
             "segmento_fonte": str(r.get("segmento") or ""), "evidencia": str(r.get("evidencia") or "")[:400],
             "fonte": str(r.get("fonte") or "lista importada")[:60]}
        k = _chave(e)
        if k not in d["empresas"]:
            d["empresas"][k] = {**e, "estado": "fila", "em": time.time()}
            novas += 1
    salvar(login, d)
    return {"importadas": novas, "na_fila": sum(1 for e in d["empresas"].values() if e["estado"] == "fila")}


# ------------------------------------------------------------------ search engine: the company's Instagram

def _buscar(consulta: str) -> list[dict]:
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
    m = re.search(r"([\d.,]+\s*(?:mil|k|m)?)\s*(?:seguidores|followers)", texto, re.I)
    return m.group(1).strip() if m else ""


def _bio(texto: str) -> str:
    m = re.search(r"no Instagram:\s*[\"“](.*?)[\"”]?\s*$", texto, re.S) or re.search(r"on Instagram:\s*[\"“](.*?)[\"”]?\s*$", texto, re.S)
    return " ".join((m.group(1) if m else texto).split())[:300]


def achar_instagram(e: dict) -> dict | None:
    """The company's Instagram from search results, only when it matches: same phone, the handle the source already
    gave, or the same name (and city). Returns {handle, seguidores, bio, titulo, confianca} or None."""
    dado = str(e.get("instagram") or "").strip().lstrip("@").rstrip("/").rsplit("/", 1)[-1]
    nome = e.get("nome") or e.get("razao") or ""
    consultas = [f"instagram.com/{dado}"] if dado else []
    consultas.append(f'"{nome}" {e.get("cidade", "")} instagram')
    fone = _digitos(e.get("telefone"))[-8:]
    for consulta in consultas:
        try:
            resultados = _buscar(consulta)
        except Exception:
            return None
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
    return None


# ------------------------------------------------------------------ queue -> leads

def _item_lead(e: dict, ig: dict, segmento_cnae: str, rx_canais: dict, rx_exclusoes: dict, segmento_rubrica) -> dict:
    bio = ig.get("bio") or ""
    texto = f"{e.get('nome', '')} {ig.get('titulo', '')} {bio} {e.get('segmento_fonte', '')}"
    segmento = segmento_rubrica(texto) or segmento_cnae or "outro_alimento"
    anos = ""
    m = re.search(r"(\d{4})$", e.get("abertura", ""))
    if m:
        anos = f", aberta em {m.group(1)}"
    origem = f"CNPJ {e['cnpj']}{anos}" if e.get("cnpj") else e.get("fonte", "lista")
    return {
        "handle": ig["handle"], "canal": "instagram", "nome": (e.get("nome") or ig["handle"])[:80], "segmento": segmento,
        "cidade": e.get("cidade") or "", "seguidores": ig.get("seguidores") or "",
        "canais": [c for c, rx in rx_canais.items() if re.search(rx, bio.lower())],
        "cardapio": bool(re.search(r"card[aá]pio|menu", bio.lower())),
        "exclusoes": [c for c, rx in rx_exclusoes.items() if re.search(rx, bio.lower())],
        "atividade_pendente": True, "fonte": e.get("fonte", ""),
        "motivo": (f"{origem} ({e.get('fonte', '')}); Instagram achado pela busca ({ig['confianca']}): "
                   f"{ig.get('seguidores') or '?'} seguidores; bio: {bio[:140]}")[:300],
        "sinal": (e.get("evidencia") or "")[:300],
    }


def enriquecer(login: str, p, limite: int = 20) -> dict:
    """Search the Instagram of the next queued companies and register the ones that fit (p = prospeccao helper)."""
    d = carregar(login)
    conhecidos = {l["handle"] for l in p.carregar(login)["leads"]} | set((p.carregar(login).get("rejeitados") or {}).keys())
    fila = [k for k, e in d["empresas"].items() if e["estado"] == "fila"]
    fila.sort(key=lambda k: (0 if d["empresas"][k].get("instagram") else 1,
                             next((i for i, (c, _) in enumerate(CNAES) if c == d["empresas"][k].get("cnae")), 9)))
    out = {"examinadas": 0, "criados": [], "sem_instagram": 0, "recusados": [], "pulados": 0}
    segmentos = dict(CNAES)
    itens = []
    for k in fila[:limite]:
        e = d["empresas"][k]
        out["examinadas"] += 1
        if (e.get("situacao") and e["situacao"] != "Ativa") or FORA.search(f"{e.get('nome', '')} {e.get('razao', '')}"):
            e["estado"], e["motivo"] = "pulada", "inativa ou fora do segmento pelo nome"
            out["pulados"] += 1
            continue
        ig = achar_instagram(e)
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


def resumo(login: str) -> str:
    d = carregar(login)
    from collections import Counter

    c = Counter(e["estado"] for e in d["empresas"].values())
    return (f"Fontes sem Instagram (GuiaPJ + buscador + listas): {len(d['empresas'])} empresas — "
            + ", ".join(f"{k}: {v}" for k, v in c.most_common()))

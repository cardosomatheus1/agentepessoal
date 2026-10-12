"""Prospecting engine for Raiz Connect: leads, the actions proposed for each one, the person's approvals, paced
execution and the numbers that say what works. State: /a0/usr/prospeccao/<login>.json.

Nothing reaches a third party unless the person approved that exact action on the phone; the execution round
takes one approved action at a time (`proxima`), within daily limits, hours and spacing, and reports back
(`resultado`). Rules that a model could forget (links in a first message, the same text twice, contacting someone
again after a "no") are enforced here, not left to the prompt."""

import datetime as dt
import json
import re
import time
import uuid
from pathlib import Path

PASTA = Path("/a0/usr/prospeccao")
FUSO = "America/Bahia"
CAIXA_TESTES = Path("/a0/usr/testes/celular.jsonl")

TIPOS = ("aquecer", "dm_abertura", "dm_lembrete", "resposta", "parceiro")
LIMITE_DIA = {"aquecer": 20, "dm_abertura": 12, "dm_lembrete": 10, "resposta": 15, "parceiro": 5}
INTERVALO = 3 * 60                 # between two executed actions
HORARIO = (9, 20)                  # executions only within [9h, 20h) local time
BLOQUEIO = 48 * 3600               # pause after Instagram blocks an action
DIAS_DM = 2                        # calendar days after warming up, before the first DM
DIAS_LEMBRETE = 3                  # calendar days after the first DM, before the reminder
# Calendar days, not hours (11/10): leads warmed at 11h on day 10 were only "due" at 11h on day 12, after the
# 9h23 round that writes the DMs, so the DMs slipped a whole day.
ESPERA_FIM = 5 * 86400             # after the reminder, the lead is closed as no answer
VALIDADE_PROPOSTA = 24 * 3600      # unapproved proposals expire
LIBERACAO = 12 * 60                # approved action: window for the approvals reviewer
ETAPAS = ("novo", "aquecido", "abordado", "lembrado", "respondeu", "lead", "demo", "teste", "cliente",
          "sem_resposta", "descartado")
FINAIS = ("cliente", "sem_resposta", "descartado")
CONTAS_PROIBIDAS = ("cardosomatheus1",)  # the person's own profile: prospecting never runs from it
CANAIS = ("instagram", "parceiro")

PROIBIDAS = re.compile(r"\b(promo[cç][aã]o|imperd[ií]vel|oportunidade [uú]nica|[uú]ltimas vagas|gr[aá]tis por tempo|"
                       r"clique aqui|link na bio|erp|cmv)\b", re.I)
LINK = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|com\.br|app|io|net|me|link|ly)\b)", re.I)
# The links prospecting may send — free tools that show a result before asking for any data: the pricing calculator
# (default) and the delivery simulator (for who sells on iFood). Only in the reminder and in answers to people who
# wrote back — never in the first message (a link from a stranger reads as spam). The Raio-X and the 15-errors quiz stay
# out: any "more or less" answer counts as a problem there, so everyone gets "8 of 8 need attention".
LINK_CALCULADORA = "raizconnect.com.br/materiais/precificacao/calculadora"  # short on purpose: the full UTM link looked huge in the DM (11/10)
LINK_DELIVERY = "raizconnect.com.br/materiais/quanto-sobra-no-delivery"
CALCULADORA = re.compile(r"(https?://)?(www\.)?raizconnect\.com\.br/materiais/(precificacao/calculadora|quanto-sobra-no-delivery)"
                         r"(\?[\w=&%.-]*)?(?![\w/])", re.I)
TIPOS_COM_LINK = ("dm_lembrete", "resposta")


# ------------------------------------------------------------------ storage

def _login(login: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "", (login or "").lower()) or "matheus"


def _id() -> str:
    return uuid.uuid4().hex[:6]


def _tz():
    from zoneinfo import ZoneInfo

    return ZoneInfo(FUSO)


def agora() -> float:
    return time.time()


def carregar(login: str) -> dict:
    try:
        d = json.loads((PASTA / f"{_login(login)}.json").read_text(encoding="utf-8"))
    except Exception:
        d = {}
    d.setdefault("leads", [])
    d.setdefault("acoes", [])
    d.setdefault("config", {})
    d.setdefault("bloqueio_ate", 0)
    return d


# ------------------------------------------------------------------ action states: one rule, one journal
# Every change of an action's state goes through _mudar() and lands in <login>_eventos.jsonl (append-only), so a
# state can never jump (11/10: "executada" was edited by hand to "duplicada" and a lock stayed on for good).
TRANSICOES = {
    "proposta": {"aprovada", "pulada", "expirada", "cancelada", "proposta"},
    "aprovada": {"executada", "falhou", "cancelada", "proposta"},  # "proposta" again = new text (editar)
    "executada": {"apagada"},  # the message was deleted (unsent) in the Instagram
    "falhou": set(), "pulada": set(), "expirada": set(), "cancelada": set(), "apagada": set(),
}
AUTOR = {"quem": "agente"}  # operator scripts set "operador: <why>"


class TransicaoInvalida(ValueError):
    pass


def _evento(d: dict, a: dict, de: str, para: str, motivo: str = "") -> None:
    d.setdefault("_eventos", []).append({"em": agora(), "acao": a["id"], "lead": a["lead_id"], "tipo": a["tipo"],
                                         "de": de, "para": para, "motivo": str(motivo)[:200], "por": AUTOR["quem"]})


def _mudar(d: dict, a: dict, novo: str, motivo: str = "", **campos) -> dict:
    atual = a["estado"]
    if novo not in TRANSICOES.get(atual, set()):
        raise TransicaoInvalida(f"ação {a['id']} ({a['tipo']}): {atual} → {novo} não é permitido")
    a["estado"] = novo
    a.update(campos)
    _evento(d, a, atual, novo, motivo)
    return a


def eventos(login: str, ultimos: int = 50) -> list[dict]:
    try:
        linhas = (PASTA / f"{_login(login)}_eventos.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [json.loads(l) for l in linhas[-ultimos:] if l.strip()]


def salvar(login: str, d: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    novos = d.pop("_eventos", [])
    if novos:
        with (PASTA / f"{_login(login)}_eventos.jsonl").open("a", encoding="utf-8") as f:
            for e in novos:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    alvo = PASTA / f"{_login(login)}.json"
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(alvo)


def modo_teste(login: str) -> bool:
    """Test mode: phone messages are recorded (CAIXA_TESTES) instead of sent, and nothing is executed."""
    return bool(carregar(login)["config"].get("teste")) or _login(login).startswith("teste_")


def _hoje_local(ts: float | None = None) -> str:
    return dt.datetime.fromtimestamp(ts or agora(), _tz()).strftime("%Y-%m-%d")


def _hora_local(ts: float | None = None) -> int:
    return dt.datetime.fromtimestamp(ts or agora(), _tz()).hour


# ------------------------------------------------------------------ leads

def normalizar(handle: str) -> str:
    h = (handle or "").strip().lower()
    h = re.sub(r"^(https?://)?(www\.|m\.)?instagram\.com/", "", h)
    h = h.split("?")[0].strip("/").lstrip("@")
    return re.sub(r"[^a-z0-9._]", "", h)


def _lead(d: dict, lid: str) -> dict | None:
    """By internal id or by the profile: "zen.marmitas", "@zen.marmitas" or its instagram.com URL (11/10: the agent
    passed the @ and the stage change was refused)."""
    lid = str(lid or "").strip()
    achado = next((l for l in d["leads"] if l["id"] == lid), None)
    if achado or not lid:
        return achado
    handle = lid.rstrip("/").rsplit("/", 1)[-1].lstrip("@").lower()
    return next((l for l in d["leads"] if str(l.get("handle", "")).lower() == handle), None)


# ------------------------------------------------------------------ lead score (fixed rubric, computed from evidence)

NOTA_MINIMA = 55   # below: not a lead
NOTA_QUENTE = 75   # first in line for the day's limited slots
PONTOS_SEGMENTO = {"marmitaria": 25, "congelados": 25, "cozinha_producao": 25, "fabrica": 22, "confeitaria": 20,
                   "salgados": 20, "doces": 18, "padaria": 15, "restaurante": 15, "outro_alimento": 5}
CANAIS_VENDA = ("ifood", "encomenda", "delivery", "whatsapp", "loja", "catalogo")
SINAIS = ("reajuste", "insumo", "expansao", "contratacao", "cardapio_precos", "kits", "promocao", "reclamacao_custo")
EXCLUSOES = {"rede": "rede ou franquia", "franquia": "rede ou franquia", "pessoal": "perfil pessoal",
             "privado": "perfil privado", "concorrente": "concorrente/sistema/consultoria",
             "curso": "curso/influenciador (é parceiro, não cliente)", "influencer": "curso/influenciador (é parceiro, não cliente)"}
REGIOES = ("salvador", "lauro de freitas", "camaçari", "camacari", "simões filho", "simoes filho", "candeias",
           "dias d'ávila", "dias davila", "madre de deus", "são francisco do conde", "vera cruz", "itaparica",
           "são paulo", "sao paulo", "campinas")


RADICAIS_SEGMENTO = (  # free text from the search round -> rubric key (the best-scoring match wins)
    (r"marmit|quentinha|fit ?food|refei[cç][aã]o (fit|saud)", "marmitaria"), (r"congelad", "congelados"),
    (r"cozinha|dark ?kitchen|produ[cç][aã]o pr[oó]pria|cozinha_producao", "cozinha_producao"),
    (r"f[aá]brica|ind[uú]stria|fabrica[cç][aã]o", "fabrica"), (r"confeit|bolo|torta", "confeitaria"),
    (r"salgad", "salgados"), (r"doce|brigadeiro|bombom|chocolat", "doces"), (r"padari|panifica|p[aã]es", "padaria"),
    (r"restaurante|refei[cç]|almo[cç]o|comida", "restaurante"),
    (r"lanchonete|caf[eé]|aliment|food|gastronom|outro_alimento", "outro_alimento"))


def segmento_rubrica(texto) -> str:
    t = str(texto or "").lower()
    achados = [k for rx, k in RADICAIS_SEGMENTO if re.search(rx, t)]
    return max(achados, key=lambda k: PONTOS_SEGMENTO[k]) if achados else ""


def _numero(seguidores) -> int:
    """'3.2k' / '18,9 mil' / '2.194' / 2194 -> 2194."""
    if isinstance(seguidores, (int, float)):
        return int(seguidores)
    s = str(seguidores or "").lower().replace(" ", "")
    mult = 1000 if ("k" in s or "mil" in s) else 1_000_000 if ("m" in s and "mil" not in s) else 1
    s = re.sub(r"[^0-9.,]", "", s)
    if mult > 1:
        s = s.replace(",", ".")
        try:
            return int(float(s) * mult)
        except ValueError:
            return 0
    return int(re.sub(r"[^0-9]", "", s) or 0)


def pontuar(item: dict) -> dict:
    """Score 0-100 with the breakdown, or {"rejeitado": why}. Every point comes from a piece of evidence the search
    round recorded (segmento, ultimo_post, seguidores, cidade, canais, sinais, cardapio, link_pedido, exclusoes)."""
    exclusoes = [str(x).lower() for x in (item.get("exclusoes") or [])]
    for x in exclusoes:
        if x in EXCLUSOES:
            return {"rejeitado": EXCLUSOES[x]}
    seg = segmento_rubrica(item.get("segmento"))
    if not seg:
        return {"rejeitado": f"segmento fora do playbook ({item.get('segmento')!r}); use: {', '.join(PONTOS_SEGMENTO)}"}
    try:
        ultimo = dt.date.fromisoformat(str(item.get("ultimo_post") or "")[:10])
        dias = (dt.datetime.fromtimestamp(agora(), _tz()).date() - ultimo).days
    except ValueError:
        if not item.get("atividade_pendente"):
            return {"rejeitado": "sem a data do último post NÃO fixado (ultimo_post AAAA-MM-DD)"}
        dias = None  # found outside Instagram (fontes.py): the warm-up visit checks the last post before following
    if dias is not None and dias > 30:
        return {"rejeitado": f"parado há {dias} dias"}
    seguidores = _numero(item.get("seguidores"))
    tamanho_pendente = bool(item.get("atividade_pendente")) and not seguidores  # checked on the warm-up visit
    if tamanho_pendente:
        pass
    elif seguidores < 300:
        return {"rejeitado": f"pequeno demais ({seguidores} seguidores)"}
    if seguidores > 50_000:
        return {"rejeitado": f"grande demais ({seguidores} seguidores: cara de rede)"}
    cidade = str(item.get("cidade") or "").lower()
    if not any(r in cidade for r in REGIOES):
        return {"rejeitado": f"fora da região ({item.get('cidade')})"}
    canais = {str(x).lower() for x in (item.get("canais") or [])} & set(CANAIS_VENDA)
    sinais = {str(x).lower() for x in (item.get("sinais") or [])} & set(SINAIS)
    partes = {
        "segmento": PONTOS_SEGMENTO[seg],
        "atividade": 12 if dias is None else 15 if dias <= 7 else 12 if dias <= 14 else 8,
        "porte": 12 if tamanho_pendente else 15 if 500 <= seguidores <= 5000 else 12 if seguidores <= 20_000 and seguidores > 5000 else 8 if seguidores > 20_000 else 6,
        "regiao": 10,
        "canais": min(10, 3 * len(canais) + (1 if len(canais) >= 3 else 0)),
        "sinais": min(15, 5 * len(sinais)),
        "profissional": (5 if item.get("cardapio") else 0) + (5 if item.get("link_pedido") else 0),
    }
    nota = sum(partes.values())
    return {"nota": nota, "partes": partes, "dias_ultimo_post": dias, "seguidores_n": seguidores, "segmento_rubrica": seg,
            "faixa": "quente" if nota >= NOTA_QUENTE else "bom" if nota >= 65 else "ok" if nota >= NOTA_MINIMA else "fraco"}


def registrar(login: str, novos: list) -> dict:
    """Add leads (dedupe by @handle). Returns {"criados": [...], "repetidos": [...], "recusados": [...]}."""
    d = carregar(login)
    por_handle = {l["handle"]: l for l in d["leads"]}
    out = {"criados": [], "repetidos": [], "recusados": []}
    for item in novos if isinstance(novos, list) else []:
        if not isinstance(item, dict):
            continue
        canal = str(item.get("canal") or "instagram").lower()
        handle = normalizar(str(item.get("handle") or item.get("url") or ""))
        faltam = [c for c in ("nome", "segmento", "cidade", "motivo") if not str(item.get(c) or "").strip()]
        if canal not in CANAIS or not handle or faltam:
            out["recusados"].append({"handle": handle or "?", "motivo": f"faltam: {', '.join(faltam) or 'canal/handle'}"})
            continue
        if handle in por_handle:
            out["repetidos"].append({"handle": handle, "id": por_handle[handle]["id"], "etapa": por_handle[handle]["etapa"]})
            continue
        avaliacao = pontuar(item) if canal == "instagram" else {"nota": None}
        if avaliacao.get("rejeitado") or (avaliacao.get("nota") is not None and avaliacao["nota"] < NOTA_MINIMA):
            motivo_rej = avaliacao.get("rejeitado") or f"nota {avaliacao['nota']} (mínimo {NOTA_MINIMA}): {avaliacao['partes']}"
            d.setdefault("rejeitados", {})[handle] = {"motivo": motivo_rej[:160], "em": agora()}
            out["recusados"].append({"handle": handle, "motivo": motivo_rej})
            continue
        lead = {"id": _id(), "canal": canal, "handle": handle, "nota": avaliacao.get("nota"), "faixa": avaliacao.get("faixa", "?"),
                "avaliacao": {k: avaliacao[k] for k in ("partes", "faixa", "dias_ultimo_post", "seguidores_n", "segmento_rubrica")
                              if k in avaliacao},
                "evidencias": {k: item.get(k) for k in ("ultimo_post", "canais", "sinais", "cardapio", "link_pedido",
                                                         "produto_exemplo", "post_recente") if item.get(k)},
                "url": str(item.get("url") or f"https://www.instagram.com/{handle}/")[:200],
                "nome": str(item["nome"])[:80], "segmento": str(item["segmento"])[:40].lower(),
                "cidade": str(item["cidade"])[:60], "seguidores": str(item.get("seguidores") or "")[:20],
                "motivo": str(item["motivo"])[:300], "sinal": str(item.get("sinal") or "")[:300],
                "etapa": "novo", "criado": agora(), "atualizado": agora(), "historico": []}
        if item.get("atividade_pendente") and not item.get("ultimo_post"):
            lead["conferir_atividade"] = True  # found outside Instagram: last post checked on the warm-up visit
            lead["fonte"] = str(item.get("fonte") or "")[:40]
        d["leads"].append(lead)
        por_handle[handle] = lead
        out["criados"].append({"handle": handle, "id": lead["id"], "nota": lead["nota"],
                               "faixa": lead["avaliacao"].get("faixa")})
    salvar(login, d)
    return out


# ------------------------------------------------------------------ fast evaluation (many profiles in one browser call)

SCRIPT_PERFIS = """(async () => {
  const handles = __HANDLES__;
  const out = [];
  for (const h of handles) {
    try {
      const r = await fetch('/api/v1/users/web_profile_info/?username=' + encodeURIComponent(h),
                            {headers: {'x-ig-app-id': '936619743392459'}, credentials: 'include'});
      if (r.status === 429) { out.push({handle: h, erro: 'http 429'}); break; }
      if (!r.ok) { out.push({handle: h, erro: 'http ' + r.status}); await new Promise(f => setTimeout(f, 3000)); continue; }
      const u = ((await r.json()).data || {}).user;
      if (!u) { out.push({handle: h, erro: 'perfil não encontrado'}); continue; }
      const posts = ((u.edge_owner_to_timeline_media || {}).edges || []).slice(0, 8).map(e => ({
        fixado: (e.node.pinned_for_users || []).length > 0,
        ts: e.node.taken_at_timestamp,
        codigo: e.node.shortcode,
        legenda: (((e.node.edge_media_to_caption || {}).edges || [])[0] || {node: {text: ''}}).node.text.slice(0, 200)
      }));
      out.push({handle: u.username, nome: u.full_name, seguidores: (u.edge_followed_by || {}).count, privado: u.is_private,
                bio: (u.biography || '').slice(0, 300), link: u.external_url || '',
                categoria: u.category_name || u.business_category_name || '', posts: posts});
    } catch (e) { out.push({handle: h, erro: String(e).slice(0, 80)}); }
    await new Promise(f => setTimeout(f, 3000));
  }
  return JSON.stringify(out);
})()"""

RX_CANAIS = {"ifood": r"ifood", "encomenda": r"encomend|sob encomenda|pedidos? antecipad", "delivery": r"delivery|entrega",
             "whatsapp": r"whats|wa\.me|zap", "loja": r"\bloja\b|retirada|endere[cç]o|\brua\b|\bav\.", "catalogo": r"cat[aá]logo"}
RX_SINAIS = {"reajuste": r"reajust|novos? pre[cç]os|aumento", "insumo": r"insumo|mat[eé]ria[- ]prima|ingrediente.*(caro|sub)",
             "expansao": r"nova unidade|segunda unidade|inaugura|nova loja", "contratacao": r"contratando|vaga|estamos contratando",
             "cardapio_precos": r"card[aá]pio.*(r\$|pre[cç])|r\$ ?\d", "kits": r"\bkits?\b|combo", "promocao": r"promo|desconto|oferta"}
RX_EXCLUSOES = {"franquia": r"franquia|franqueado", "curso": r"\bcurso|mentoria|aulas?\b|aprenda"}


SCRIPT_BUSCA = """(async () => {
  const termos = __TERMOS__;
  const achados = {};
  const pegar = (texto, termo) => {
    for (const m of texto.matchAll(/"username":"([A-Za-z0-9._]{2,30})"/g)) {
      const h = m[1].toLowerCase();
      if (!achados[h]) achados[h] = termo;
    }
  };
  for (const t of termos) {
    const q = encodeURIComponent(t);
    try {
      const r = await fetch('/web/search/topsearch/?context=blended&include_reel=false&query=' + q,
                            {headers: {'x-ig-app-id': '936619743392459'}, credentials: 'include'});
      if (r.status === 429) break;
      if (r.ok) pegar(await r.text(), t);
    } catch (e) {}
    await new Promise(f => setTimeout(f, 1500));
  }
  return JSON.stringify(Object.keys(achados).map(h => ({handle: h, termo: achados[h]})));
})()"""


def montar_busca(termos: list) -> str:
    ts = [str(t).strip()[:40] for t in termos if str(t).strip()][:3]  # evaluate times out at 30 s
    return SCRIPT_BUSCA.replace("__TERMOS__", json.dumps(ts, ensure_ascii=False))


def novos_handles(login: str, achados, limite: int = 30) -> list:
    """Handles found by the search script minus the ones already known or rejected (and our own accounts)."""
    lista = json.loads(achados) if isinstance(achados, str) else (achados or [])
    d = carregar(login)
    ja = {l["handle"] for l in d["leads"]} | set(d.get("rejeitados") or {}) | set(CONTAS_PROIBIDAS) | {conta(login)}
    out = []
    for x in lista if isinstance(lista, list) else []:
        h = normalizar(str(x.get("handle") if isinstance(x, dict) else x))
        if h and h not in ja and h not in out:
            out.append(h)
    return out[:limite]


def api_pausada(login: str) -> str:
    """'' or until when the profile scripts are paused after an Instagram 429."""
    ate = carregar(login)["config"].get("api_pausa_ate") or 0
    return dt.datetime.fromtimestamp(ate, _tz()).strftime("%H:%M") if agora() < ate else ""


# ------------------------------------------------------------------ official API (Instagram Graph "business discovery")

GRAPH = "https://graph.facebook.com/v21.0"
COFRE_TOKEN, COFRE_IG = "META_IG_TOKEN", "META_IG_USER_ID"


def _cofre():
    import importlib.util as iu
    spec = iu.spec_from_file_location("cofre_helper_pro", "/a0/usr/plugins/cofre/helpers/cofre.py")
    m = iu.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def _graph(caminho: str, params: dict) -> dict:
    import urllib.error, urllib.parse, urllib.request
    url = f"{GRAPH}/{caminho}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"error": {"message": f"http {e.code}"}}


def guardar_token_meta(login: str, token_usuario: str) -> dict:
    """From a (long-lived) user token: find the Page linked to the prospecting Instagram account, keep ITS token
    (a Page token from a long-lived user token does not expire) and the IG user id in the owner's vault. Returns a
    summary without secrets."""
    esperado = conta(login) or "raiz.connect"
    r = _graph("me/accounts", {"fields": "name,access_token,instagram_business_account{id,username}", "limit": 50,
                               "access_token": token_usuario})
    if r.get("error"):
        return {"ok": False, "erro": r["error"].get("message", "")[:200]}
    paginas = r.get("data") or []
    alvo = next((pg for pg in paginas if (pg.get("instagram_business_account") or {}).get("username", "").lower() == esperado), None)
    if not alvo:
        ligadas = {pg.get("name"): (pg.get("instagram_business_account") or {}).get("username") for pg in paginas}
        return {"ok": False, "erro": f"nenhuma Página ligada a @{esperado}", "paginas": ligadas}
    c = _cofre()
    c.salvar(login, COFRE_TOKEN, alvo["access_token"]); c.descrever(login, COFRE_TOKEN, f"Meta · token da Página {alvo['name']} (leitura do Instagram @{esperado})")
    c.salvar(login, COFRE_IG, alvo["instagram_business_account"]["id"]); c.descrever(login, COFRE_IG, f"Meta · id da conta @{esperado}")
    info = _graph("debug_token", {"input_token": alvo["access_token"], "access_token": alvo["access_token"]}).get("data") or {}
    expira = info.get("expires_at", 0)
    return {"ok": True, "pagina": alvo["name"], "instagram": esperado,
            "expira": "nunca" if not expira else dt.datetime.fromtimestamp(expira, _tz()).strftime("%d/%m/%Y")}


def descobrir_perfis(login: str, handles: list) -> list:
    """Profile data through the official API, in the same shape the browser script returns (so avaliar_perfis
    reads both). Accounts that are not business/creator come back as an error (personal profiles: out anyway)."""
    segredos = _cofre().carregar(login)
    token, ig = segredos.get(COFRE_TOKEN), segredos.get(COFRE_IG)
    if not token or not ig:
        return [{"handle": "-", "erro": "API da Meta não configurada (falta o token no cofre)"}]
    out = []
    for h in [normalizar(str(x)) for x in handles if normalizar(str(x))][:30]:
        campos = (f"business_discovery.username({h}){{username,name,biography,website,followers_count,"
                  "media.limit(8){timestamp,caption,permalink}}")
        r = _graph(ig, {"fields": campos, "access_token": token})
        if r.get("error"):
            msg = r["error"].get("message", "")
            out.append({"handle": h, "erro": "limite da API (espere)" if r["error"].get("code") in (4, 17, 32, 613)
                        else "conta pessoal ou inexistente" if "business" in msg.lower() or "username" in msg.lower() or r["error"].get("code") == 110
                        else msg[:120]})
            continue
        b = r.get("business_discovery") or {}
        posts = []
        for m in (b.get("media") or {}).get("data") or []:
            try:
                ts = int(dt.datetime.strptime(m["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp())
            except Exception:
                continue
            codigo = (m.get("permalink") or "").rstrip("/").split("/")[-1]
            posts.append({"fixado": False, "ts": ts, "codigo": codigo, "legenda": (m.get("caption") or "")[:200]})
        out.append({"handle": b.get("username", h), "nome": b.get("name") or h, "seguidores": b.get("followers_count") or 0,
                    "privado": False, "bio": (b.get("biography") or "")[:300], "link": b.get("website") or "",
                    "categoria": "", "posts": posts})
    return out


SCRIPT_DIRECT = """(async () => {
  const pegar = async (url) => {
    try {
      const r = await fetch(url, {headers: {'x-ig-app-id': '936619743392459'}, credentials: 'include'});
      return r.ok ? await r.json() : {erro: 'http ' + r.status};
    } catch (e) { return {erro: String(e).slice(0, 80)}; }
  };
  const resumir = (j) => {
    const caixa = j.inbox || {};
    return {erro: j.erro || '', threads: (caixa.threads || []).slice(0, 40).map(t => ({
      usuarios: (t.users || []).map(u => u.username),
      itens: (t.items || []).slice(0, 6).map(i => ({de_mim: String(i.user_id) === String(j.viewer ? j.viewer.pk : ''),
        tipo: i.item_type, texto: (i.text || '').slice(0, 300), ts: Math.floor((i.timestamp || 0) / 1e6)}))}))};
  };
  const principal = await pegar('/api/v1/direct_v2/inbox/?persistentBadging=true&limit=40&thread_message_limit=6');
  await new Promise(f => setTimeout(f, 1500));
  const pedidos = await pegar('/api/v1/direct_v2/pending_inbox/?limit=40&thread_message_limit=6');
  return JSON.stringify({principal: resumir(principal), pedidos: resumir(pedidos)});
})()"""


def processar_direct(login: str, dados) -> dict:
    """Reads the Direct inbox JSON (from SCRIPT_DIRECT): every known lead whose newest message is theirs is marked
    "respondeu" with what they wrote (recorded once per message). Returns the new answers and a count for conferido."""
    j = json.loads(dados) if isinstance(dados, str) else (dados or {})
    d = carregar(login)
    por_handle = {l["handle"]: l for l in d["leads"]}
    novas, conversas, erros = [], 0, []
    for pasta in ("principal", "pedidos"):
        caixa = j.get(pasta) or {}
        if caixa.get("erro"):
            erros.append(f"{pasta}: {caixa['erro']}")
        for t in caixa.get("threads") or []:
            conversas += 1
            itens = [i for i in t.get("itens") or [] if i.get("tipo") in ("text", "link", "media_share", "voice_media", "clip", "media")]
            if not itens or itens[0].get("de_mim"):
                continue  # newest message is ours: nothing new from them
            for u in t.get("usuarios") or []:
                lead = por_handle.get(normalizar(u))
                if not lead or lead["etapa"] in ("cliente", "descartado"):
                    continue
                texto = itens[0].get("texto") or f"({itens[0].get('tipo')})"
                etapa = lead["etapa"] if lead["etapa"] in ("respondeu", "lead", "demo", "teste") else "respondeu"
                r = mudar_etapa(login, lead["id"], etapa, texto, "direct")
                if r and r.get("novidade"):
                    novas.append({"lead_id": lead["id"], "handle": lead["handle"], "nome": lead["nome"], "texto": texto,
                                  "pasta": pasta, "url": lead["url"]})
    return {"novas": novas, "conversas": conversas, "erros": erros}


def montar_script(handles: list) -> str:
    hs = [normalizar(str(h)) for h in handles if normalizar(str(h))][:5]  # 5 x 3 s: under the 30 s evaluate limit, gentle
    return SCRIPT_PERFIS.replace("__HANDLES__", json.dumps(hs))


def _evidencia(perfil: dict) -> dict:
    """Evidence for pontuar() read straight from the profile data (no model judgment)."""
    texto_bio = f"{perfil.get('nome', '')} {perfil.get('categoria', '')} {perfil.get('bio', '')}".lower()
    posts = [x for x in perfil.get("posts") or [] if x.get("ts")]
    nao_fixados = sorted((x for x in posts if not x.get("fixado")), key=lambda x: -x["ts"])
    legendas = " ".join(x.get("legenda", "") for x in posts[:6]).lower()
    tudo = f"{texto_bio} {legendas} {perfil.get('link', '').lower()}"
    ultimo = nao_fixados[0] if nao_fixados else None
    cidade = next((r for r in REGIOES if r in texto_bio), "")
    return {
        "handle": perfil["handle"], "canal": "instagram", "nome": (perfil.get("nome") or perfil["handle"])[:80],
        "segmento": segmento_rubrica(f"{perfil.get('categoria', '')} {perfil.get('nome', '')} {perfil.get('bio', '')}") or "",
        "cidade": cidade.title() if cidade else "", "seguidores": perfil.get("seguidores") or 0,
        "ultimo_post": dt.datetime.fromtimestamp(ultimo["ts"], _tz()).date().isoformat() if ultimo else "",
        "canais": [c for c, rx in RX_CANAIS.items() if re.search(rx, tudo)],
        "sinais": [c for c, rx in RX_SINAIS.items() if re.search(rx, legendas)],
        "cardapio": bool(re.search(r"card[aá]pio|menu", tudo)),
        "link_pedido": bool(re.search(r"ifood|wa\.me|whats|linktr|anota|goomer|pedido|card[aá]pio|menu", perfil.get("link", "").lower())),
        "exclusoes": (["privado"] if perfil.get("privado") else []) + [c for c, rx in RX_EXCLUSOES.items() if re.search(rx, texto_bio)],
        "post_recente": (ultimo.get("legenda") or "")[:150] if ultimo else "",
        "url_post_recente": f"https://www.instagram.com/p/{ultimo['codigo']}/" if ultimo and ultimo.get("codigo") else "",
        "motivo": (f"{perfil.get('categoria') or 'negócio'}; bio: {perfil.get('bio', '')[:140]}"
                   + (f"; último post {dt.datetime.fromtimestamp(ultimo['ts'], _tz()).strftime('%d/%m')}: {(ultimo.get('legenda') or '')[:80]}" if ultimo else "")),
        "sinal": "",
    }


def avaliar_perfis(login: str, dados) -> dict:
    """Takes the JSON the browser script returned. Registers what fits (with its score), rejects what clearly does
    not, and returns only what needs a human look (city or segment not in the bio)."""
    perfis = json.loads(dados) if isinstance(dados, str) else (dados or [])
    out = {"criados": [], "recusados": [], "conferir": [], "erros": []}
    para_registrar = []
    for perfil in perfis if isinstance(perfis, list) else []:
        if not isinstance(perfil, dict) or not perfil.get("handle"):
            continue
        if perfil.get("erro"):
            out["erros"].append({"handle": perfil["handle"], "erro": perfil["erro"]})
            continue
        ev = _evidencia(perfil)
        if not ev["segmento"] or not ev["cidade"]:
            # the hard filters still apply before anyone spends time opening the profile
            teste = pontuar({**ev, "segmento": ev["segmento"] or "outro_alimento", "cidade": ev["cidade"] or "salvador"})
            if teste.get("rejeitado") and "segmento" not in teste["rejeitado"] and "região" not in teste["rejeitado"]:
                rejeitar(login, [{"handle": ev["handle"], "motivo": teste["rejeitado"]}])
                out["recusados"].append({"handle": ev["handle"], "motivo": teste["rejeitado"]})
            else:
                falta = [c for c in ("segmento", "cidade") if not ev[c]]
                out["conferir"].append({"falta": falta, "item": ev})
            continue
        para_registrar.append(ev)
    if any("429" in e["erro"] for e in out["erros"]):  # Instagram rate limit: profile scripts pause for 15 min
        d = carregar(login)
        d["config"]["api_pausa_ate"] = agora() + 15 * 60
        salvar(login, d)
    if para_registrar:
        r = registrar(login, para_registrar)
        out["criados"] += r["criados"]
        out["recusados"] += r["recusados"]
        out["recusados"] += [{"handle": x["handle"], "motivo": "já conhecido"} for x in r["repetidos"]]
    return out


REJEITADO_DIAS = 60


def rejeitar(login: str, itens: list) -> int:
    """Profiles examined that do not fit, with why: skipped by later rounds for 60 days, and auditable."""
    d = carregar(login)
    rej = d.setdefault("rejeitados", {})
    n = 0
    for item in itens if isinstance(itens, list) else []:
        h = normalizar(str((item or {}).get("handle") or ""))
        if h and not any(l["handle"] == h for l in d["leads"]):
            rej[h] = {"motivo": str(item.get("motivo") or "")[:160], "em": agora()}
            n += 1
    corte = agora() - REJEITADO_DIAS * 86400
    d["rejeitados"] = {h: v for h, v in rej.items() if v["em"] > corte}
    salvar(login, d)
    return n


ONDE = ("direct", "comentario")


def _citacao(nota: str) -> str:
    """The person's own words inside the note («…», “…” or "…"), normalized; the whole note when nothing is quoted.
    Rounds describe the same answer in different words around the same quote (11/10: Zen was announced twice)."""
    trechos = re.findall(r"«([^»]+)»|“([^”]+)”|\"([^\"]+)\"", nota or "")
    texto = " ".join(next(t for t in g if t) for g in trechos) if trechos else (nota or "")
    return re.sub(r"[^\w]+", " ", texto.lower()).strip()


def mudar_etapa(login: str, lid: str, etapa: str, nota: str = "", onde: str = "direct") -> dict | None:
    """New stage. The returned lead carries "novidade": False when the same answer was already recorded (rounds
    re-read the same Direct/notifications every half hour; the person must hear about each answer once)."""
    d = carregar(login)
    lead = _lead(d, lid)
    if not lead or etapa not in ETAPAS:
        return None
    onde = onde if onde in ONDE else "direct"
    nota = nota[:300]
    repetida = any(h["tipo"] == f"etapa:{etapa}" and _citacao(h.get("texto", "")) == _citacao(nota)
                   and h.get("onde", "direct") == onde for h in lead["historico"])
    falas = [h for h in lead["historico"] if str(h.get("tipo", "")).startswith("etapa:")]
    if not repetida and falas and lead["etapa"] == etapa and falas[-1].get("onde", "direct") == onde == "comentario":
        # the same comment reply described in other words, with no quote (11/10: Anna announced twice): while we
        # have not answered it yet, a reply in the comments re-read by the next round is not news
        respondemos = any(a["lead_id"] == lead["id"] and a["tipo"] == "resposta" and a["estado"] == "executada"
                          and a.get("executada_em", 0) > falas[-1]["em"] for a in d["acoes"])
        repetida = not respondemos
    if repetida and lead["etapa"] == etapa:
        return {**lead, "novidade": False}
    lead["etapa"], lead["atualizado"] = etapa, agora()
    lead["historico"].append({"em": agora(), "tipo": f"etapa:{etapa}", "texto": nota, "onde": onde})
    if etapa in FINAIS or etapa in ("respondeu", "lead"):  # pending outreach stops when they answer or are closed
        for a in d["acoes"]:
            if a["lead_id"] == lead["id"] and a["estado"] in ("proposta", "aprovada") and a["tipo"] != "resposta":
                _mudar(d, a, "cancelada", f"lead foi para {etapa}", decidida=agora())
    salvar(login, d)
    return {**lead, "novidade": True}


def fechar_vencidos(login: str) -> int:
    """Leads that got the reminder and stayed silent become sem_resposta (no third message, ever)."""
    d = carregar(login)
    n = 0
    for l in d["leads"]:
        if l["etapa"] == "lembrado" and agora() - l["atualizado"] > ESPERA_FIM:
            l["etapa"], l["atualizado"] = "sem_resposta", agora()
            n += 1
    if n:
        salvar(login, d)
    return n


def _dias_desde(ts: float) -> int:
    """Calendar days (America/Bahia) between ts and now."""
    return (dt.datetime.fromtimestamp(agora(), _tz()).date() - dt.datetime.fromtimestamp(ts, _tz()).date()).days


# Lead stock (Matheus, 12/10: "manter um estoque de 100 — o que consumir, buscar"): the search rounds refill the
# queue of new leads up to this target; the execution rounds consume it (refill of «aquecer» slots).
ESTOQUE_ALVO = 100


def estoque(login: str) -> dict:
    """New leads ready to be warmed (Instagram, never tried) vs the target: {"prontos", "alvo", "faltam"}."""
    d = carregar(login)
    tentados = {a["lead_id"] for a in d["acoes"] if a["tipo"] == "aquecer" and a["estado"] in ("falhou", "cancelada")}
    prontos = sum(1 for l in d["leads"] if l["etapa"] == "novo" and l["canal"] == "instagram" and l["id"] not in tentados)
    alvo = int(d["config"].get("estoque_alvo") or ESTOQUE_ALVO)
    return {"prontos": prontos, "alvo": alvo, "faltam": max(0, alvo - prontos)}


def _fila_repor(login: str) -> list:
    """Best new lead that may take a free «aquecer» slot today ([] when none or no pre-approval)."""
    d = carregar(login)
    if not d["config"].get("auto") or cotas(login)["aquecer"] <= 0:
        return []
    tentados = {a["lead_id"] for a in d["acoes"] if a["tipo"] == "aquecer" and a["estado"] in ("falhou", "cancelada")}
    return [l for l in devidos(login)["aquecer"] if l["id"] not in tentados][:1]  # a failed visit is not retried


def repor_aquecer(login: str) -> int:
    """Fill the day's free «aquecer» slots with the best new leads (follow + like, no text, so no reviewer needed).
    11/10: the 9h23 round proposed 8, the visit discarded 5 (stale, too big, wrong business) and nobody refilled:
    only 3 of 8 slots were used. One lead per call: the execution round asks again after each action."""
    fila = _fila_repor(login)
    if not fila:
        return 0
    out = propor(login, [{"lead_id": fila[0]["id"], "tipo": "aquecer", "texto": "",
                          "base": "reposição automática: vaga do dia livre depois de um descarte"}])
    return len(out.get("automaticas", []))


def devidos(login: str) -> dict:
    """What each lead needs next, by the playbook's timing."""
    d = carregar(login)
    pendentes = {a["lead_id"] for a in d["acoes"] if a["estado"] in ("proposta", "aprovada")}
    out = {"dm_abertura": [], "dm_lembrete": [], "aquecer": []}
    for l in d["leads"]:
        if l["id"] in pendentes or l["canal"] != "instagram":
            continue
        dias = _dias_desde(l["atualizado"])
        if l["etapa"] == "novo":
            out["aquecer"].append(l)
        elif l["etapa"] == "aquecido" and dias >= DIAS_DM:
            out["dm_abertura"].append(l)
        elif l["etapa"] == "abordado" and dias >= DIAS_LEMBRETE:
            out["dm_lembrete"].append(l)
    for lista in out.values():  # who engaged back first, then best fit: the day's slots are limited
        lista.sort(key=lambda l: (not l.get("interagiu"), -(l.get("nota") if l.get("nota") is not None else 60)))
    return out


# ------------------------------------------------------------------ actions

LIMITE_PILOTO = {"aquecer": 15, "dm_abertura": 5, "dm_lembrete": 5, "resposta": 15, "parceiro": 3}  # aquecer 8 → 15: Matheus, 12/10


def limites(d: dict) -> dict:
    """Daily limits: the config's, else the pilot's for the first 7 days, else the playbook's."""
    if d["config"].get("limites"):
        return {**LIMITE_DIA, **d["config"]["limites"]}
    inicio = d["config"].get("inicio") or (min([l["criado"] for l in d["leads"]] or [agora()]))
    return LIMITE_PILOTO if agora() - inicio < 7 * 86400 else LIMITE_DIA


def _usadas_hoje(d: dict, tipo: str) -> int:
    hoje = _hoje_local()
    return sum(1 for a in d["acoes"] if a["tipo"] == tipo and a["estado"] in ("proposta", "aprovada", "executada")
               and _hoje_local(a.get("executada_em") or a.get("decidida") or a["criada"]) == hoje)


def cotas(login: str) -> dict:
    d = carregar(login)
    lim = limites(d)
    return {t: max(0, lim[t] - _usadas_hoje(d, t)) for t in TIPOS}


def validar_texto(tipo: str, texto: str, d: dict, lid: str) -> str:
    """'' when the text may be proposed, else why not (playbook rules a model could slip on)."""
    t = (texto or "").strip()
    if tipo == "aquecer":
        if t and (len(t) > 220 or LINK.search(t) or re.search(r"raiz", t, re.I)):
            return "comentário de aquecimento: até 220 caracteres, sem link e sem citar a Raiz"
        return ""
    if len(t) < 40:
        return "mensagem curta demais para ser específica"
    if len(t) > 900:
        return "mensagem longa demais para uma DM (até 900 caracteres)"
    sem_calculadora = CALCULADORA.sub("", t)
    if LINK.search(sem_calculadora) or (tipo not in TIPOS_COM_LINK and CALCULADORA.search(t)):
        return (f"link só o da calculadora ({LINK_CALCULADORA}) ou o do simulador de delivery ({LINK_DELIVERY}), e só no "
                "lembrete ou na resposta a quem escreveu" if tipo in TIPOS_COM_LINK
                else "sem link na primeira mensagem nem em mensagem a parceiro")
    if tipo != "resposta" and PROIBIDAS.search(t):
        return f"palavra fora do tom do playbook: «{PROIBIDAS.search(t).group(0)}»"
    if tipo in ("dm_abertura", "parceiro") and not re.search(r"matheus", t, re.I):
        return "assine como Matheus, da Raiz Connect"
    norma = re.sub(r"\W+", " ", t.lower())
    for a in d["acoes"]:  # the same message to two people is mass messaging
        if a["lead_id"] != lid and a.get("texto") and a["estado"] in ("proposta", "aprovada", "executada"):
            outra = re.sub(r"\W+", " ", a["texto"].lower())
            if norma == outra or (len(norma) > 80 and _parecido(norma, outra) > 0.9):
                return "texto igual (ou quase) ao de outra pessoa — personalize"
    return ""


def _parecido(a: str, b: str) -> float:
    import difflib

    return difflib.SequenceMatcher(None, a, b).ratio()


def propor(login: str, itens: list) -> dict:
    """Validate and store proposed actions. Returns {"propostas": [...acoes], "recusadas": [{...,"motivo"}]}."""
    d = carregar(login)
    out = {"propostas": [], "recusadas": []}
    restantes = cotas(login)
    ja = {(a["lead_id"], a["tipo"]) for a in d["acoes"] if a["estado"] in ("proposta", "aprovada")}
    for item in itens if isinstance(itens, list) else []:
        if not isinstance(item, dict):
            continue
        tipo = str(item.get("tipo") or "").lower()
        lid = str(item.get("lead_id") or "")
        lead = _lead(d, lid)
        if lead:
            lid = lead["id"]  # the agent may have passed the @
        texto = str(item.get("texto") or "").strip()
        motivo = ""
        if tipo not in TIPOS:
            motivo = f"tipo inválido (use {', '.join(TIPOS)})"
        elif not lead:
            motivo = "lead não encontrado (registre antes)"
        elif lead["etapa"] in FINAIS and not (tipo == "resposta" and lead["etapa"] == "descartado"):
            motivo = f"lead encerrado ({lead['etapa']}): não contate de novo"
        elif (lid, tipo) in ja:
            motivo = "já existe essa ação pendente para esse lead"
        elif d["config"].get("auto") and _versoes_reprovadas(d, lid, tipo) >= VERSOES_REVISOR:
            motivo = f"o revisor já reprovou {VERSOES_REVISOR} versões hoje: deixe para amanhã"
        elif tipo == "dm_abertura" and lead["etapa"] != "aquecido":
            motivo = "DM de abertura só depois do aquecimento"
        elif tipo == "dm_lembrete" and lead["etapa"] != "abordado":
            motivo = "lembrete só para quem recebeu a abertura e não respondeu"
        elif tipo == "dm_lembrete" and _dias_desde(lead["atualizado"]) < DIAS_LEMBRETE:
            motivo = "cedo demais para o lembrete"
        elif tipo == "resposta" and lead["etapa"] not in ("respondeu", "lead", "demo", "teste", "descartado"):
            motivo = "resposta só para quem escreveu"
        elif tipo == "resposta" and _ja_respondido(d, lead):
            motivo = "já respondemos a última fala dessa pessoa: espere ela escrever de novo (registre com `etapa`)"
        elif tipo == "resposta" and _resposta_falhou(d, lead):
            motivo = ("a resposta a essa fala já falhou no Instagram (Direct fechado para nós?): não proponha de novo; "
                      "o Matheus já foi avisado e decide")
        elif tipo == "parceiro" and lead["canal"] != "parceiro":
            motivo = "ação de parceiro só para leads do canal parceiro"
        elif restantes.get(tipo, 0) <= 0:
            motivo = f"limite do dia para {tipo} atingido"
        else:
            motivo = validar_texto(tipo, texto, d, lid)
        if motivo:
            out["recusadas"].append({"lead_id": lid, "tipo": tipo, "motivo": motivo})
            continue
        variante = str(item.get("variante") or "").upper()[:1]
        if tipo == "dm_abertura" and variante not in ("A", "B"):
            variante = "A" if sum(1 for a in d["acoes"] if a["tipo"] == "dm_abertura") % 2 == 0 else "B"
        acao = {"id": _id(), "lead_id": lid, "tipo": tipo, "texto": texto[:900], "variante": variante,
                "alvo": str(item.get("alvo") or lead["url"])[:200], "base": str(item.get("base") or "")[:300],
                "estado": "proposta", "criada": agora()}
        d["acoes"].append(acao)
        _evento(d, acao, "-", "proposta", "proposta criada")
        ja.add((lid, tipo))
        restantes[tipo] -= 1
        out["propostas"].append(acao)
    salvar(login, d)
    if d["config"].get("auto"):
        out = _auto_aprovar(login, out)
    return out


# ------------------------------------------------------------------ pre-approved within the daily limits

AUTO_TIPOS = ("aquecer", "dm_abertura", "dm_lembrete", "resposta", "parceiro")
# Matheus, 12/10: "não preciso aprovar as coisas do Instagram, pode me avisar que foi feito". With pre-approval on
# and config sem_aprovacao (default true), what the reviewer rejects is NOT sent to his phone: the agent rewrites it
# by the reviewer's reason, up to VERSOES_REVISOR versions per lead and type a day.
VERSOES_REVISOR = 3
PROXY = "http://host.docker.internal:8787"
MODELO_REVISOR = "openai.gpt-6-luna"
revisor = None  # tests replace it: fn(pedido: str) -> str

REVISOR = """Você é o revisor independente das mensagens de prospecção da Raiz Connect. O dono autorizou que elas saiam
SEM perguntar a ele, então você é a última barreira antes de uma pessoa real recebê-las. Reprove um item SÓ se:
1. Afirma um fato sobre o negócio (prato, unidade, novidade, número, cidade) que NÃO está nos DADOS DO LEAD nem no que
   o agente diz ter visto. Pergunta não é afirmação ("ele entra no kit?" é aceitável); elogio a algo que está nos
   dados também é.
2. Fere o playbook: comentário de aquecimento que vende, cita a Raiz, um sistema ou chama para o direct; jargão
   (ERP, sistema de gestão, CMV, solução) na abertura; promessa de resultado ou número inventado; pressão; link na
   primeira mensagem (os únicos links permitidos são a calculadora de precificação e o simulador de delivery da
   Raiz, no lembrete e nas respostas — e são opcionais: lembrete sem link também vale); primeira mensagem
   sem a assinatura do Matheus. A primeira mensagem pode ser só uma pergunta sobre como a pessoa precifica (variante
   A) ou já trazer a oferta da calculadora grátis (variante B): as duas são válidas. Pedir a receita da pessoa
   ("me manda a receita", ficha técnica) fere o playbook: soa invasivo.
3. Soa como spam, intimidade forçada ou constrange a pessoa.
4. Tem erro de português ou abreviação de internet que faça a marca parecer descuidada.
5. Numa resposta: não combina com O QUE A PESSOA DISSE (ignora a pergunta dela, insiste depois de um não, ou finge
   uma conversa que não houve).
Os modelos do playbook são guia, não texto fixo: variações naturais são boas (falar de entrega, embalagem ou iFood ao
explicar o cálculo; outra forma de oferecer a calculadora; outro elogio verdadeiro). Não reprove por estilo.
Na dúvida REAL sobre fato ou respeito, reprove: o item volta ao dono para ele decidir, nada se perde.
Responda só JSON: {"itens": [{"id": "<id>", "aprovado": true|false, "motivo": "<uma frase>"}]}"""


def _chamar_revisor(pedido: str) -> str:
    if revisor:
        return revisor(pedido)
    import urllib.request

    body = {"model": MODELO_REVISOR, "reasoning": {"effort": "medium"}, "input": [{"role": "user", "content": pedido}]}
    req = urllib.request.Request(f"{PROXY}/openai/v1/responses", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    return "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []) if c.get("type") == "output_text")


def _ja_respondido(d: dict, lead: dict) -> bool:
    """True when our last sent reply is newer than the person's last recorded words: no second reply to the same line
    (replies leave without the person's ✅ since 11/10)."""
    falas = [h["em"] for h in lead.get("historico", []) if str(h.get("tipo", "")).startswith("etapa:")]
    enviadas = [a.get("executada_em", 0) for a in d["acoes"]
                if a["lead_id"] == lead["id"] and a["tipo"] == "resposta" and a["estado"] == "executada"]
    return bool(enviadas) and (not falas or max(enviadas) >= max(falas))


def _resposta_falhou(d: dict, lead: dict) -> bool:
    """A reply to the person's latest words already failed (e.g. Message button disabled): stop the retry loop."""
    falas = [h["em"] for h in lead.get("historico", []) if str(h.get("tipo", "")).startswith("etapa:")]
    ultima = max(falas) if falas else 0
    minhas = [a for a in d["acoes"] if a["lead_id"] == lead["id"] and a["tipo"] == "resposta"
              and a.get("executada_em", 0) >= ultima]
    if any(a["estado"] in ("executada", "apagada") for a in minhas):
        return False  # a later attempt went through (11/10 zen.marmitas: two early "failed" kept blocking for good)
    return any(a["estado"] == "falhou" for a in minhas)


def marcar_apagada(login: str, aid: str, detalhe: str = "") -> dict | None:
    """An executed message that was deleted (unsent) in the Instagram: it no longer counts as answered, so one
    new message can go (11/10: the only reply to @zen.marmitas was deleted as a 'duplicate' and the lock stayed)."""
    d = carregar(login)
    a = next((x for x in d["acoes"] if x["id"] == aid), None)
    if not a or a["estado"] != "executada" or a["tipo"] not in ("dm_abertura", "dm_lembrete", "resposta", "parceiro"):
        return None
    _mudar(d, a, "apagada", detalhe, detalhe=(f"APAGADA: {detalhe} | antes: " + str(a.get("detalhe", "")))[:600])
    lead = _lead(d, a["lead_id"])
    if lead:
        lead["historico"].append({"em": agora(), "tipo": "apagada", "texto": f"{a['tipo']} {aid} apagada: {detalhe}"[:300]})
    salvar(login, d)
    return a


def _disse(lead: dict) -> str:
    """What the person said last (the note of the latest etapa:respondeu/lead/descartado), for the reviewer."""
    falas = [h for h in lead.get("historico", []) if str(h.get("tipo", "")).startswith("etapa:")]
    return (falas[-1]["texto"][:300] + f" (em {falas[-1].get('onde', 'direct')})") if falas else "(não registrado)"


def revisar_textos(d: dict, acoes: list) -> dict:
    """{id: {"aprovado": bool, "motivo": str}} from a fresh model against the playbook. Fails closed: when the
    reviewer is unreachable or unclear, nothing is approved here (it goes to the person)."""
    playbook = (Path(__file__).resolve().parents[1] / "playbook.md")
    blocos = []
    for a in acoes:
        lead = _lead(d, a["lead_id"]) or {}
        dados = {k: lead.get(k) for k in ("nome", "handle", "segmento", "cidade", "seguidores", "motivo", "sinal", "evidencias")}
        blocos.append(f"## Item {a['id']} — {a['tipo']}\nDADOS DO LEAD: {json.dumps(dados, ensure_ascii=False)}\n"
                      + (f"O QUE O AGENTE DIZ TER VISTO AGORA NO PERFIL: {a['base']}\n" if a.get("base") else "")
                      + (f"JÁ RECEBEU: {lead['historico'][-1]['texto'][:300]}\n" if lead.get("historico") and a["tipo"] != "resposta" else "")
                      + (f"O QUE A PESSOA DISSE: {_disse(lead)}\n" if a["tipo"] == "resposta" else "")
                      + f"TEXTO:\n«{a['texto']}»")
    pedido = (REVISOR + "\n\n# PLAYBOOK\n" + (playbook.read_text(encoding="utf-8")[:12000] if playbook.exists() else "")
              + "\n\n# ITENS\n" + "\n\n".join(blocos))
    try:
        saida = _chamar_revisor(pedido)
        achado = re.search(r"\{.*\}", saida or "", re.S)
        res = json.loads(achado.group(0), strict=False) if achado else {}
    except Exception as exc:
        return {a["id"]: {"aprovado": False, "motivo": f"revisor indisponível ({str(exc)[:80]})"} for a in acoes}
    vistos = {str(i.get("id")): i for i in (res.get("itens") or []) if isinstance(i, dict)}
    return {a["id"]: {"aprovado": vistos.get(a["id"], {}).get("aprovado") is True,
                      "motivo": str(vistos.get(a["id"], {}).get("motivo") or "revisor não respondeu sobre este item")[:200]}
            for a in acoes}


def _auto_aprovar(login: str, out: dict) -> dict:
    """Pre-approved types: follow/like with no text pass straight; any text passes the reviewer first. Whatever the
    reviewer does not pass stays a proposal for the person. out gains "automaticas"; "propostas" keeps only the manual."""
    d = carregar(login)
    candidatas = [a for a in out["propostas"] if a["tipo"] in AUTO_TIPOS]
    com_texto = [a for a in candidatas if a["texto"]]
    vereditos = revisar_textos(d, com_texto) if com_texto else {}
    # the reviewer claimed something is missing that a plain rule shows is there (11/10: it held a reply "for not
    # introducing Matheus nor linking the calculator" — the text did both): ask once more, pointing at the fact
    contraditos = [a for a in com_texto if not vereditos.get(a["id"], {}).get("aprovado") and _contradiz(a, vereditos[a["id"]]["motivo"])]
    if contraditos:
        for a in contraditos:
            a = {**a, "base": (a.get("base") or "") + f" | CONFERIDO POR REGRA, NÃO PELO MODELO: {_fatos(a)}. "
                 f"Uma revisão anterior disse: «{vereditos[a['id']]['motivo']}» — isso contradiz o texto; reveja só pelo resto."}
            segunda = revisar_textos(d, [a]).get(a["id"], {})
            vereditos[a["id"]] = {"aprovado": segunda.get("aprovado") is True,
                                  "motivo": f"2ª revisão: {segunda.get('motivo', '')} (a 1ª errou: {vereditos[a['id']]['motivo'][:80]})"[:200]}
    automaticas, manuais = [], [a for a in out["propostas"] if a["tipo"] not in AUTO_TIPOS]
    recusadas = list(out.get("recusadas", []))
    sem_aprovacao = d["config"].get("sem_aprovacao", True)
    for a in candidatas:
        v = vereditos.get(a["id"], {"aprovado": True, "motivo": "seguir e curtir, sem texto"})
        guardada = next(x for x in d["acoes"] if x["id"] == a["id"])
        guardada["revisao"] = v["motivo"]
        if v["aprovado"]:
            _mudar(d, guardada, "aprovada", f"revisor: {v['motivo']}", decidida=agora(), auto=True)
            automaticas.append(guardada)
        elif sem_aprovacao:
            _mudar(d, guardada, "pulada", f"revisor reprovou: {v['motivo']}", decidida=agora(), reprovada_revisor=True)
            versoes = _versoes_reprovadas(d, guardada["lead_id"], guardada["tipo"])
            restam = VERSOES_REVISOR - versoes
            recusadas.append({"lead_id": guardada["lead_id"], "tipo": guardada["tipo"], "motivo": (
                f"REESCREVA — o revisor reprovou: {v['motivo']}. Escreva outra versão que resolva isso e proponha de novo "
                f"({restam} versão(ões) restante(s) hoje)." if restam > 0 else
                f"o revisor reprovou {VERSOES_REVISOR} versões ({v['motivo']}): deixe este para amanhã")})
        else:
            manuais.append(guardada)
    salvar(login, d)
    return {**out, "propostas": manuais, "automaticas": automaticas, "recusadas": recusadas}


def _versoes_reprovadas(d: dict, lid: str, tipo: str) -> int:
    hoje = _hoje_local()
    return sum(1 for a in d["acoes"] if a["lead_id"] == lid and a["tipo"] == tipo and a.get("reprovada_revisor")
               and _hoje_local(a.get("decidida") or a["criada"]) == hoje)


def _fatos(a: dict) -> str:
    t = a.get("texto") or ""
    fatos = []
    if re.search(r"matheus", t, re.I):
        fatos.append("o texto apresenta/assina o Matheus")
    if CALCULADORA.search(t):
        fatos.append("o texto tem o link da calculadora/simulador")
    if re.search(r"sem cadastro|sem precisar (se )?cadastrar", t, re.I):
        fatos.append("o texto diz que dá para usar sem cadastro")
    return "; ".join(fatos) or "nada"


def _contradiz(a: dict, motivo: str) -> bool:
    """The reviewer's reason says something is missing that the text plainly has."""
    m, t = (motivo or "").lower(), a.get("texto") or ""
    falta = re.search(r"\b(n[aã]o|sem|falta|faltou|aus[eê]ncia)\b", m)
    return bool(falta and (("matheus" in m or "assinatura" in m or "apresent" in m) and re.search(r"matheus", t, re.I)
                           or ("link" in m or "calculadora" in m) and CALCULADORA.search(t)
                           or "cadastro" in m and re.search(r"sem cadastro", t, re.I)))


def definir_auto(login: str, ligado: bool) -> None:
    d = carregar(login)
    d["config"]["auto"] = bool(ligado)
    salvar(login, d)


def decidir(login: str, aid: str, decisao: str) -> dict | None:
    """The person's tap: aprovar | pular. Only pending proposals change."""
    d = carregar(login)
    a = next((x for x in d["acoes"] if x["id"] == aid), None)
    if not a or a["estado"] != "proposta":
        return None
    if agora() - a["criada"] > VALIDADE_PROPOSTA:
        _mudar(d, a, "expirada", "aprovação depois do prazo", decidida=agora())
    else:
        _mudar(d, a, "aprovada" if decisao == "aprovar" else "pulada", f"decisão: {decisao}", decidida=agora())
    salvar(login, d)
    return a


def aprovar_todas(login: str, ids: list) -> int:
    n = 0
    for aid in ids:
        a = decidir(login, aid, "aprovar")
        n += bool(a and a["estado"] == "aprovada")
    return n


def editar(login: str, aid: str, texto: str) -> tuple[dict | None, str]:
    """New text for a proposal or approved action: it goes back to the person for approval."""
    d = carregar(login)
    a = next((x for x in d["acoes"] if x["id"] == aid), None)
    if not a or a["estado"] not in ("proposta", "aprovada"):
        return None, "ação não encontrada ou já decidida"
    motivo = validar_texto(a["tipo"], texto, d, a["lead_id"])
    if motivo:
        return None, motivo
    _mudar(d, a, "proposta", "texto editado", texto=texto.strip()[:900], criada=agora())
    a.pop("decidida", None)
    salvar(login, d)
    return a, ""


def conta(login: str) -> str:
    return normalizar(carregar(login)["config"].get("conta_instagram") or "")


def definir_conta(login: str, handle: str) -> str:
    h = normalizar(handle)
    if not h or h in CONTAS_PROIBIDAS:
        return "conta inválida para prospecção"
    d = carregar(login)
    d["config"]["conta_instagram"] = h
    salvar(login, d)
    return ""


CONFERENCIA_VALE = 40 * 60  # an execution round must have read the Direct and the notifications this recently


def conferido(login: str, direct: str, notificacoes: str, interagiram: list | None = None) -> str:
    """The round says what it read in the Direct and in the notifications (answers are looked for before acting).
    '' when recorded, else why not: the notifications text must be what is on the page, not a one-word claim."""
    direct, notificacoes = (direct or "").strip(), (notificacoes or "").strip()
    if len(direct) < 8 or len(notificacoes) < 25:
        return ("leia de verdade: em `direct`, quantas conversas têm mensagem nova e de quem; em `notificacoes`, copie "
                "as primeiras linhas que aparecem na página de notificações")
    d = carregar(login)
    d["conferencia"] = {"em": agora(), "direct": direct[:500], "notificacoes": notificacoes[:800]}
    for h in interagiram or []:  # followed back / liked / commented: warmer, goes first for the next message
        lead = next((l for l in d["leads"] if l["handle"] == normalizar(str(h))), None)
        if lead and not lead.get("interagiu"):
            lead["interagiu"] = agora()
            lead["historico"].append({"em": agora(), "tipo": "interagiu", "texto": "seguiu de volta / curtiu / comentou"})
    salvar(login, d)
    return ""


def proxima(login: str, conta_ativa: str = "", repor: bool = True) -> tuple[dict | None, str]:
    """Next approved action that may run now (right account, hours, pause, spacing, daily limits)."""
    d = carregar(login)
    esperada, ativa = conta(login), normalizar(conta_ativa)
    if not esperada:
        return None, "a conta de Instagram da prospecção não está configurada: nada é executado"
    if ativa in CONTAS_PROIBIDAS:
        return None, f"a conta ativa é @{ativa} (pessoal): troque para @{esperada} pelo seletor de contas e chame de novo"
    if ativa != esperada:
        return None, (f"confirme a conta ATIVA no Instagram (o @ que aparece no menu do perfil) e chame `proxima` com "
                      f"conta_ativa; tem que ser @{esperada}")
    if d["config"].get("exigir_conferencia") and agora() - (d.get("conferencia") or {}).get("em", 0) > CONFERENCIA_VALE:
        return None, ("antes de executar, confira as respostas: leia o Direct e a página de notificações e chame "
                      "`prospeccao` acao \"conferido\" com o que viu em cada um")
    if modo_teste(login) and not d["config"].get("executar_em_teste"):
        return None, "modo teste: nada é executado"
    if agora() < d["bloqueio_ate"]:
        return None, "pausado após bloqueio do Instagram até " + dt.datetime.fromtimestamp(d["bloqueio_ate"], _tz()).strftime("%d/%m %H:%M")
    h = _hora_local()
    if not HORARIO[0] <= h < HORARIO[1]:
        return None, f"fora do horário ({HORARIO[0]}h–{HORARIO[1]}h)"
    if repor and not any(x["estado"] == "aprovada" for x in d["acoes"]) and not _fila_repor(login):
        # nothing to do at all: say so now, not "wait for the spacing" (11/10 17h20: the round waited on nothing)
        return None, "nenhuma ação aprovada esperando"
    ultima = _ultima_acao(d)  # a catch-up comment also counts for the spacing
    if agora() - ultima < INTERVALO:
        return None, f"espaçamento: próxima a partir de {dt.datetime.fromtimestamp(ultima + INTERVALO, _tz()).strftime('%H:%M')}"
    # replies go first (someone is waiting), then the rest in approval order
    for a in sorted((x for x in d["acoes"] if x["estado"] == "aprovada"), key=lambda x: (x["tipo"] != "resposta", x.get("decidida", 0))):
        lead = _lead(d, a["lead_id"])
        if not lead or (lead["etapa"] in FINAIS and not (a["tipo"] == "resposta" and lead["etapa"] == "descartado")):
            _mudar(d, a, "cancelada", "lead encerrado antes da execução")
            continue
        executadas_hoje = sum(1 for x in d["acoes"] if x["tipo"] == a["tipo"] and x["estado"] == "executada"
                              and _hoje_local(x.get("executada_em")) == _hoje_local())
        if executadas_hoje >= limites(d)[a["tipo"]]:
            continue
        a["em_execucao"] = agora()
        salvar(login, d)
        return {**a, "lead": lead}, ""
    salvar(login, d)
    if repor and repor_aquecer(login):
        return proxima(login, conta_ativa, repor=False)
    return None, "nenhuma ação aprovada esperando"


# ------------------------------------------------------------------ comment written during the visit
# 11/10: warm-ups from the sources and the automatic refill go with no text (nobody had seen the posts), so the 8
# warm-ups of the day had no comment. Now, on the visit, the agent reads the latest post and may write one; the
# reviewer checks it; only an approved comment is published. Also for warm-ups done in the last days (catch-up).
DIAS_COMENTARIO = 3
TENTATIVAS_COMENTARIO = 4  # the reviewer said no: rewrite with its reason and try again, up to this many (Matheus, 11/10)


def comentar(login: str, aid: str, texto: str, base: str = "") -> tuple[bool, str]:
    """(approved, why). Comment for an «aquecer» that is being executed now, or was executed in the last days
    without one. Never two comments per warm-up; same rules as the warm-up text plus the reviewer."""
    d = carregar(login)
    a = next((x for x in d["acoes"] if x["id"] == aid), None)
    if not a or a["tipo"] != "aquecer":
        return False, "ação de aquecer não encontrada"
    if a.get("texto") or (a.get("comentario") or {}).get("estado") in ("aprovado", "publicado"):
        return False, "esse aquecimento já tem comentário"
    em_visita = a["estado"] == "aprovada" and a.get("em_execucao")
    recente = a["estado"] == "executada" and _dias_desde(a.get("executada_em") or 0) <= DIAS_COMENTARIO
    if not (em_visita or recente):
        return False, "só durante a visita do aquecimento ou até 3 dias depois dele"
    lead = _lead(d, a["lead_id"])
    if not lead or lead["etapa"] in FINAIS:
        return False, "lead encerrado: não comente"
    t = (texto or "").strip()
    motivo = validar_texto("aquecer", t, d, a["lead_id"]) or ("" if len(t) >= 15 else "comentário vazio ou curto demais")
    if not motivo and not em_visita:  # catch-up comments follow the same pace as any action
        h = _hora_local()
        ultima = _ultima_acao(d)
        if not HORARIO[0] <= h < HORARIO[1]:
            motivo = f"fora do horário ({HORARIO[0]}h–{HORARIO[1]}h)"
        elif agora() - ultima < INTERVALO:
            motivo = "espaçamento: próxima a partir de " + dt.datetime.fromtimestamp(ultima + INTERVALO, _tz()).strftime("%H:%M")
    if motivo:
        return False, motivo
    tentativas = (a.get("comentario") or {}).get("tentativas", 0)
    if tentativas >= TENTATIVAS_COMENTARIO:
        return False, f"{TENTATIVAS_COMENTARIO} versões reprovadas pelo revisor: siga sem comentário neste perfil"
    v = revisar_textos(d, [{"id": a["id"], "lead_id": a["lead_id"], "tipo": "aquecer", "texto": t, "base": base}])[a["id"]]
    a["comentario"] = {"texto": t, "base": str(base)[:300], "revisao": v["motivo"], "em": agora(),
                       "estado": "aprovado" if v["aprovado"] else "recusado", "tentativas": tentativas + 1}
    if not v["aprovado"]:
        restam = TENTATIVAS_COMENTARIO - tentativas - 1
        v = {**v, "motivo": (f"REESCREVA — o revisor reprovou: {v['motivo']}. Escreva outra versão que resolva isso e chame "
                             f"\"comentar\" de novo ({restam} tentativa(s) restante(s))." if restam else
                             f"o revisor reprovou a última versão permitida ({v['motivo']}): siga sem comentário")}
    _evento(d, a, a["estado"], a["estado"], f"comentário {a['comentario']['estado']}: {v['motivo']}")
    salvar(login, d)
    return v["aprovado"], v["motivo"]


def comentado(login: str, aid: str, ok: bool, detalhe: str = "") -> dict | None:
    """The approved comment was (or was not) published."""
    d = carregar(login)
    a = next((x for x in d["acoes"] if x["id"] == aid), None)
    if not a or (a.get("comentario") or {}).get("estado") != "aprovado":
        return None
    a["comentario"].update({"estado": "publicado" if ok else "falhou", "detalhe": str(detalhe)[:300], "feito_em": agora()})
    if ok:
        a["comentado_em"] = agora()
        lead = _lead(d, a["lead_id"])
        if lead:
            lead["historico"].append({"em": agora(), "tipo": "comentario", "texto": a["comentario"]["texto"][:300]})
    _evento(d, a, a["estado"], a["estado"], f"comentário {'publicado' if ok else 'não saiu'}: {detalhe}")
    salvar(login, d)
    return a


def sem_comentario(login: str) -> list[dict]:
    """Warm-ups of the last days with no comment, newest first (catch-up list)."""
    d = carregar(login)
    out = []
    for a in d["acoes"]:
        lead = _lead(d, a["lead_id"]) or {}
        if (a["tipo"] == "aquecer" and a["estado"] == "executada" and not a.get("texto")
                and not (a.get("comentario") or {}).get("estado") in ("aprovado", "publicado")
                and _dias_desde(a.get("executada_em") or 0) <= DIAS_COMENTARIO and lead.get("etapa") not in FINAIS):
            out.append({"acao_id": a["id"], "handle": lead.get("handle"), "url": lead.get("url"), "executada_em": a["executada_em"]})
    return sorted(out, key=lambda x: -x["executada_em"])


def _ultima_acao(d: dict) -> float:
    return max([a.get("executada_em", 0) for a in d["acoes"]] + [a.get("comentado_em", 0) for a in d["acoes"]] + [0])


TIPOS_DIRECT = ("dm_abertura", "dm_lembrete", "resposta", "parceiro")


def script_digitar(texto: str) -> str:
    """Script for `browser` evaluate on the open Direct conversation, run AFTER clearing the box with the keyboard
    (click the box, Control+A, Backspace). Instagram's box (a Lexical editor) keeps the draft of an earlier attempt
    (11/10: Zen and Anna got the text twice in one bubble), ignores a scripted delete and shows typed text only a moment
    later (12/10: the first version checked at once, saw it empty and said DIFERENTE). So: refuse a box that is not
    empty, insert the text once, then wait until the box shows exactly that text. Idempotent: a box already holding
    exactly the text answers OK without inserting again."""
    return ("(async () => { const t = " + json.dumps(texto, ensure_ascii=False) + "; "
            "const norm = s => (s || '').replace(/\\s+/g, ' ').trim(); "
            "const espera = ms => new Promise(r => setTimeout(r, ms)); "
            "const caixas = [...document.querySelectorAll('div[role=\"textbox\"][contenteditable=\"true\"]')]; "
            "const box = caixas[caixas.length - 1]; if (!box) return 'SEM CAMPO DE MENSAGEM'; "
            "box.focus(); await espera(300); "
            "if (norm(box.innerText)) { if (norm(box.innerText) === norm(t)) return 'OK'; "
            "return 'CAMPO NÃO ESTÁ VAZIO: clique no campo, aperte Control+A e depois Backspace (ações press do browser) e rode de novo. Agora tem: ' + norm(box.innerText).slice(0, 120); } "
            "document.execCommand('insertText', false, t); "
            "for (let i = 0; i < 20; i++) { await espera(150); if (norm(box.innerText) === norm(t)) return 'OK'; } "
            "return 'DIFERENTE: ' + norm(box.innerText).slice(0, 300); })()")


def aviso_sem_acao(motivo: str) -> str:
    """What the agent is told when `proxima` has nothing right now. Spacing is a wait, not the end of the round
    (11/10: "NADA AGORA: espaçamento…" ended the 14h50 round after 1 of 5 free slots)."""
    if "confira as respostas" in motivo:
        return f"AINDA NÃO: {motivo}."
    if motivo.startswith("espaçamento"):
        return (f"ESPERE: {motivo}. Aguarde até esse horário (ex.: code_execution_tool com `sleep 180`) e chame "
                "`proxima` de novo. A rodada só termina com NADA AGORA ou depois de 3 ações feitas.")
    return f"NADA AGORA: {motivo}. Termine a rodada."


def resultado(login: str, aid: str, ok: bool, detalhe: str = "", bloqueio: bool = False) -> dict | None:
    d = carregar(login)
    a = next((x for x in d["acoes"] if x["id"] == aid), None)
    if not a or a["estado"] != "aprovada":
        return None
    _mudar(d, a, "executada" if ok else "falhou", detalhe, executada_em=agora(), detalhe=detalhe[:300])
    lead = _lead(d, a["lead_id"])
    if ok and lead:
        proxima_etapa = {"aquecer": "aquecido", "dm_abertura": "abordado", "dm_lembrete": "lembrado"}.get(a["tipo"])
        if proxima_etapa:
            lead["etapa"] = proxima_etapa
        if a["tipo"] == "dm_abertura":
            lead["variante"] = a["variante"]
        lead["atualizado"] = agora()
        lead["historico"].append({"em": agora(), "tipo": a["tipo"], "texto": a["texto"][:300]})
    if bloqueio:
        d["bloqueio_ate"] = agora() + BLOQUEIO
    salvar(login, d)
    return a


def expirar(login: str) -> int:
    d = carregar(login)
    n = 0
    for a in d["acoes"]:
        if a["estado"] == "proposta" and agora() - a["criada"] > VALIDADE_PROPOSTA:
            _mudar(d, a, "expirada", "proposta sem decisão no prazo")
            n += 1
    if n:
        salvar(login, d)
    return n


# ------------------------------------------------------------------ approvals reviewer window

def liberar(contexto, acao: dict) -> None:
    """Let the approvals reviewer pass the third-party step of THIS approved action for a few minutes."""
    contexto.set_data("_aprovacoes_liberadas", {"categorias": ["mensagem_terceiros", "publicar"], "ate": agora() + LIBERACAO,
                                                "motivo": f"prospecção: ação {acao['id']} ({acao['tipo']}) " +
                                                ("pré-aprovada pelo usuário (dentro dos limites do dia, texto revisado)"
                                                 if acao.get("auto") else "aprovada pelo usuário")})


def encerrar_liberacao(contexto) -> None:
    contexto.set_data("_aprovacoes_liberadas", None)


# ------------------------------------------------------------------ phone

ROTULO = {"aquecer": "🔥 Aquecer", "dm_abertura": "💬 Primeira mensagem", "dm_lembrete": "🔁 Lembrete",
          "resposta": "↩️ Resposta", "parceiro": "🤝 Parceiro"}


def mensagem_acao(a: dict, lead: dict) -> str:
    linhas = [f"{ROTULO[a['tipo']]}{' (' + a['variante'] + ')' if a.get('variante') else ''} — *{lead['nome']}* (@{lead['handle']})",
              f"_{lead['segmento']} · {lead['cidade']}{' · ' + lead['seguidores'] + ' seguidores' if lead.get('seguidores') else ''}_",
              f"Por quê: {lead['motivo']}"]
    if a["tipo"] == "aquecer":
        linhas.append("Vou: seguir e curtir 1–2 posts recentes" + (f"; comentar:\n«{a['texto']}»" if a["texto"] else "."))
    else:
        linhas += ["", a["texto"]]
    linhas.append(lead["url"])
    return "\n".join(linhas)


def botoes_acao(login: str, aid: str) -> list:
    base = f"pa:{_login(login)}:{aid}"
    return [{"id": f"{base}:aprovar", "titulo": "✅ Aprovar"}, {"id": f"{base}:editar", "titulo": "✏️ Editar"},
            {"id": f"{base}:pular", "titulo": "❌ Pular"}]


def pendentes(login: str) -> list:
    """Proposals still waiting for the person (to resend them when test mode is turned off)."""
    d = carregar(login)
    return [(a, _lead(d, a["lead_id"])) for a in d["acoes"] if a["estado"] == "proposta"]


def guardar_pacote(login: str, ids: list) -> str:
    d = carregar(login)
    pid = _id()
    d.setdefault("pacotes", {})[pid] = {"ids": ids, "em": agora()}
    d["pacotes"] = dict(list(d["pacotes"].items())[-30:])
    salvar(login, d)
    return pid


def ids_do_pacote(login: str, pid: str) -> list:
    return (carregar(login).get("pacotes") or {}).get(pid, {}).get("ids", [])


def enviar(login: str, texto: str, botoes: list | None = None, tipo: str = "progresso", ponte=None) -> str:
    """Phone message; in test mode it is recorded instead (no third party is ever involved here — it is the owner's
    phone — but tests must not buzz it)."""
    if modo_teste(login):
        CAIXA_TESTES.parent.mkdir(parents=True, exist_ok=True)
        with CAIXA_TESTES.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"em": agora(), "usuario": _login(login), "texto": texto, "botoes": botoes or [],
                                "tipo": tipo, "origem": "prospeccao"}, ensure_ascii=False) + "\n")
        return ""
    return ponte.enviar(login, texto, botoes=botoes, tipo=tipo) if ponte else "ponte indisponível"


# ------------------------------------------------------------------ numbers

def metricas(login: str, dias: int = 7) -> dict:
    d = carregar(login)
    corte = agora() - dias * 86400
    acoes = [a for a in d["acoes"] if a["criada"] >= corte]
    por_estado: dict = {}
    for a in acoes:
        por_estado.setdefault(a["tipo"], {}).setdefault(a["estado"], 0)
        por_estado[a["tipo"]][a["estado"]] += 1
    abordados = [l for l in d["leads"] if any(h["tipo"] == "dm_abertura" and h["em"] >= corte for h in l["historico"])]
    responderam = {"respondeu", "lead", "demo", "teste", "cliente"}
    viraram_lead = {"lead", "demo", "teste", "cliente"}

    def taxa(grupo):
        n = len(grupo)
        r = sum(1 for l in grupo if l["etapa"] in responderam or any(h["tipo"] == "etapa:respondeu" for h in l["historico"]))
        ld = sum(1 for l in grupo if l["etapa"] in viraram_lead)
        return {"abordados": n, "responderam": r, "leads": ld,
                "taxa_resposta": round(100 * r / n, 1) if n else 0.0, "taxa_lead": round(100 * ld / n, 1) if n else 0.0}

    def por(campo):
        grupos: dict = {}
        for l in abordados:
            grupos.setdefault(str(l.get(campo) or "?"), []).append(l)
        return {k: taxa(v) for k, v in grupos.items()}

    etapas: dict = {}
    for l in d["leads"]:
        etapas[l["etapa"]] = etapas.get(l["etapa"], 0) + 1
    aprovadas = sum(1 for a in acoes if a["estado"] in ("aprovada", "executada", "falhou"))
    decididas = sum(1 for a in acoes if a["estado"] in ("aprovada", "executada", "falhou", "pulada"))
    return {"dias": dias, "acoes": por_estado, "etapas": etapas, "geral": taxa(abordados),
            "por_variante": por("variante"), "por_segmento": por("segmento"), "por_cidade": por("cidade"),
            "por_faixa": por("faixa"),
            "taxa_aprovacao": round(100 * aprovadas / decididas, 1) if decididas else 0.0,
            "falhas": [a.get("detalhe", "") for a in acoes if a["estado"] == "falhou"][-5:],
            "pausado": agora() < d["bloqueio_ate"]}


def resumo_hoje(login: str) -> str:
    """End-of-day report for the phone: only what matters (answers first), short. '' when the day had nothing."""
    d = carregar(login)
    hoje = _hoje_local()
    de_hoje = lambda ts: bool(ts) and _hoje_local(ts) == hoje  # noqa: E731
    leads = {l["id"]: l for l in d["leads"]}
    respostas = [l for l in d["leads"] if any(h["tipo"] in ("etapa:respondeu", "etapa:lead", "etapa:demo") and de_hoje(h["em"])
                                              for h in l["historico"])]
    feitas = [a for a in d["acoes"] if a["estado"] == "executada" and de_hoje(a.get("executada_em"))]
    falhas = [a for a in d["acoes"] if a["estado"] == "falhou" and de_hoje(a.get("executada_em"))]
    novos = [l for l in d["leads"] if de_hoje(l["criado"])]
    rejeitados = sum(1 for v in (d.get("rejeitados") or {}).values() if de_hoje(v["em"]))
    esperando = [a for a in d["acoes"] if a["estado"] == "proposta"]
    if not (respostas or feitas or falhas or novos or esperando):
        return ""
    linhas = [f"🎯 *Prospecção Raiz — {dt.datetime.fromtimestamp(agora(), _tz()).strftime('%d/%m')}*"]
    if respostas:
        linhas.append("\n💬 *Responderam* — olhe primeiro")
        for l in respostas:
            h = next(x for x in reversed(l["historico"]) if x["tipo"].startswith("etapa:") and de_hoje(x["em"]))
            onde = "no comentário" if h.get("onde") == "comentario" else "no Direct"
            linhas.append(f"• {l['nome'][:40]} (@{l['handle']}) — {onde}: «{(h.get('texto') or '')[:160]}» ({l['etapa']})")
    if feitas:  # everything that went out today, one line per profile
        n = {t: sum(1 for a in feitas if a["tipo"] == t) for t in TIPOS}
        nomes = {"aquecer": "aquecidos", "dm_abertura": "primeiras mensagens", "dm_lembrete": "lembretes",
                 "resposta": "respostas", "parceiro": "parceiros"}
        linhas.append("\n✅ *Feito hoje:* " + ", ".join(f"{n[t]} {nomes[t]}" for t in TIPOS if n[t]))
        for a in sorted(feitas, key=lambda x: x["executada_em"]):
            l = leads.get(a["lead_id"]) or {}
            if a["tipo"] == "aquecer":
                c = a.get("comentario") or {}
                texto_c = a["texto"] or (c.get("texto") if c.get("estado") == "publicado" else "")
                comentou = texto_c and "não saiu" not in (a.get("detalhe") or "") and "não foi publicado" not in (a.get("detalhe") or "")
                o_que = "seguiu e curtiu" + (f"; comentou «{texto_c[:90]}{'…' if len(texto_c) > 90 else ''}»" if comentou else
                                             " (o comentário não saiu)" if a["texto"] else "")
            else:
                o_que = f"{nomes[a['tipo']][:-1] if a['tipo'] != 'dm_abertura' else 'primeira mensagem'}: «{a['texto'][:120]}{'…' if len(a['texto']) > 120 else ''}»"
            linhas.append(f"• @{l.get('handle')} — {o_que}")
    comentados = [a for a in d["acoes"] if a not in feitas and (a.get("comentario") or {}).get("estado") == "publicado"
                  and de_hoje(a["comentario"].get("feito_em"))]
    if comentados:  # comments written today on warm-ups of earlier days
        linhas.append(f"\n💬 *Comentários em perfis já aquecidos:* {len(comentados)}")
        linhas += [f"• @{(leads.get(a['lead_id']) or {}).get('handle')} — «{a['comentario']['texto'][:90]}»" for a in comentados]
    e = estoque(login)
    if novos or rejeitados or e["faltam"]:
        linhas.append(f"\n🔎 *Leads:* {len(novos)} entraram hoje · estoque {e['prontos']}/{e['alvo']} prontos para aquecer"
                      f" · {rejeitados} descartados hoje")
        novos.sort(key=lambda l: -(l.get("nota") or 0))
        if novos:
            linhas.append("Melhores de hoje: " + ", ".join(f"@{l['handle']} ({l['nota']})" for l in novos[:3] if l.get("nota") is not None))
    if falhas:
        vistos, itens = set(), []
        for a in falhas:  # one line per profile: who, what, and the first sentence of why
            if a["lead_id"] in vistos:
                continue
            vistos.add(a["lead_id"])
            motivo = re.split(r"(?<=[.;])\s", (a.get("detalhe") or "sem detalhe").strip())[0][:110]
            itens.append(f"• @{(leads.get(a['lead_id']) or {}).get('handle')} ({ROTULO.get(a['tipo'], a['tipo'])}) — {motivo}")
        linhas.append("\n⚠️ *Não saíram:*\n" + "\n".join(itens[:5]))
    if esperando:
        linhas.append(f"\n✋ {len(esperando)} esperando o seu ✅ (o revisor não liberou sozinho)")
    if agora() < d["bloqueio_ate"]:
        linhas.append("\n⛔ Pausado até " + dt.datetime.fromtimestamp(d["bloqueio_ate"], _tz()).strftime("%d/%m %H:%M"))
    return "\n".join(linhas)


def resumo_contexto(login: str) -> str:
    """What a search round needs: limits left, leads due a next step, handles already known, pause state."""
    expirar(login)
    fechar_vencidos(login)
    d = carregar(login)
    c = cotas(login)
    dev = devidos(login)
    e = estoque(login)
    linhas = [f"# Prospecção — {dt.datetime.now(_tz()).strftime('%a %d/%m %H:%M')} ({FUSO})",
              "Cotas que ainda cabem hoje (propostas aprovadas contam): " + ", ".join(f"{k} {v}" for k, v in c.items()),
              f"Estoque de leads prontos para aquecer: {e['prontos']} de {e['alvo']}" +
              (f" — FALTAM {e['faltam']}: reponha com `fontes` (e a busca no Instagram se as fontes secarem)." if e["faltam"] else " (cheio).")]
    if agora() < d["bloqueio_ate"]:
        linhas.append("⛔ PAUSADO após bloqueio do Instagram — não proponha nada até " +
                      dt.datetime.fromtimestamp(d["bloqueio_ate"], _tz()).strftime("%d/%m %H:%M"))
    for tipo, lista in dev.items():
        if lista:
            linhas.append(f"\n## Devem receber «{tipo}» agora ({len(lista)})")
            linhas += [f"- [{l['id']}] @{l['handle']} — {l['nome']} ({l['segmento']}, {l['cidade']}; nota {l.get('nota', '—')}); motivo: {l['motivo'][:120]}"
                       + (f"; já recebeu: {l['historico'][-1]['texto'][:160]}" if l["historico"] else "") for l in lista[:25]]
    conversas = [l for l in d["leads"] if l["etapa"] in ("abordado", "lembrado", "respondeu", "lead", "demo")]
    if conversas:
        linhas.append(f"\n## Conversas no Direct para conferir ({len(conversas)}) — abra cada uma (perfil → Mensagem)")
        linhas += [f"- [{l['id']}] @{l['handle']} ({l['etapa']}); última nossa: {l['historico'][-1]['texto'][:80] if l['historico'] else ''}"
                   for l in conversas[:20]]
    conhecidos = sorted(l["handle"] for l in d["leads"])
    linhas.append(f"\n## Já conhecidos ({len(conhecidos)}) — não registre de novo\n" + (", ".join(conhecidos[-400:]) or "(nenhum)"))
    rej = d.get("rejeitados") or {}
    if rej:
        linhas.append(f"\n## Já examinados e rejeitados ({len(rej)}) — não abra de novo\n" + ", ".join(sorted(rej)[-400:]))
    m = metricas(login, 14)
    linhas.append(f"\n## Como está indo (14 dias)\n{json.dumps(m['geral'], ensure_ascii=False)}; por variante: "
                  f"{json.dumps(m['por_variante'], ensure_ascii=False)}; aprovação das propostas: {m['taxa_aprovacao']}%")
    return "\n".join(linhas)

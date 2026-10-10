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
ESPERA_DM = 2 * 86400              # after warming up, before the first DM
ESPERA_LEMBRETE = 3 * 86400        # after the first DM, before the reminder
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


def salvar(login: str, d: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
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
    return next((l for l in d["leads"] if l["id"] == lid), None)


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
    except ValueError:
        return {"rejeitado": "sem a data do último post NÃO fixado (ultimo_post AAAA-MM-DD)"}
    dias = (dt.datetime.fromtimestamp(agora(), _tz()).date() - ultimo).days
    if dias > 30:
        return {"rejeitado": f"parado há {dias} dias"}
    seguidores = _numero(item.get("seguidores"))
    if seguidores < 300:
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
        "atividade": 15 if dias <= 7 else 12 if dias <= 14 else 8,
        "porte": 15 if 500 <= seguidores <= 5000 else 12 if seguidores <= 20_000 and seguidores > 5000 else 8 if seguidores > 20_000 else 6,
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
        d["leads"].append(lead)
        por_handle[handle] = lead
        out["criados"].append({"handle": handle, "id": lead["id"], "nota": lead["nota"],
                               "faixa": lead["avaliacao"].get("faixa")})
    salvar(login, d)
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


def mudar_etapa(login: str, lid: str, etapa: str, nota: str = "", onde: str = "direct") -> dict | None:
    """New stage. The returned lead carries "novidade": False when the same answer was already recorded (rounds
    re-read the same Direct/notifications every half hour; the person must hear about each answer once)."""
    d = carregar(login)
    lead = _lead(d, lid)
    if not lead or etapa not in ETAPAS:
        return None
    onde = onde if onde in ONDE else "direct"
    nota = nota[:300]
    repetida = any(h["tipo"] == f"etapa:{etapa}" and h.get("texto") == nota and h.get("onde", "direct") == onde
                   for h in lead["historico"])
    if repetida and lead["etapa"] == etapa:
        return {**lead, "novidade": False}
    lead["etapa"], lead["atualizado"] = etapa, agora()
    lead["historico"].append({"em": agora(), "tipo": f"etapa:{etapa}", "texto": nota, "onde": onde})
    if etapa in FINAIS or etapa in ("respondeu", "lead"):  # pending outreach stops when they answer or are closed
        for a in d["acoes"]:
            if a["lead_id"] == lid and a["estado"] in ("proposta", "aprovada") and a["tipo"] != "resposta":
                a["estado"], a["decidida"] = "cancelada", agora()
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


def devidos(login: str) -> dict:
    """What each lead needs next, by the playbook's timing."""
    d = carregar(login)
    pendentes = {a["lead_id"] for a in d["acoes"] if a["estado"] in ("proposta", "aprovada")}
    out = {"dm_abertura": [], "dm_lembrete": [], "aquecer": []}
    for l in d["leads"]:
        if l["id"] in pendentes or l["canal"] != "instagram":
            continue
        espera = agora() - l["atualizado"]
        if l["etapa"] == "novo":
            out["aquecer"].append(l)
        elif l["etapa"] == "aquecido" and espera >= ESPERA_DM:
            out["dm_abertura"].append(l)
        elif l["etapa"] == "abordado" and espera >= ESPERA_LEMBRETE:
            out["dm_lembrete"].append(l)
    for lista in out.values():  # best fit first: the day's slots are limited
        lista.sort(key=lambda l: -(l.get("nota") if l.get("nota") is not None else 60))
    return out


# ------------------------------------------------------------------ actions

LIMITE_PILOTO = {"aquecer": 8, "dm_abertura": 5, "dm_lembrete": 5, "resposta": 15, "parceiro": 3}


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
    if tipo in ("dm_abertura", "dm_lembrete", "parceiro") and LINK.search(t):
        return "sem link nas mensagens de abordagem"
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
        elif tipo == "dm_abertura" and lead["etapa"] != "aquecido":
            motivo = "DM de abertura só depois do aquecimento"
        elif tipo == "dm_lembrete" and lead["etapa"] != "abordado":
            motivo = "lembrete só para quem recebeu a abertura e não respondeu"
        elif tipo == "dm_lembrete" and agora() - lead["atualizado"] < ESPERA_LEMBRETE:
            motivo = "cedo demais para o lembrete"
        elif tipo == "resposta" and lead["etapa"] not in ("respondeu", "lead", "demo", "teste", "descartado"):
            motivo = "resposta só para quem escreveu"
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
        ja.add((lid, tipo))
        restantes[tipo] -= 1
        out["propostas"].append(acao)
    salvar(login, d)
    if d["config"].get("auto"):
        out = _auto_aprovar(login, out)
    return out


# ------------------------------------------------------------------ pre-approved within the daily limits

AUTO_TIPOS = ("aquecer", "dm_abertura", "dm_lembrete")  # replies and partner messages still go to the person
PROXY = "http://host.docker.internal:8787"
MODELO_REVISOR = "openai.gpt-6-luna"
revisor = None  # tests replace it: fn(pedido: str) -> str

REVISOR = """Você é o revisor independente das mensagens de prospecção da Raiz Connect. O dono autorizou que elas saiam
SEM perguntar a ele, então você é a última barreira antes de uma pessoa real recebê-las. Reprove um item SÓ se:
1. Afirma um fato sobre o negócio (prato, unidade, novidade, número, cidade) que NÃO está nos DADOS DO LEAD nem no que
   o agente diz ter visto. Pergunta não é afirmação ("ele entra no kit?" é aceitável); elogio a algo que está nos
   dados também é.
2. Fere o playbook: comentário de aquecimento que vende, cita a Raiz, um sistema ou chama para o direct; jargão
   (ERP, sistema de gestão, CMV, solução) na abertura; promessa de resultado ou número inventado; pressão; link;
   primeira mensagem sem a oferta do cálculo grátis ou sem a assinatura do Matheus.
3. Soa como spam, intimidade forçada ou constrange a pessoa.
4. Tem erro de português ou abreviação de internet que faça a marca parecer descuidada.
Os modelos do playbook são guia, não texto fixo: variações naturais são boas (falar de entrega, embalagem ou iFood ao
explicar o cálculo; outra forma de pedir a receita e o preço; outro elogio verdadeiro). Não reprove por estilo.
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
                      + (f"JÁ RECEBEU: {lead['historico'][-1]['texto'][:300]}\n" if lead.get("historico") else "")
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
    automaticas, manuais = [], [a for a in out["propostas"] if a["tipo"] not in AUTO_TIPOS]
    for a in candidatas:
        v = vereditos.get(a["id"], {"aprovado": True, "motivo": "seguir e curtir, sem texto"})
        guardada = next(x for x in d["acoes"] if x["id"] == a["id"])
        guardada["revisao"] = v["motivo"]
        if v["aprovado"]:
            guardada.update({"estado": "aprovada", "decidida": agora(), "auto": True})
            automaticas.append(guardada)
        else:
            manuais.append(guardada)
    salvar(login, d)
    return {**out, "propostas": manuais, "automaticas": automaticas}


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
        a["estado"] = "expirada"
    else:
        a["estado"] = "aprovada" if decisao == "aprovar" else "pulada"
    a["decidida"] = agora()
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
    a.update({"texto": texto.strip()[:900], "estado": "proposta", "criada": agora()})
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


def conferido(login: str, direct: str, notificacoes: str) -> str:
    """The round says what it read in the Direct and in the notifications (answers are looked for before acting).
    '' when recorded, else why not: the notifications text must be what is on the page, not a one-word claim."""
    direct, notificacoes = (direct or "").strip(), (notificacoes or "").strip()
    if len(direct) < 8 or len(notificacoes) < 25:
        return ("leia de verdade: em `direct`, quantas conversas têm mensagem nova e de quem; em `notificacoes`, copie "
                "as primeiras linhas que aparecem na página de notificações")
    d = carregar(login)
    d["conferencia"] = {"em": agora(), "direct": direct[:500], "notificacoes": notificacoes[:800]}
    salvar(login, d)
    return ""


def proxima(login: str, conta_ativa: str = "") -> tuple[dict | None, str]:
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
    ultima = max([a.get("executada_em", 0) for a in d["acoes"]] + [0])
    if agora() - ultima < INTERVALO:
        return None, f"espaçamento: próxima a partir de {dt.datetime.fromtimestamp(ultima + INTERVALO, _tz()).strftime('%H:%M')}"
    for a in sorted((x for x in d["acoes"] if x["estado"] == "aprovada"), key=lambda x: x.get("decidida", 0)):
        lead = _lead(d, a["lead_id"])
        if not lead or (lead["etapa"] in FINAIS and not (a["tipo"] == "resposta" and lead["etapa"] == "descartado")):
            a["estado"] = "cancelada"
            continue
        executadas_hoje = sum(1 for x in d["acoes"] if x["tipo"] == a["tipo"] and x["estado"] == "executada"
                              and _hoje_local(x.get("executada_em")) == _hoje_local())
        if executadas_hoje >= limites(d)[a["tipo"]]:
            continue
        a["em_execucao"] = agora()
        salvar(login, d)
        return {**a, "lead": lead}, ""
    salvar(login, d)
    return None, "nenhuma ação aprovada esperando"


def resultado(login: str, aid: str, ok: bool, detalhe: str = "", bloqueio: bool = False) -> dict | None:
    d = carregar(login)
    a = next((x for x in d["acoes"] if x["id"] == aid), None)
    if not a or a["estado"] != "aprovada":
        return None
    a["estado"] = "executada" if ok else "falhou"
    a["executada_em"], a["detalhe"] = agora(), detalhe[:300]
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
            a["estado"], n = "expirada", n + 1
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
                comentou = a["texto"] and "não saiu" not in (a.get("detalhe") or "") and "não foi publicado" not in (a.get("detalhe") or "")
                o_que = "seguiu e curtiu" + (f"; comentou «{a['texto'][:90]}{'…' if len(a['texto']) > 90 else ''}»" if comentou else
                                             " (o comentário não saiu)" if a["texto"] else "")
            else:
                o_que = f"{nomes[a['tipo']][:-1] if a['tipo'] != 'dm_abertura' else 'primeira mensagem'}: «{a['texto'][:120]}{'…' if len(a['texto']) > 120 else ''}»"
            linhas.append(f"• @{l.get('handle')} — {o_que}")
    if novos:
        novos.sort(key=lambda l: -(l.get("nota") or 0))
        linhas.append(f"\n🔎 *{len(novos)} leads novos* ({rejeitados} perfis examinados e descartados)")
        linhas += [f"• {l['nome'][:40]} — " + (f"nota {l['nota']}" if l.get("nota") is not None else "sem nota (antes da avaliação)")
                   + f" ({l['segmento'][:30]}, {l['cidade'][:30]})" for l in novos[:5]]
    if falhas:
        linhas.append(f"\n⚠️ {len(falhas)} não saíram: " + "; ".join(a.get("detalhe", "")[:80] for a in falhas[:3]))
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
    linhas = [f"# Prospecção — {dt.datetime.now(_tz()).strftime('%a %d/%m %H:%M')} ({FUSO})",
              "Cotas que ainda cabem hoje (propostas aprovadas contam): " + ", ".join(f"{k} {v}" for k, v in c.items())]
    if agora() < d["bloqueio_ate"]:
        linhas.append("⛔ PAUSADO após bloqueio do Instagram — não proponha nada até " +
                      dt.datetime.fromtimestamp(d["bloqueio_ate"], _tz()).strftime("%d/%m %H:%M"))
    for tipo, lista in dev.items():
        if lista:
            linhas.append(f"\n## Devem receber «{tipo}» agora ({len(lista)})")
            linhas += [f"- [{l['id']}] @{l['handle']} — {l['nome']} ({l['segmento']}, {l['cidade']}; nota {l.get('nota', '—')}); motivo: {l['motivo'][:120]}"
                       + (f"; já recebeu: {l['historico'][-1]['texto'][:160]}" if l["historico"] else "") for l in lista[:25]]
    conhecidos = sorted(l["handle"] for l in d["leads"])
    linhas.append(f"\n## Já conhecidos ({len(conhecidos)}) — não registre de novo\n" + (", ".join(conhecidos[-400:]) or "(nenhum)"))
    rej = d.get("rejeitados") or {}
    if rej:
        linhas.append(f"\n## Já examinados e rejeitados ({len(rej)}) — não abra de novo\n" + ", ".join(sorted(rej)[-400:]))
    m = metricas(login, 14)
    linhas.append(f"\n## Como está indo (14 dias)\n{json.dumps(m['geral'], ensure_ascii=False)}; por variante: "
                  f"{json.dumps(m['por_variante'], ensure_ascii=False)}; aprovação das propostas: {m['taxa_aprovacao']}%")
    return "\n".join(linhas)

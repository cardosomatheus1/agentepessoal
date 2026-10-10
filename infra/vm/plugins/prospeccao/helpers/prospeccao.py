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
        lead = {"id": _id(), "canal": canal, "handle": handle,
                "url": str(item.get("url") or f"https://www.instagram.com/{handle}/")[:200],
                "nome": str(item["nome"])[:80], "segmento": str(item["segmento"])[:40].lower(),
                "cidade": str(item["cidade"])[:60], "seguidores": str(item.get("seguidores") or "")[:20],
                "motivo": str(item["motivo"])[:300], "sinal": str(item.get("sinal") or "")[:300],
                "etapa": "novo", "criado": agora(), "atualizado": agora(), "historico": []}
        d["leads"].append(lead)
        por_handle[handle] = lead
        out["criados"].append({"handle": handle, "id": lead["id"]})
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


def mudar_etapa(login: str, lid: str, etapa: str, nota: str = "") -> dict | None:
    d = carregar(login)
    lead = _lead(d, lid)
    if not lead or etapa not in ETAPAS:
        return None
    lead["etapa"], lead["atualizado"] = etapa, agora()
    lead["historico"].append({"em": agora(), "tipo": f"etapa:{etapa}", "texto": nota[:300]})
    if etapa in FINAIS or etapa in ("respondeu", "lead"):  # pending outreach stops when they answer or are closed
        for a in d["acoes"]:
            if a["lead_id"] == lid and a["estado"] in ("proposta", "aprovada") and a["tipo"] != "resposta":
                a["estado"], a["decidida"] = "cancelada", agora()
    salvar(login, d)
    return lead


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
                "alvo": str(item.get("alvo") or lead["url"])[:200], "estado": "proposta", "criada": agora()}
        d["acoes"].append(acao)
        ja.add((lid, tipo))
        restantes[tipo] -= 1
        out["propostas"].append(acao)
    salvar(login, d)
    return out


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
                                                "motivo": f"prospecção: ação {acao['id']} ({acao['tipo']}) aprovada pelo usuário"})


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
            grupos.setdefault(l.get(campo) or "?", []).append(l)
        return {k: taxa(v) for k, v in grupos.items()}

    etapas: dict = {}
    for l in d["leads"]:
        etapas[l["etapa"]] = etapas.get(l["etapa"], 0) + 1
    aprovadas = sum(1 for a in acoes if a["estado"] in ("aprovada", "executada", "falhou"))
    decididas = sum(1 for a in acoes if a["estado"] in ("aprovada", "executada", "falhou", "pulada"))
    return {"dias": dias, "acoes": por_estado, "etapas": etapas, "geral": taxa(abordados),
            "por_variante": por("variante"), "por_segmento": por("segmento"), "por_cidade": por("cidade"),
            "taxa_aprovacao": round(100 * aprovadas / decididas, 1) if decididas else 0.0,
            "falhas": [a.get("detalhe", "") for a in acoes if a["estado"] == "falhou"][-5:],
            "pausado": agora() < d["bloqueio_ate"]}


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
            linhas += [f"- [{l['id']}] @{l['handle']} — {l['nome']} ({l['segmento']}, {l['cidade']}); motivo: {l['motivo'][:120]}"
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

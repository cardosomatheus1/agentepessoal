"""Prospecting engine for Raiz Connect: leads, the actions proposed for each one, the person's approvals, paced
execution and the numbers that say what works. State: /a0/usr/prospeccao/<login>.json.

Nothing reaches a third party unless the person approved that exact action on the phone; the execution round
takes one approved action at a time (`proxima`), within daily limits, hours and spacing, and reports back
(`resultado`). Rules that a model could forget (links in a first message, the same text twice, contacting someone
again after a "no") are enforced here, not left to the prompt."""

import datetime as dt
import fcntl
import functools
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import unicodedata
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

PASTA = Path("/a0/usr/prospeccao")
FUSO = "America/Bahia"
CAIXA_TESTES = Path("/a0/usr/testes/celular.jsonl")

TIPOS = ("aquecer", "dm_abertura", "dm_lembrete", "resposta", "parceiro", "seguimento")
LIMITE_DIA = {"aquecer": 20, "dm_abertura": 12, "dm_lembrete": 10, "resposta": 15, "parceiro": 5, "seguimento": 10}
FORA_DO_PICO = ("dm_abertura", "dm_lembrete", "seguimento")  # not sent during PICO_DM
DIAS_SEGUIMENTO = 2  # after our link, with no word from the person: one follow-up (12/10 blind review, item 7)
INTERVALO = 3 * 60                 # typical spacing between two executed actions (tests use it)
ESPACO = (2 * 60, 6 * 60)          # 12/10 blind review: the real spacing varies 2-6 min (a fixed 3 min looked like a robot)
HORARIO = (9, 20)                  # executions only within [9h, 20h) local time
PICO_DM = ("10:30", "14:00")       # no first message, reminder or follow-up while food producers are busiest
PICO_SEGMENTO = {"marmitaria": ("08:00", "14:00"), "restaurante": ("08:00", "14:00")}  # blind review 5: they cook from 7h
RESPOSTA_ATE = "22:00"             # replies to who wrote go until then (owners read after closing); the rest until 20h
FOLGA = 6                          # weekday (Monday=0) with only replies: no follow, like, comment or new message
RAMPA_DM = (5, 8, 10, 12)          # first messages a day in weeks 1, 2, 3 and after; a block in the last 7 days steps back
REAVALIAR_DIAS = 60                # a profile discarded on the visit (stale, size) comes back to the stock after this
RETORNO_AGORA_NAO = 30             # days after "agora não" before the one follow-up (blind review 4)
DIAS_VAI_PASSAR = 2                # days after "vou passar pro dono" before asking whether they talked (blind review 4)
VAI_PASSAR = re.compile(r"(vou|vai|vamos) (passar|repassar|mostrar)|passo (pra|para)|falar com (o|a) (dono|dona|respons|chefe)|"
                        r"pro dono|pra dona|pro respons|pra respons", re.I)
PEDIU_LINK = re.compile(r"n[aã]o (consegui|abriu|abre|achei|carrega)|(manda|mande|envia|envie)( o link)? (de novo|novamente)|"
                        r"(link|calculadora).{0,30}(de novo|novamente|outra vez|n[aã]o (abre|abriu|funciona))|reenvi|perdi o link", re.I)
AGORA_NAO = re.compile(r"agora n[aã]o|sem tempo|depois (eu )?vejo|outra hora|mais pra frente|no momento n[aã]o|"
                       r"m[eê]s que vem|semana que vem|ocupad", re.I)
ROBO = re.compile(r"manychat|automation powered|mensagem autom[aá]tica|resposta autom[aá]tica|j[aá] j[aá] (te )?respond|"
                  r"entraremos em contato|recebemos sua mensagem|em breve (te )?(retornaremos|responderemos)|"
                  r"obrigad[oa] pelo contato|hor[aá]rio de atendimento", re.I)
CONSULTAS_DIA = 30                 # profiles/searches read by script with our account, per day (blind review, item 1)
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
LINK_CADASTRO = "raizconnect.com.br/#/register"  # the 15-day trial signup (Matheus, 12/10: send it to who wants to test)
CADASTRO = re.compile(r"(https?://)?(www\.)?raizconnect\.com\.br/?#/register(?![\w/])", re.I)
TIPOS_COM_LINK = ("resposta",)  # 12/10 blind review: the reminder offers the link, it does not carry it


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


# ------------------------------------------------------------------ safe state file
# 12/10 review: two rounds at once could erase each other's work (the pre-approval loaded the state, waited minutes
# for the reviewer and saved over what the execution round had recorded, so a DM marked as sent could come back as
# approved), two writers shared one temporary name, and an unreadable file became an empty state that the next save
# wrote over everything. Now: one writer at a time per person (a short file lock, never held while waiting for a model
# or the network), a unique temporary file flushed to disk, and an unreadable file stops the work instead.
ESPERA_TRAVA = 60  # seconds; the critical sections take milliseconds
_DONO = threading.local()


class EstadoIlegivel(RuntimeError):
    pass


@contextmanager
def _exclusivo(login: str):
    """One writer at a time per person, across threads and processes; re-entrant in the same thread."""
    chave = _login(login)
    travas = getattr(_DONO, "travas", None)
    if travas is None:
        travas = _DONO.travas = {}
    if travas.get(chave):
        travas[chave] += 1
        try:
            yield
        finally:
            travas[chave] -= 1
        return
    PASTA.mkdir(parents=True, exist_ok=True)
    with open(PASTA / f"{chave}.lock", "a") as fh:
        limite = time.time() + ESPERA_TRAVA
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() > limite:
                    raise RuntimeError("a prospecção está ocupada gravando há mais de 1 min; tente de novo") from None
                time.sleep(0.05)
        travas[chave] = 1
        try:
            yield
        finally:
            travas[chave] = 0
            fcntl.flock(fh, fcntl.LOCK_UN)


def _transacao(fn):
    """Load → change → save as one step for the person in the first argument."""
    @functools.wraps(fn)
    def envolta(login, *args, **kwargs):
        with _exclusivo(login):
            return fn(login, *args, **kwargs)
    return envolta


def carregar(login: str) -> dict:
    arq = PASTA / f"{_login(login)}.json"
    d = {}
    if arq.exists():
        for tentativa in range(3):
            try:
                d = json.loads(arq.read_text(encoding="utf-8"))
                if not isinstance(d, dict):
                    raise ValueError("não é um objeto JSON")
                break
            except (OSError, ValueError) as exc:
                if tentativa == 2:
                    raise EstadoIlegivel(f"o arquivo da prospecção ({arq.name}) não pôde ser lido ({str(exc)[:80]}); "
                                         "nada foi gravado. Avise o Matheus.") from None
                time.sleep(0.2)
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
    "aprovada": {"executada", "falhou", "cancelada", "proposta", "incerta"},  # "proposta" again = new text (editar)
    "incerta": {"executada", "falhou"},  # handed out, never reported: checked on the screen before anything is resent
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
    with _exclusivo(login):
        PASTA.mkdir(parents=True, exist_ok=True)
        novos = d.pop("_eventos", [])
        if novos:
            with (PASTA / f"{_login(login)}_eventos.jsonl").open("a", encoding="utf-8") as f:
                for e in novos:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
        alvo = PASTA / f"{_login(login)}.json"
        fd, tmp = tempfile.mkstemp(dir=PASTA, prefix=f".{_login(login)}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, alvo)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


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
    """By internal id, by the profile: "zen.marmitas", "@zen.marmitas" or its instagram.com URL (11/10: the agent
    passed the @ and the stage change was refused), or by the id of one of its actions (12/10: the visit found an
    inactive profile, the agent passed the warm-up's id to discard it, was refused and stopped the round)."""
    lid = str(lid or "").strip()
    achado = next((l for l in d["leads"] if l["id"] == lid), None)
    if achado or not lid:
        return achado
    acao = next((a for a in d.get("acoes", []) if a["id"] == lid), None)
    if acao:
        return next((l for l in d["leads"] if l["id"] == acao["lead_id"]), None)
    handle = lid.rstrip("/").rsplit("/", 1)[-1].lstrip("@").lower()
    return next((l for l in d["leads"] if str(l.get("handle", "")).lower() == handle), None)


# ------------------------------------------------------------------ lead score (fixed rubric, computed from evidence)

NOTA_MINIMA = 55   # below: not a lead
NOTA_QUENTE = 75   # first in line for the day's limited slots
PONTOS_SEGMENTO = {"marmitaria": 25, "congelados": 25, "cozinha_producao": 25, "fabrica": 22, "confeitaria": 20,
                   "salgados": 20, "doces": 18, "padaria": 15, "restaurante": 15, "outro_alimento": 5}
CANAIS_VENDA = ("ifood", "encomenda", "delivery", "whatsapp", "loja", "catalogo", "direct")
SINAIS = ("reajuste", "insumo", "expansao", "contratacao", "cardapio_precos", "kits", "promocao", "reclamacao_custo",
          "responde_comentarios")
EXCLUSOES = {"rede": "rede ou franquia", "franquia": "rede ou franquia", "pessoal": "perfil pessoal",
             "privado": "perfil privado", "concorrente": "concorrente/sistema/consultoria",
             "curso": "curso/influenciador (é parceiro, não cliente)", "influencer": "curso/influenciador (é parceiro, não cliente)"}
# Region (Matheus, 12/10: "não precisa ser só Salvador, é Brasil mesmo"): any city in Brazil scores; only a city
# clearly abroad is out. CIDADES_BR is only used to READ the city from a bio (the rubric no longer filters by it).
REGIOES = ("salvador", "lauro de freitas", "camaçari", "camacari", "simões filho", "simoes filho", "candeias",
           "dias d'ávila", "dias davila", "madre de deus", "são francisco do conde", "vera cruz", "itaparica",
           "são paulo", "sao paulo", "campinas")
CIDADES_BR = REGIOES + (
    "rio de janeiro", "belo horizonte", "curitiba", "porto alegre", "recife", "fortaleza", "brasília", "brasilia",
    "goiânia", "goiania", "florianópolis", "florianopolis", "vitória", "vitoria", "manaus", "belém", "belem",
    "são luís", "sao luis", "joão pessoa", "joao pessoa", "natal", "maceió", "maceio", "aracaju", "teresina",
    "cuiabá", "cuiaba", "campo grande", "palmas", "porto velho", "rio branco", "macapá", "macapa", "boa vista",
    "guarulhos", "santo andré", "santo andre", "são bernardo", "sao bernardo", "osasco", "santos", "sorocaba",
    "ribeirão preto", "ribeirao preto", "são josé dos campos", "sao jose dos campos", "jundiaí", "jundiai",
    "niterói", "niteroi", "duque de caxias", "nova iguaçu", "nova iguacu", "contagem", "uberlândia", "uberlandia",
    "juiz de fora", "londrina", "maringá", "maringa", "joinville", "blumenau", "caxias do sul", "pelotas",
    "feira de santana", "vitória da conquista", "vitoria da conquista", "ilhéus", "ilheus", "itabuna", "jaboatão",
    "olinda", "caruaru", "petrolina", "juazeiro", "campina grande", "mossoró", "mossoro", "anápolis", "anapolis",
    "aparecida de goiânia", "vila velha", "serra", "cariacica", "betim", "montes claros")
FORA_DO_BRASIL = re.compile(r"\b(portugal|lisboa|porto, portugal|miami|orlando|eua|usa|estados unidos|new york|london|"
                            r"londres|argentina|buenos aires|chile|santiago de chile|m[eé]xico|espanha|madrid|"
                            r"barcelona|paris|it[aá]lia|roma|canad[aá]|toronto|uruguai|montevid[eé]u|paraguai)\b", re.I)


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
    stories = str(item.get("stories") or "").lower() in ("true", "1", "sim")  # blind review 4: menus live in the stories
    if dias is not None and dias > 30 and not stories:
        return {"rejeitado": f"parado há {dias} dias"}
    seguidores = _numero(item.get("seguidores"))
    tamanho_pendente = bool(item.get("atividade_pendente")) and not seguidores  # checked on the warm-up visit
    if tamanho_pendente:
        pass
    elif seguidores < 300:
        return {"rejeitado": f"pequeno demais ({seguidores} seguidores)"}
    if seguidores > 50_000:
        return {"rejeitado": f"grande demais ({seguidores} seguidores: cara de rede)"}
    cidade = str(item.get("cidade") or "").strip().lower()
    if not cidade:
        return {"rejeitado": "sem a cidade (confira no perfil)"}
    if FORA_DO_BRASIL.search(cidade):
        return {"rejeitado": f"fora do Brasil ({item.get('cidade')})"}
    canais = {str(x).lower() for x in (item.get("canais") or [])} & set(CANAIS_VENDA)
    sinais = {str(x).lower() for x in (item.get("sinais") or [])} & set(SINAIS)
    partes = {
        "segmento": PONTOS_SEGMENTO[seg],
        "atividade": 15 if stories else 12 if dias is None else 15 if dias <= 7 else 12 if dias <= 14 else 8,
        "porte": 12 if tamanho_pendente else 15 if 500 <= seguidores <= 5000 else 12 if seguidores <= 20_000 and seguidores > 5000 else 8 if seguidores > 20_000 else 6,
        "regiao": 10,
        "canais": min(10, 3 * len(canais) + (1 if len(canais) >= 3 else 0)),
        "sinais": min(15, 5 * len(sinais)),
        "profissional": (5 if item.get("cardapio") else 0) + (5 if item.get("link_pedido") else 0),
        # will this person read a DM? orders by Direct or answers to comments: yes; orders only by WhatsApp: less likely
        "le_direct": 5 if ("direct" in canais or "responde_comentarios" in sinais) else -5 if canais == {"whatsapp"} else 0,
    }
    nota = max(0, min(100, sum(partes.values())))
    return {"nota": nota, "partes": partes, "dias_ultimo_post": dias, "seguidores_n": seguidores, "segmento_rubrica": seg,
            "faixa": "quente" if nota >= NOTA_QUENTE else "bom" if nota >= 65 else "ok" if nota >= NOTA_MINIMA else "fraco"}


@_transacao
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
                                                         "produto_exemplo", "post_recente", "stories") if item.get(k)},
                "url": str(item.get("url") or f"https://www.instagram.com/{handle}/")[:200],
                "nome": str(item["nome"])[:80], "segmento": str(item["segmento"])[:40].lower(),
                "cidade": str(item["cidade"])[:60], "seguidores": str(item.get("seguidores") or "")[:20],
                "motivo": str(item["motivo"])[:300], "sinal": str(item.get("sinal") or "")[:300],
                "etapa": "novo", "criado": agora(), "atualizado": agora(), "historico": []}
        if item.get("atividade_pendente") and not item.get("ultimo_post"):
            lead["conferir_atividade"] = True  # found outside Instagram: last post checked on the warm-up visit
            lead["fonte"] = str(item.get("fonte") or "")[:40]
        lead["origem"] = origem({**lead, "origem": item.get("origem"), "fonte": item.get("fonte") or lead.get("fonte", "")})
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
             "whatsapp": r"whats|wa\.me|zap", "loja": r"\bloja\b|retirada|endere[cç]o|\brua\b|\bav\.", "catalogo": r"cat[aá]logo",
             "direct": r"\b(?:no|pelo|via|chama no|manda(?: um)?)\s+direct\b|\bdm\b|\binbox\b"}
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
      if (r.status === 429) { achados['__429__'] = 'http 429'; break; }
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
        if h and h not in ja and h not in out and h != "__429__":  # the search script's 429 marker is not a profile
            out.append(h)
    return out[:limite]


def scripts_conta(login: str) -> bool:
    """Search/profile scripts run with the brand's logged-in account (blind reviews 2 and 3: the riskiest thing the
    account does). Off unless the person turns them on; Apify and the official API cover the stock."""
    return bool(carregar(login)["config"].get("scripts_conta"))


@_transacao
def definir_scripts_conta(login: str, ligado: bool) -> None:
    d = carregar(login)
    d["config"]["scripts_conta"] = bool(ligado)
    salvar(login, d)


def api_pausada(login: str) -> str:
    """'' or until when the profile scripts are paused after an Instagram 429 (or the day's query ceiling)."""
    c = carregar(login)["config"]
    ate = c.get("api_pausa_ate") or 0
    if agora() >= ate:
        return ""
    if ate - agora() > 30 * 86400:
        return "o Matheus liberar (o Instagram limitou as consultas dois dias seguidos)"
    return "amanhã" if _hoje_local(ate) != _hoje_local() else dt.datetime.fromtimestamp(ate, _tz()).strftime("%H:%M")


def _amanha_cedo() -> float:
    amanha = dt.datetime.fromtimestamp(agora(), _tz()).date() + dt.timedelta(days=1)
    return dt.datetime.combine(amanha, dt.time(0, 0), _tz()).timestamp()


def _registrar_429(d: dict) -> None:
    """12/10 blind review, item 1: the 429 is the Instagram warning about OUR account. Every script that reads
    Instagram with it stops until the next day (it used to be 15 min, and the round then opened profiles by hand);
    two days in a row, nothing runs until the person decides (`liberar_consultas`)."""
    hoje = _hoje_local()
    ontem = (dt.datetime.fromtimestamp(agora(), _tz()).date() - dt.timedelta(days=1)).isoformat()
    dias = [x for x in (d["config"].get("api_429_dias") or []) if x != hoje][-5:] + [hoje]
    d["config"]["api_429_dias"] = dias
    d["config"]["api_pausa_ate"] = agora() + 365 * 86400 if ontem in dias else _amanha_cedo()


@_transacao
def limite_consulta(login: str, detalhe: str = "") -> str:
    """The round saw a 429 (or a "try again later" on a query): record it; returns until when the queries stop."""
    d = carregar(login)
    _registrar_429(d)
    d["config"]["api_pausa_detalhe"] = str(detalhe or "")[:200]
    salvar(login, d)
    return api_pausada(login)


@_transacao
def liberar_consultas(login: str) -> None:
    """The person allows the profile scripts again (after a two-day 429 stop)."""
    d = carregar(login)
    d["config"]["api_pausa_ate"] = 0
    d["config"]["api_429_dias"] = []
    salvar(login, d)


@_transacao
def reservar_consultas(login: str, n: int) -> int:
    """How many of `n` profile/search reads with our account fit in today's ceiling (CONSULTAS_DIA); counted now."""
    d = carregar(login)
    reg = d["config"].get("consultas_dia") or {}
    if reg.get("dia") != _hoje_local():
        reg = {"dia": _hoje_local(), "n": 0}
    teto = int(d["config"].get("consultas_teto") or CONSULTAS_DIA)
    cabem = max(0, min(int(n), teto - int(reg["n"])))
    reg["n"] = int(reg["n"]) + cabem
    d["config"]["consultas_dia"] = reg
    salvar(login, d)
    return cabem


# ------------------------------------------------------------------ official API (Instagram Graph "business discovery")

GRAPH = "https://graph.facebook.com/v25.0"
COFRE_TOKEN, COFRE_IG, COFRE_PAGINA = "META_IG_TOKEN", "META_IG_USER_ID", "META_PAGE_ID"


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


def escolher_token_meta(tokens: list) -> str:
    """Of the tokens read on the screen, the one that lasts longest by Meta's own answer (debug_token): never expiring
    first, then the latest expiry; invalid ones are left out."""
    melhor, nota_melhor = "", -1.0
    for tok in tokens[:10]:
        info = _graph("debug_token", {"input_token": tok, "access_token": tok}).get("data") or {}
        if not info.get("is_valid", True):
            continue
        expira = info.get("expires_at") or 0
        nota = float("inf") if not expira else float(expira)
        if nota > nota_melhor:
            melhor, nota_melhor = tok, nota
    return melhor


def guardar_token_meta(login: str, token_usuario: str) -> dict:
    """From a token read on the screen: the Page token linked to the prospecting Instagram account and the IG user id,
    kept in the owner's vault. A Page token taken from a LONG-lived user token never expires; from a short one it lasts
    about an hour (12/10: the first one stored expired the same afternoon, and the second try read a Page token, for
    which me/accounts is empty). A Page token is now recognized as such, and when the stored token expires the answer
    says exactly what to extend. Returns a summary without secrets."""
    esperado = conta(login) or "raiz.connect"
    info = _graph("debug_token", {"input_token": token_usuario, "access_token": token_usuario}).get("data") or {}
    if info.get("type") == "PAGE":
        pg = _graph("me", {"fields": "id,name,instagram_business_account{id,username}", "access_token": token_usuario})
        conta_ig = pg.get("instagram_business_account") or {}
        if str(conta_ig.get("username", "")).lower() != esperado:
            return {"ok": False, "erro": f"o token é de uma Página que não está ligada a @{esperado}"}
        alvo = {"name": pg.get("name", ""), "access_token": token_usuario, "instagram_business_account": conta_ig}
    else:
        r = _graph("me/accounts", {"fields": "name,access_token,instagram_business_account{id,username}", "limit": 50,
                                   "access_token": token_usuario})
        if r.get("error"):
            return {"ok": False, "erro": r["error"].get("message", "")[:200]}
        paginas = r.get("data") or []
        alvo = next((pg for pg in paginas if (pg.get("instagram_business_account") or {}).get("username", "").lower() == esperado), None)
        pid = str(_cofre().carregar(login).get(COFRE_PAGINA) or "")
        if not alvo and pid:
            # a Page inside a business portfolio is not listed by me/accounts without business_management (12/10):
            # ask the known Page for its token directly
            pg = _graph(pid, {"fields": "name,access_token,instagram_business_account{id,username}", "access_token": token_usuario})
            if pg.get("access_token") and (pg.get("instagram_business_account") or {}).get("username", "").lower() == esperado:
                alvo = pg
        if not alvo:
            ligadas = {pg.get("name"): (pg.get("instagram_business_account") or {}).get("username") for pg in paginas}
            return {"ok": False, "erro": f"nenhuma Página ligada a @{esperado}", "paginas": ligadas}
    c = _cofre()
    c.salvar(login, COFRE_TOKEN, alvo["access_token"]); c.descrever(login, COFRE_TOKEN, f"Meta · token da Página {alvo['name']} (leitura do Instagram @{esperado})")
    c.salvar(login, COFRE_IG, alvo["instagram_business_account"]["id"]); c.descrever(login, COFRE_IG, f"Meta · id da conta @{esperado}")
    if alvo.get("id"):
        c.salvar(login, COFRE_PAGINA, str(alvo["id"])); c.descrever(login, COFRE_PAGINA, f"Meta · id da Página {alvo['name']}")
    info = _graph("debug_token", {"input_token": alvo["access_token"], "access_token": alvo["access_token"]}).get("data") or {}
    expira, acesso = info.get("expires_at", 0), info.get("data_access_expires_at", 0)
    _ACESSO_META.pop(_login(login), None)  # the next round reads the new dates
    out = {"ok": True, "pagina": alvo["name"], "instagram": esperado,
           "expira": "nunca" if not expira else dt.datetime.fromtimestamp(expira, _tz()).strftime("%d/%m/%Y %H:%M"),
           "acesso_aos_dados_ate": dt.datetime.fromtimestamp(acesso, _tz()).strftime("%d/%m/%Y") if acesso else "sem limite"}
    if expira:
        out["aviso"] = ("este token vence: no Explorador da Graph API escolha «Token do usuário» (não Página), gere, abra na "
                        "ferramenta de token, clique em «Estender token de acesso» e chame token_meta de novo com essa aba aberta")
    return out


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
                if ROBO.search(texto):
                    continue  # an automatic reply (Manychat, "recebemos sua mensagem"): the person did not write yet
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
    cidade = next((r for r in CIDADES_BR if re.search(rf"\b{re.escape(r)}\b", texto_bio)), "")
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


@_transacao
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
    if any("429" in e["erro"] for e in out["erros"]):  # Instagram rate limit on our account: stop reading
        d = carregar(login)
        _registrar_429(d)
        salvar(login, d)
    if para_registrar:
        r = registrar(login, para_registrar)
        out["criados"] += r["criados"]
        out["recusados"] += r["recusados"]
        out["recusados"] += [{"handle": x["handle"], "motivo": "já conhecido"} for x in r["repetidos"]]
    return out


# ------------------------------------------------------------------ stock check before the visit
# 12/10: 11 of the 15 sheet profiles visited were discarded on the visit (stale, too big, private, gone). Leads found
# outside Instagram are now checked in batches before their turn: the browser script (5 profiles a call), the
# official API (business discovery) or a scraper's data (Apify) in the same shape. What fails the hard rules leaves
# the stock now; what passes gets its real numbers and score. Whether it is the right business is still looked at on
# the visit (conferir_negocio).

def a_conferir(login: str, limite: int = 5, via: str = "script") -> list:
    """Handles of stock leads whose activity and size were not checked yet, best score first. The official API only
    reads business/creator accounts: via="api" leaves out the ones it could not read (they go by the script)."""
    d = carregar(login)
    tentados = {a["lead_id"] for a in d["acoes"] if a["tipo"] == "aquecer" and a["estado"] in ("falhou", "cancelada")}
    pend = [l for l in d["leads"] if l["etapa"] == "novo" and l.get("conferir_atividade") and l["id"] not in tentados
            and l.get("conferencia_falhas", 0) < 2 and not (via == "api" and l.get("conferir_por_script"))]
    pend.sort(key=lambda l: -(l.get("nota") or 0))
    return [l["handle"] for l in pend[:limite]]


def _perfil_padrao(p: dict) -> dict:
    """An Apify instagram-profile-scraper item in the browser script's shape (script/API items pass unchanged)."""
    if "handle" in p or "username" not in p:
        return p
    if p.get("error") or p.get("errorDescription"):
        return {"handle": p["username"], "erro": "perfil não encontrado" if "not" in str(p.get("error") or p.get("errorDescription")).lower()
                else str(p.get("error") or p.get("errorDescription"))[:80]}
    posts = []
    for m in p.get("latestPosts") or []:
        try:
            ts = int(dt.datetime.fromisoformat(str(m.get("timestamp")).replace("Z", "+00:00")).timestamp())
        except ValueError:
            continue
        posts.append({"fixado": bool(m.get("isPinned")), "ts": ts, "codigo": m.get("shortCode") or "",
                      "legenda": (m.get("caption") or "")[:200]})
    return {"handle": p["username"], "nome": p.get("fullName") or "", "seguidores": p.get("followersCount") or 0,
            "privado": bool(p.get("private")), "bio": (p.get("biography") or "")[:300], "link": p.get("externalUrl") or "",
            "categoria": p.get("businessCategoryName") or "", "posts": posts}


@_transacao
def conferir_perfis(login: str, dados, fonte: str = "script") -> dict:
    """Profile data for stock leads still to be checked. Returns {"conferidos": [...], "descartados": [...], "erros": [...]}."""
    perfis = json.loads(dados) if isinstance(dados, str) else (dados or [])
    out = {"conferidos": [], "descartados": [], "erros": []}
    d = carregar(login)
    por_handle = {l["handle"]: l for l in d["leads"]}
    descartar = []
    for bruto in perfis if isinstance(perfis, list) else []:
        if not isinstance(bruto, dict):
            continue
        perfil = _perfil_padrao(bruto)
        lead = por_handle.get(normalizar(str(perfil.get("handle") or "")))
        if not lead or lead["etapa"] != "novo" or not lead.get("conferir_atividade"):
            continue
        erro = str(perfil.get("erro") or "")
        if erro:
            if fonte == "api" and "conta pessoal" in erro:
                # the API reads only business/creator accounts; a small producer often has a personal one: the
                # browser script checks it instead (never a discard for that)
                lead["conferir_por_script"] = True
                out.setdefault("pelo_script", []).append(lead["handle"])
            elif re.search(r"não encontrado|http 404", erro):
                descartar.append((lead, f"conferido antes da visita: {erro}"))
            else:  # rate limit or network: try again later; after 2 tries the visit checks it
                lead["conferencia_falhas"] = lead.get("conferencia_falhas", 0) + 1
                out["erros"].append({"handle": lead["handle"], "erro": erro})
            continue
        ev = _evidencia(perfil)
        item = {**ev, "segmento": ev["segmento"] or lead["segmento"], "cidade": ev["cidade"] or lead["cidade"],
                "canais": sorted(set(ev["canais"]) | set((lead.get("evidencias") or {}).get("canais") or []))}
        teste = pontuar(item)
        motivo = teste.get("rejeitado") or (f"nota {teste['nota']} depois de conferir (mínimo {NOTA_MINIMA})"
                                            if teste["nota"] < NOTA_MINIMA else "")
        if motivo:
            descartar.append((lead, f"conferido antes da visita: {motivo}"))
            continue
        lead.update({"nota": teste["nota"], "faixa": teste["faixa"], "seguidores": str(ev["seguidores"])[:20],
                     "avaliacao": {k: teste[k] for k in ("partes", "faixa", "dias_ultimo_post", "seguidores_n", "segmento_rubrica")},
                     "conferir_atividade": False, "conferir_negocio": origem(lead) != "instagram",
                     "conferencia": {"em": agora(), "fonte": fonte, "ultimo_post": ev["ultimo_post"], "seguidores": ev["seguidores"]}})
        lead.setdefault("evidencias", {}).update({k: item[k] for k in ("ultimo_post", "canais", "post_recente") if item.get(k)})
        out["conferidos"].append({"handle": lead["handle"], "nota": teste["nota"], "ultimo_post": ev["ultimo_post"],
                                  "seguidores": ev["seguidores"]})
    if any("429" in e["erro"] for e in out["erros"]):  # Instagram rate limit on our account: stop reading
        _registrar_429(d)
    salvar(login, d)
    for lead, motivo in descartar:
        mudar_etapa(login, lead["id"], "descartado", motivo[:300])
        out["descartados"].append({"handle": lead["handle"], "motivo": motivo})
    return out


def apify_pronto(login: str) -> bool:
    """Apify's token is in the person's vault (APIFY_API)."""
    try:
        s = _cofre().carregar(login)
    except Exception:
        return False
    return bool(s.get("APIFY_API") or s.get("APIFY_TOKEN") or s.get("APIFY_API_TOKEN"))


def api_meta_pronta(login: str) -> bool:
    """The official API (business discovery) is configured in the person's vault."""
    try:
        s = _cofre().carregar(login)
    except Exception:
        return False
    return bool(s.get(COFRE_TOKEN) and s.get(COFRE_IG))


# The Page token never expires, but Meta cuts its access to data 90 days after the Facebook account last authorized
# the app ("data access expiration"; 12/10 → 10/01/2027). Matheus asked for at least 90 days: the search round sees
# the date and renews it by itself (same steps as the first time) in the last 15 days, before anything stops.
RENOVAR_META_DIAS = 15
_ACESSO_META: dict = {}


def acesso_meta(login: str) -> dict:
    """{"expira": ts|0, "acesso_ate": ts|0, "valido": bool} of the stored token, by Meta itself; cached for 6 h."""
    guardado = _ACESSO_META.get(_login(login))
    if guardado and agora() - guardado["em"] < 6 * 3600:
        return guardado["info"]
    try:
        tok = _cofre().carregar(login).get(COFRE_TOKEN) or ""
    except Exception:
        tok = ""
    if not tok:
        return {}
    d = _graph("debug_token", {"input_token": tok, "access_token": tok}).get("data") or {}
    info = {"expira": d.get("expires_at") or 0, "acesso_ate": d.get("data_access_expires_at") or 0,
            "valido": bool(d.get("is_valid"))} if d else {}
    _ACESSO_META[_login(login)] = {"em": agora(), "info": info}
    return info


def aviso_acesso_meta(info: dict, agora_ts: float) -> str:
    """The renewal instruction for the round when the data access ends within RENOVAR_META_DIAS (or already ended)."""
    if not info:
        return ""
    datas = [t for t in (info.get("expira"), info.get("acesso_ate")) if t]
    fim, valido = (min(datas) if datas else 0), info.get("valido", True)
    if valido and (not fim or fim - agora_ts > RENOVAR_META_DIAS * 86400):
        return ""
    if not valido or (fim and fim <= agora_ts):
        quando = "já venceu"
    else:
        quando = (f"vence em {max(1, int((fim - agora_ts) // 86400))} dia(s), "
                  f"{dt.datetime.fromtimestamp(fim, _tz()).strftime('%d/%m')}")
    return (f"🔑 O acesso da API da Meta aos dados {quando}: renove agora, sem pedir ok (decisão do Matheus). "
            "Explorador da Graph API → app «Raiz Prospecção» → Token do usuário (pages_show_list, pages_read_engagement, "
            "instagram_basic, instagram_manage_insights) → Generate Access Token (autorize a Página e a @raiz.connect) → "
            "«i» → abrir na ferramenta de token → Estender token de acesso → `prospeccao` acao \"token_meta\" com a aba "
            "aberta. Confira no resultado o novo «acesso_aos_dados_ate».")


REJEITADO_DIAS = 60


@_transacao
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


def _mesma_citacao(a: str, b: str) -> bool:
    """The same words of the person read twice by different rounds: @mentions and punctuation aside, equal or one
    inside the other (12/10 18h: "@raiz.connect oieeee….entra sim!!!!" and "oieeee….entra sim!!!" were two entries)."""
    na, nb = (" ".join(_citacao(re.sub(r"@[\w.]+", " ", x or "")).split()) for x in (a, b))
    return na == nb or (min(len(na), len(nb)) >= 8 and (na in nb or nb in na))


RESPOSTAS_ETAPAS = ("respondeu", "lead", "demo", "teste", "cliente")  # the answer funnel, in order


@_transacao
def entrou_aviso(login: str, handle: str, fala: str) -> bool:
    """Someone outside the registry wrote to @raiz.connect about something else: True only the first time this text
    is seen, so the person is told once and not by every round (blind review 4, item 3)."""
    d = carregar(login)
    vistos = d.setdefault("fora_do_registro", {}).setdefault(normalizar(handle), [])
    if any(_mesma_citacao(v.get("texto", ""), fala) for v in vistos):
        return False
    vistos.append({"em": agora(), "texto": " ".join(str(fala or "").split())[:300]})
    salvar(login, d)
    return True


@_transacao
def registrar_entrada(login: str, handle: str, fala: str) -> dict:
    """Someone outside the registry wrote about the Raiz, the calculator, a price or our comment: the hottest lead
    there is. Registered without a score (they came to us); their words then go through mudar_etapa like any answer."""
    d = carregar(login)
    h = normalizar(handle)
    if not h:
        return {"erro": "sem o @"}
    existente = next((l for l in d["leads"] if l["handle"] == h), None)
    if existente:
        return {"lead_id": existente["id"], "existia": True}
    lead = {"id": _id(), "canal": "instagram", "handle": h, "nota": None, "faixa": "entrada", "avaliacao": {},
            "evidencias": {}, "url": f"https://www.instagram.com/{h}/", "nome": h, "segmento": "", "cidade": "",
            "seguidores": "", "motivo": "escreveu para a Raiz: " + " ".join(str(fala or "").split())[:200], "sinal": "",
            "etapa": "novo", "criado": agora(), "atualizado": agora(), "historico": [], "origem": "instagram",
            "entrada": True}
    d["leads"].append(lead)
    salvar(login, d)
    return {"lead_id": lead["id"], "existia": False}


@_transacao
def interacao_comentario(login: str, lid: str, nota: str = "") -> dict | None:
    """12/10 blind review, item 3: someone who answers our comment ("obrigada! fazemos sim") did not answer an offer.
    It is an interaction: the person goes first in the queue of the first message (which may mention the exchange),
    no reply with the link is proposed and the person is not notified about it. Only talk about price/cost, or a
    message in the Direct, makes "respondeu"."""
    d = carregar(login)
    lead = _lead(d, lid)
    if not lead:
        return None
    nota = " ".join(str(nota or "").split())[:300]
    if any((h["tipo"] == "interagiu" or str(h["tipo"]).startswith("etapa:")) and h.get("onde") == "comentario"
           and _mesma_citacao(h.get("texto", ""), nota) for h in lead["historico"]):
        return {**lead, "novidade": False}
    lead["interagiu"] = lead.get("interagiu") or agora()
    lead["historico"].append({"em": agora(), "tipo": "interagiu", "texto": nota or "respondeu ao nosso comentário",
                              "onde": "comentario"})
    salvar(login, d)
    return {**lead, "novidade": True}


@_transacao
def mudar_etapa(login: str, lid: str, etapa: str, nota: str = "", onde: str = "direct") -> dict | None:
    """New stage. The returned lead carries "novidade": False when it is not a new answer: the rounds re-read the same
    Direct and comments every half hour and describe the same message in other words (11–12/10: "respondeu" reached
    the phone 3–4 times). One answer is news once:
    - the same quote at the same place is the same answer;
    - re-read before we answered it, an answer at the same place is the same answer (comments since 11/10, the Direct
      too since 12/10);
    - the same answer understood better (respondeu → lead) moves the stage up without a new notice;
    - the stage never goes back: a new message from someone already a lead keeps "lead"."""
    d = carregar(login)
    lead = _lead(d, lid)
    if not lead or etapa not in ETAPAS:
        return None
    onde = onde if onde in ONDE else "direct"
    nota = nota[:300]
    if etapa in RESPOSTAS_ETAPAS:
        tipos = {f"etapa:{e}" for e in RESPOSTAS_ETAPAS}
        falas = [h for h in lead["historico"] if h["tipo"] in tipos and not h.get("mesma_fala")]
        mesma = any(_citacao(h.get("texto", "")) == _citacao(nota) and h.get("onde", "direct") == onde for h in falas)
        if not mesma and falas and falas[-1].get("onde", "direct") == onde:
            respondemos = any(a["lead_id"] == lead["id"] and a["tipo"] == "resposta" and a["estado"] == "executada"
                              and a.get("executada_em", 0) > falas[-1]["em"] for a in d["acoes"])
            mesma = not respondemos
        nivel = lambda e: RESPOSTAS_ETAPAS.index(e) if e in RESPOSTAS_ETAPAS else -1  # noqa: E731
        sobe = nivel(etapa) > nivel(lead["etapa"])
        if mesma:
            if sobe:
                lead["etapa"], lead["atualizado"] = etapa, agora()
                lead["historico"].append({"em": agora(), "tipo": f"etapa:{etapa}", "texto": nota, "onde": onde, "mesma_fala": True})
                salvar(login, d)
            return {**lead, "novidade": False}
        lead["etapa"], lead["atualizado"] = (etapa if sobe or nivel(lead["etapa"]) < 0 else lead["etapa"]), agora()
    else:
        repetida = any(h["tipo"] == f"etapa:{etapa}" and _citacao(h.get("texto", "")) == _citacao(nota)
                       and h.get("onde", "direct") == onde for h in lead["historico"])
        if repetida and lead["etapa"] == etapa:
            return {**lead, "novidade": False}
        lead["etapa"], lead["atualizado"] = etapa, agora()
    lead["historico"].append({"em": agora(), "tipo": f"etapa:{etapa}", "texto": nota, "onde": onde})
    if (etapa == "descartado" and not any(h["tipo"] in TIPOS_DIRECT for h in lead["historico"])
            and _motivo_descarte(nota) in ("parado", "tamanho") and not re.search(r"rede|franquia", nota, re.I)):
        lead["reavaliar_em"] = agora() + REAVALIAR_DIAS * 86400  # never contacted: a stale or small profile may change
    if etapa in FINAIS or etapa in ("respondeu", "lead"):  # pending outreach stops when they answer or are closed
        for a in d["acoes"]:
            if a["lead_id"] == lead["id"] and a["estado"] in ("proposta", "aprovada") and a["tipo"] != "resposta":
                _mudar(d, a, "cancelada", f"lead foi para {etapa}", decidida=agora())
    salvar(login, d)
    return {**lead, "novidade": True}


@_transacao
def fechar_vencidos(login: str) -> int:
    """Leads that got the reminder and stayed silent become sem_resposta (no third message, ever)."""
    d = carregar(login)
    n = 0
    for l in d["leads"]:
        if l["etapa"] == "lembrado" and agora() - l["atualizado"] > ESPERA_FIM:
            l["etapa"], l["atualizado"] = "sem_resposta", agora()
            n += 1
        elif (l["etapa"] == "abordado" and not l.get("interagiu")
              and agora() - l["atualizado"] > DIAS_LEMBRETE * 86400 + ESPERA_FIM):
            l["etapa"], l["atualizado"] = "sem_resposta", agora()  # no reminder for them: closes after the same wait
            n += 1
        elif l["etapa"] == "descartado" and l.get("reavaliar_em") and agora() >= l["reavaliar_em"]:
            l.pop("reavaliar_em")  # back to the stock; the visit checks it again before following
            l["etapa"], l["atualizado"], l["conferir_atividade"], l["reaberto_em"] = "novo", agora(), True, agora()
            l["historico"].append({"em": agora(), "tipo": "etapa:novo", "texto": "volta ao estoque para nova avaliação"})
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
# The stock is split among the sources (Matheus, 12/10: "acho que temos que dividir as fontes") so each one keeps
# flowing and its yield can be compared: by 12/10, 11 of the 15 sheet profiles visited were discarded (stale, too big,
# private) while the 14 found on Instagram itself had no discard and gave both replies. So Instagram gets the bigger
# share (Matheus: "se a planilha rende pouco Instagram, como ela vai ficar com 60%?") and the CNPJ catalog (2 leads out
# of 100 companies) is out until it proves otherwise. A source with no share is used only when the others are empty.
# Config "estoque_fontes".
ORIGENS = ("planilha", "instagram", "catalogo")
ESTOQUE_FONTES = {"planilha": 40, "instagram": 60, "catalogo": 0}


def origem(lead: dict) -> str:
    """Where a lead came from: the Grok SDR sheet, Instagram itself (the agent's search) or the CNPJ catalog."""
    o = str(lead.get("origem") or "")
    if o in ORIGENS:
        return o
    t = f"{lead.get('fonte', '')} {lead.get('motivo', '')}"
    if re.search(r"grok|planilha|sdr", t, re.I):
        return "planilha"
    if re.search(r"guiapj|\bCNPJ \d", t, re.I) or lead.get("conferir_atividade"):
        return "catalogo"
    return "instagram"


def _alvos_fontes(d: dict, alvo: int) -> dict:
    cfg = d["config"].get("estoque_fontes") or ESTOQUE_FONTES
    pesos = {o: max(0, int(cfg.get(o) or 0)) for o in ORIGENS}
    total = sum(pesos.values()) or 1
    return {o: round(alvo * pesos[o] / total) for o in ORIGENS}


def _tentados(d: dict) -> set:
    """Leads whose warm-up failed or was cancelled (a failed visit is not retried) — since they came back to the stock,
    when they did (REAVALIAR_DIAS)."""
    reaberto = {l["id"]: float(l.get("reaberto_em") or 0) for l in d["leads"]}
    return {a["lead_id"] for a in d["acoes"] if a["tipo"] == "aquecer" and a["estado"] in ("falhou", "cancelada")
            and float(a.get("criada") or 0) >= reaberto.get(a["lead_id"], 0)}


def estoque(login: str) -> dict:
    """New leads ready to be warmed (Instagram, never tried) vs the target, in total and per source:
    {"prontos", "alvo", "faltam", "por_fonte": {origem: {"prontos", "alvo", "faltam", "a_conferir"}}}."""
    d = carregar(login)
    tentados = _tentados(d)
    novos = [l for l in d["leads"] if l["etapa"] == "novo" and l["canal"] == "instagram" and l["id"] not in tentados]
    alvo = int(d["config"].get("estoque_alvo") or ESTOQUE_ALVO)
    alvos = _alvos_fontes(d, alvo)
    por_fonte = {}
    for o in ORIGENS:
        meus = [l for l in novos if origem(l) == o]
        por_fonte[o] = {"prontos": len(meus), "alvo": alvos[o], "faltam": max(0, alvos[o] - len(meus)),
                        "a_conferir": sum(1 for l in meus if l.get("conferir_atividade"))}
    return {"prontos": len(novos), "alvo": alvo, "faltam": max(0, alvo - len(novos)), "por_fonte": por_fonte}


def _fila_repor(login: str) -> list:
    """Best new lead that may take a free «aquecer» slot today ([] when none or no pre-approval). Someone who
    interacted with the Raiz goes first; otherwise the sources take turns by their share of the stock, so each one is
    tried and measured every day. A failed visit is not retried."""
    d = carregar(login)
    if not d["config"].get("auto") or cotas(login)["aquecer"] <= 0:
        return []
    tentados = _tentados(d)
    candidatos = [l for l in devidos(login)["aquecer"] if l["id"] not in tentados]
    if not candidatos or candidatos[0].get("interagiu"):
        return candidatos[:1]
    alvos = _alvos_fontes(d, 100)
    hoje = _hoje_local()
    vez = Counter(origem(_lead(d, a["lead_id"]) or {}) for a in d["acoes"]
                  if a["tipo"] == "aquecer" and _hoje_local(a.get("criada", 0)) == hoje)
    por_origem: dict = {}
    for l in candidatos:
        por_origem.setdefault(origem(l), []).append(l)
    com_peso = [o for o in por_origem if alvos.get(o)]
    escolhida = min(com_peso, key=lambda o: (vez[o] / alvos[o], -alvos[o])) if com_peso else next(iter(por_origem))
    # within the source: profiles already checked (last post known) before the ones still to be checked on the visit
    return sorted(por_origem[escolhida], key=lambda l: bool(l.get("conferir_atividade")))[:1]


def _motivo_descarte(texto: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", str(texto or "")) if unicodedata.category(c) != "Mn").lower()
    if re.search(r"privad|indispon|confirm|outro neg|nao corresponde|inexist", t):
        return "não confere / privado"
    if re.search(r"seguidor|grande|pequeno|rede|franquia", t):
        return "tamanho"
    if re.search(r"parad|dias|post|inativ", t):
        return "parado"
    return "outro"


def metricas_fontes(login: str, dias: int = 28) -> dict:
    """Funnel per source over the last days: leads in, profiles visited, discarded on the visit (and why), warmed,
    first messages, answers. Splitting the sources is only worth it if we know which one pays off."""
    d = carregar(login)
    corte = agora() - dias * 86400
    out = {o: {"leads": 0, "visitados": 0, "descartados_visita": 0, "motivos": {}, "aquecidos": 0, "abordados": 0,
               "responderam": 0} for o in ORIGENS}
    visitas: dict = {}
    for a in d["acoes"]:
        if a["tipo"] == "aquecer" and a["estado"] in ("executada", "falhou", "cancelada"):
            visitas.setdefault(a["lead_id"], []).append(a)
    for l in d["leads"]:
        if l["criado"] < corte:
            continue
        m = out[origem(l)]
        m["leads"] += 1
        hist, minhas = l["historico"], visitas.get(l["id"], [])
        aquecido = any(a["estado"] == "executada" for a in minhas)
        descarte = next((h for h in hist if h["tipo"] == "etapa:descartado"), None)
        if aquecido:
            m["aquecidos"] += 1
        elif descarte and minhas:
            m["descartados_visita"] += 1
            motivo = _motivo_descarte(descarte.get("texto", ""))
            m["motivos"][motivo] = m["motivos"].get(motivo, 0) + 1
        if aquecido or (descarte and minhas):
            m["visitados"] += 1
        if any(h["tipo"] == "dm_abertura" for h in hist):
            m["abordados"] += 1
        if l["etapa"] in ("respondeu", "lead", "demo", "teste", "cliente") or any(h["tipo"] == "etapa:respondeu" for h in hist):
            m["responderam"] += 1
    for m in out.values():
        m["descarte_pct"] = round(100 * m["descartados_visita"] / m["visitados"]) if m["visitados"] else None
    return out


def linha_fontes(login: str, dias: int = 28) -> str:
    """One line per source for people: «planilha: 77 leads, 15 visitados (73% descartados: parado 6…), 0 respostas»."""
    linhas = []
    for o, m in metricas_fontes(login, dias).items():
        if not m["leads"]:
            continue
        desc = ""
        if m["descartados_visita"]:
            desc = (f" ({m['descarte_pct']}% descartados na visita: "
                    + ", ".join(f"{k} {v}" for k, v in sorted(m["motivos"].items(), key=lambda x: -x[1])) + ")")
        elif m["visitados"]:
            desc = " (nenhum descartado na visita)"
        linhas.append(f"{o}: {m['leads']} leads, {m['visitados']} visitados{desc}, {m['aquecidos']} aquecidos, "
                      f"{m['abordados']} abordados, {m['responderam']} responderam")
    return "\n".join(linhas)


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


def _agradeceu(texto: str) -> bool:
    """A short thanks after the link ("obrigada!", "valeu, vou testar") is not a reply that ends the follow-up."""
    t = str(texto or "")
    citado = _citacao(t)
    return (len(citado) <= 60 and bool(re.search(r"\b(obrigad|brigad|valeu|vou (testar|ver|olhar|dar uma olhada)|show|top|"
                                                  r"massa|beleza|blz)", citado))) or t.lower().startswith("agradeceu")


def motivo_seguimento(d: dict, lead: dict) -> str:
    """'' or why one follow-up is due now (blind reviews 2-4): "link" — DIAS_SEGUIMENTO days after the calculator link,
    with no word since but thanks; "agora_nao" — RETORNO_AGORA_NAO days after "agora não", once; "vai_passar" —
    DIAS_VAI_PASSAR days after "vou passar pro dono", once."""
    if lead["etapa"] not in ("respondeu", "lead") or lead.get("humano") or lead["canal"] != "instagram":
        return ""
    acoes = [a for a in d["acoes"] if a["lead_id"] == lead["id"]]
    seguimentos = [float(a.get("criada") or 0) for a in acoes if a["tipo"] == "seguimento"
                   and a["estado"] in ("proposta", "aprovada", "incerta", "executada")]
    falas = [h for h in lead["historico"] if h["tipo"] in {f"etapa:{e}" for e in RESPOSTAS_ETAPAS}]
    ultima = falas[-1] if falas else None
    for rx, prazo, motivo in ((AGORA_NAO, RETORNO_AGORA_NAO, "agora_nao"), (VAI_PASSAR, DIAS_VAI_PASSAR, "vai_passar")):
        if ultima and rx.search(str(ultima.get("texto") or "")):
            if any(c >= ultima["em"] for c in seguimentos):
                return ""
            return motivo if _dias_desde(ultima["em"]) >= prazo else ""
    if seguimentos:
        return ""
    links = [a.get("executada_em") or 0 for a in acoes if a["estado"] == "executada" and a["tipo"] in ("resposta", "dm_lembrete")
             and CALCULADORA.search(a.get("texto") or "")]
    if not links:
        return ""
    if any(h["em"] > max(links) and not _agradeceu(h.get("texto")) for h in falas):
        return ""  # the person wrote after the link: that is a reply, not a follow-up
    return "link" if _dias_desde(max(links)) >= DIAS_SEGUIMENTO else ""


MOTIVOS_SEGUIMENTO = {"link": "2 dias depois do link, sem resposta (playbook › Modelos › Seguimento)",
                      "agora_nao": "30 dias depois do «agora não»: um retorno leve, sem link",
                      "vai_passar": "2 dias depois de «vou passar pro dono»: pergunte se conseguiu falar"}


def marcar_links(texto: str, d: dict, lid: str) -> str:
    """Matheus, 12/10: the calculator link carries the variant of the first message (?o=ig-a / ig-b), so the Raiz site
    can tell which opening leads to the calculator and to the trial. Short on purpose (a long UTM looked huge)."""
    var = next((str(a.get("variante") or "").lower() for a in reversed(d["acoes"])
                if a["lead_id"] == lid and a["tipo"] == "dm_abertura" and a.get("variante") in ("A", "B")), "x")
    return CALCULADORA.sub(lambda m: m.group(0) if m.group(4) else m.group(0) + f"?o=ig-{var}", texto)


def avisar_agora(etapa: str, nota: str = "") -> bool:
    """Matheus, 12/10: the phone rings right away only for lead, demo and what waits on him ("pendente:"); a plain
    answer ("oi", a heart) goes to the 20h17 summary."""
    return etapa in ("lead", "demo") or str(nota or "").strip().lower().startswith("pendente:")


def _seguimento_devido(d: dict, lead: dict) -> bool:
    return bool(motivo_seguimento(d, lead))


def variante_sugerida(d: dict, lead: dict) -> str:
    """The first message's variant for this lead: the fixed one, else A or B by the lead's id (half and half, and the
    agent never picks — it would put B on the "best" profiles and bias the comparison)."""
    fixa = d["config"].get("variante_fixa")
    if fixa in ("A", "B"):
        return fixa
    return "A" if int(hashlib.sha256(str(lead.get("id")).encode()).hexdigest(), 16) % 2 == 0 else "B"


def _pascoa(ano: int) -> dt.date:
    """Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d_, e, f = b // 4, b % 4, (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d_ - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    return dt.date(ano, (h + l - 7 * m + 114) // 31, ((h + l - 7 * m + 114) % 31) + 1)


def data_de_pico(segmento: str, dia: dt.date | None = None) -> str:
    """'' or the selling date that keeps confeitarias and doces busiest (the 14 days before it, or December): no first
    message for them then (blind reviews 4 and 5 — the tool filters, the agent does not compute Easter)."""
    if segmento_rubrica(segmento) not in ("confeitaria", "doces"):
        return ""
    dia = dia or dt.datetime.fromtimestamp(agora(), _tz()).date()
    if dia.month == 12:
        return "dezembro (Natal)"
    maio = dt.date(dia.year, 5, 1)
    datas = [(_pascoa(dia.year), "Páscoa"), (maio + dt.timedelta(days=(6 - maio.weekday()) % 7 + 7), "Dia das Mães"),
             (dt.date(dia.year, 6, 12), "Dia dos Namorados"), (dt.date(dia.year, 9, 27), "Cosme e Damião"),
             (dt.date(dia.year, 10, 12), "Dia das Crianças")]
    return next((nome for data, nome in datas if 0 <= (data - dia).days <= 14), "")


def devidos(login: str) -> dict:
    """What each lead needs next, by the playbook's timing."""
    d = carregar(login)
    pendentes = {a["lead_id"] for a in d["acoes"] if a["estado"] in ("proposta", "aprovada", "incerta")}
    out = {"dm_abertura": [], "dm_lembrete": [], "seguimento": [], "aquecer": []}
    for l in d["leads"]:
        if l["id"] in pendentes or l["canal"] != "instagram":
            continue
        dias = _dias_desde(l["atualizado"])
        if l["etapa"] == "novo":
            out["aquecer"].append(l)
        elif l["etapa"] == "aquecido" and dias >= (1 if l.get("interagiu") else DIAS_DM):
            if not data_de_pico(l.get("segmento", "")):  # their busiest weeks: the first message waits
                out["dm_abertura"].append(l)  # who answered our comment or followed back: next day, still fresh
        elif l["etapa"] == "abordado" and dias >= DIAS_LEMBRETE and l.get("interagiu"):
            out["dm_lembrete"].append(l)  # the others' first message sits in "requests": no second one (blind review)
        elif _seguimento_devido(d, l):
            out["seguimento"].append(l)
    for lista in out.values():  # who engaged back first, then best fit: the day's slots are limited
        lista.sort(key=lambda l: (not l.get("interagiu"), -(l.get("nota") if l.get("nota") is not None else 60)))
    return out


# ------------------------------------------------------------------ actions

LIMITE_PILOTO = {"aquecer": 15, "dm_abertura": 5, "dm_lembrete": 5, "resposta": 15, "parceiro": 3,  # aquecer 8 → 15: Matheus, 12/10
                 "seguimento": 5}


def bloqueio_recente(d: dict) -> bool:
    """A block or verification in the last 7 days (the account comes back at half pace, not at 100%)."""
    return any(agora() - float(b.get("em") or 0) < 7 * 86400 for b in d.get("bloqueios") or [])


def limites(d: dict) -> dict:
    """Daily limits: the config's, else the pilot's for the first 7 days, else the playbook's — with the first messages
    going up a step a week (RAMPA_DM; 12/10 blind review: 5 to 12 overnight on day 8). For 7 days after a block,
    everything but the replies runs at half (blind review 3: back to 100% right after the 48 h pause is a robot sign)."""
    if d["config"].get("limites"):
        base = {**LIMITE_DIA, **d["config"]["limites"]}
    else:
        inicio = d["config"].get("inicio") or (min([l["criado"] for l in d["leads"]] or [agora()]))
        semana = int(max(0, agora() - inicio) // (7 * 86400))
        base = dict(LIMITE_PILOTO) if semana == 0 else {**LIMITE_DIA, "dm_abertura": RAMPA_DM[min(semana, len(RAMPA_DM) - 1)]}
    if bloqueio_recente(d):
        base = {k: (v if k == "resposta" else max(1, v // 2)) for k, v in base.items()}
    return base


def _usadas_hoje(d: dict, tipo: str) -> int:
    hoje = _hoje_local()
    return sum(1 for a in d["acoes"] if a["tipo"] == tipo and a["estado"] in ("proposta", "aprovada", "executada")
               and _hoje_local(a.get("executada_em") or a.get("decidida") or a["criada"]) == hoje)


def cotas(login: str) -> dict:
    d = carregar(login)
    lim = limites(d)
    return {t: max(0, lim[t] - _usadas_hoje(d, t)) for t in TIPOS}


# 12/10 review ("revisor estável"): what is objective is checked here, not left to the model. The playbook forbids
# asking for the person's recipe ("me manda a receita que eu calculo" sounds invasive); a reply to someone who offers
# it is left to the reviewer.
PEDE_RECEITA = re.compile(r"\b(mand\w*|envi[ae]\w*|compartilh\w*|pass(a|e|ar|em|arem))\b[^.!?\n]{0,20}"
                          r"\b(receita|ficha t[eé]cnica)", re.I)


def validar_texto(tipo: str, texto: str, d: dict, lid: str) -> str:
    """'' when the text may be proposed, else why not (playbook rules a model could slip on)."""
    t = (texto or "").strip()
    if tipo == "aquecer":
        if t and (len(t) > 220 or LINK.search(t) or re.search(r"raiz", t, re.I)):
            return "comentário de aquecimento: até 220 caracteres, sem link e sem citar a Raiz"
        return ""
    if len(t) < (15 if tipo == "resposta" else 40):  # a reply may be short ("Obrigado! Fico no aguardo por aqui.")
        return "mensagem curta demais para ser específica"
    if len(t) > 900:
        return "mensagem longa demais para uma DM (até 900 caracteres)"
    sem_calculadora = CADASTRO.sub("", CALCULADORA.sub("", t))
    if LINK.search(sem_calculadora) or (tipo not in TIPOS_COM_LINK and (CALCULADORA.search(t) or CADASTRO.search(t))):
        if tipo in TIPOS_COM_LINK:
            return (f"link só o da calculadora ({LINK_CALCULADORA}), o do simulador de delivery ({LINK_DELIVERY}) ou o do "
                    f"cadastro do teste ({LINK_CADASTRO}), e só na resposta a quem escreveu")
        if tipo == "dm_lembrete":
            return "lembrete sem link: ofereça mandar (\"quer que eu te mande o link aqui?\")"
        return "sem link na primeira mensagem, no seguimento nem em mensagem a parceiro"
    lead = _lead(d, lid) or {}
    if tipo == "resposta" and CADASTRO.search(t):
        if lead.get("etapa") == "descartado":
            return "quem disse não recebe só um obrigado curto: sem link"
        if any(a["lead_id"] == lead.get("id") and a["estado"] == "executada" and CADASTRO.search(a.get("texto") or "")
               for a in d["acoes"]):
            return "a pessoa já recebeu o link do cadastro: não repita; pergunte se conseguiu entrar"
    if tipo == "resposta" and CALCULADORA.search(t):
        if lead.get("etapa") == "descartado":
            return "quem disse não recebe só um obrigado curto: sem link e sem pergunta"
        enviados = sum(1 for a in d["acoes"] if a["lead_id"] == lead.get("id") and a["estado"] == "executada"
                       and CALCULADORA.search(a.get("texto") or ""))
        falas = [h for h in lead.get("historico", []) if str(h.get("tipo", "")).startswith("etapa:")]
        pediu = bool(falas) and bool(PEDIU_LINK.search(str(falas[-1].get("texto") or "")))
        if enviados and not (enviados == 1 and pediu):
            return "a pessoa já recebeu o link: não repita; pergunte se conseguiu abrir ou se ficou alguma dúvida"
    if tipo != "resposta" and PROIBIDAS.search(t):
        return f"palavra fora do tom do playbook: «{PROIBIDAS.search(t).group(0)}»"
    if tipo != "resposta" and PEDE_RECEITA.search(t):
        return "não peça a receita (o playbook proíbe: soa invasivo); ofereça a conta de graça ou a calculadora"
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
    """Validate and store proposed actions. Returns {"propostas": [...acoes], "recusadas": [{...,"motivo"}]}. The
    pre-approval's reviewer runs after the proposals are saved and outside the lock."""
    d, out = _propor_gravar(login, itens)
    if d["config"].get("auto"):
        out = _auto_aprovar(login, out)
    return out


@_transacao
def _propor_gravar(login: str, itens: list) -> tuple[dict, dict]:
    d = carregar(login)
    out = {"propostas": [], "recusadas": []}
    restantes = cotas(login)
    ja = {(a["lead_id"], a["tipo"]) for a in d["acoes"] if a["estado"] in ("proposta", "aprovada", "incerta")}
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
        elif lead.get("humano"):
            motivo = ("o Matheus está conversando com esse perfil pessoalmente: não proponha nada (ele devolve quando "
                      "quiser, e aí `prospeccao` acao \"devolver\")")
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
        elif tipo == "dm_lembrete" and not lead.get("interagiu"):
            motivo = ("lembrete só para quem segue a Raiz ou interagiu com ela (para os outros a 1ª mensagem está em "
                      "Solicitações): deixe fechar sem resposta")
        elif tipo == "seguimento" and not _seguimento_devido(d, lead):
            motivo = (f"seguimento só uma vez, {DIAS_SEGUIMENTO} dias depois de mandarmos o link, e só se a pessoa não "
                      "escreveu mais")
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
        fixa = d["config"].get("variante_fixa")
        if tipo == "dm_abertura" and fixa in ("A", "B") and variante in ("A", "B") and variante != fixa:
            out["recusadas"].append({**item, "motivo": f"a variante {fixa} foi fixada pelos números: escreva no modelo {fixa}"})
            continue
        if tipo == "dm_abertura" and fixa in ("A", "B"):
            variante = fixa
        elif tipo == "dm_abertura" and variante not in ("A", "B"):
            variante = variante_sugerida(d, lead)
        if tipo in TIPOS_COM_LINK:
            texto = marcar_links(texto, d, lid)
        acao = {"id": _id(), "lead_id": lid, "tipo": tipo, "texto": texto[:900], "variante": variante,
                "alvo": str(item.get("alvo") or lead["url"])[:200], "base": str(item.get("base") or "")[:300],
                "estado": "proposta", "criada": agora()}
        d["acoes"].append(acao)
        _evento(d, acao, "-", "proposta", "proposta criada")
        ja.add((lid, tipo))
        restantes[tipo] -= 1
        out["propostas"].append(acao)
    salvar(login, d)
    return d, out


# ------------------------------------------------------------------ pre-approved within the daily limits

AUTO_TIPOS = ("aquecer", "dm_abertura", "dm_lembrete", "resposta", "parceiro", "seguimento")
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
   dados também é. Dizer que o Matheus está na cidade do lead ("aqui em {cidade}") quando ela não é Salvador, ou que
   ele também produz comida, é fato inventado (para lead de Salvador, "também sou de Salvador" é verdade). Sobre a
   Raiz (função, integração, plano, preço, prazo), só vale o que está no playbook ou o que o agente diz que o Matheus
   ditou para aquela conversa ("o Matheus disse: …"): o resto é fato inventado. O detalhe do post ou do perfil citado na mensagem ou no comentário tem
   de aparecer no trecho que o agente copiou (legenda, texto na arte, preço, bio, cardápio); a descrição automática do
   Instagram ("Pode ser uma imagem de…") não é fato: reprove o que só se apoia nela.
2. Fere o playbook: comentário de aquecimento que vende, cita a Raiz, um sistema, chama para o direct ou faz pergunta
   (o comentário é uma observação, sem pergunta: a conta não volta ao comentário para continuar a conversa); jargão (ERP, sistema de gestão, CMV, solução) na
   abertura; promessa de resultado ou número inventado; pressão; link fora do lugar (os únicos links permitidos são a
   calculadora de precificação, o simulador de delivery e o cadastro do teste da Raiz, e só na resposta a quem escreveu: primeira
   mensagem, lembrete e seguimento vão sem link); repetir o link a quem já recebeu; oferta ou link para quem disse
   não ("agora não", "sem tempo" e "depois vejo" não são não: o playbook manda deixar o link); primeira mensagem sem
   a assinatura do Matheus. A primeira mensagem pode ser só uma pergunta sobre como a
   pessoa precifica (variante A) ou já trazer a oferta da calculadora grátis pedindo licença para mandar o link
   (variante B): as duas são válidas. Pedir a receita da pessoa ("me manda a receita", ficha técnica) fere o
   playbook: soa invasivo.
3. Soa como spam, intimidade forçada ou constrange a pessoa.
4. Tem erro de português ou abreviação de internet que faça a marca parecer descuidada.
5. Numa resposta: não combina com O QUE A PESSOA DISSE (ignora a pergunta dela, insiste depois de um não, ou finge
   uma conversa que não houve). Perguntou se é robô: a resposta não pode negar que há um assistente.
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


# ------------------------------------------------------------------ action ledger (plugins/central; 12/10 review §4.1)
# Every executed, failed or deleted action also goes to the append-only ledger, where the Conferência checks it (e.g. the
# same DM to the same person twice). The ledger is optional and never stops the work: no plugin, no record.
LIVRO = Path("/a0/usr/plugins/central/helpers/livro.py")
VERBO_LIVRO = {"aquecer": "seguir_curtir", "dm_abertura": "dm", "dm_lembrete": "dm", "resposta": "dm", "parceiro": "dm",
               "seguimento": "dm"}
LIVRO_MODULO = None  # tests put a stand-in here


def _livro():
    import importlib.util
    import sys

    if LIVRO_MODULO is not None:
        return LIVRO_MODULO
    if not LIVRO.exists():
        return None
    antigo = sys.modules.get("central_livro")
    mtime = LIVRO.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location("central_livro", LIVRO)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules["central_livro"] = modulo
    return sys.modules["central_livro"]


def registro_livro(a: dict, lead: dict | None, fase: str, detalhe: str = "", comentario: bool = False) -> dict:
    """The ledger fields of one prospecting action (what, to whom, which text, which key)."""
    if comentario:
        verbo, conteudo, chave = "comentario", (a.get("comentario") or {}).get("texto", ""), f"prosp:{a['id']}:comentario"
    else:
        verbo, conteudo, chave = VERBO_LIVRO.get(a["tipo"], a["tipo"]), a.get("texto", ""), f"prosp:{a['id']}"
    return {"fase": fase, "origem": "prospeccao", "ferramenta": "instagram", "verbo": verbo,
            "alvo": f"instagram:@{(lead or {}).get('handle') or '?'}", "conteudo": conteudo, "chave": chave,
            "resultado": str(detalhe or "")[:300], "evidencia": {"tipo": a["tipo"], "lead": a.get("lead_id")}}


def _anotar(login: str, a: dict, lead: dict | None, fase: str, detalhe: str = "", comentario: bool = False,
            ctx_id: str = "") -> None:
    try:
        livro = _livro()
        if livro:
            livro.registrar(login=login, ator=AUTOR["quem"], ctx_id=ctx_id,
                            **registro_livro(a, lead, fase, detalhe, comentario))
    except Exception as exc:  # pragma: no cover - the ledger never stops the round
        print(f"prospeccao: livro não registrou {a.get('id')}: {exc}", flush=True)


@_transacao
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
    _anotar(login, a, lead, "cancelada", f"apagada no Instagram: {detalhe}")
    return a


def _disse(lead: dict) -> str:
    """What the person said last (the note of the latest etapa:respondeu/lead/descartado), for the reviewer."""
    falas = [h for h in lead.get("historico", []) if str(h.get("tipo", "")).startswith("etapa:")]
    return (falas[-1]["texto"][:300] + f" (em {falas[-1].get('onde', 'direct')})") if falas else "(não registrado)"


VEREDITOS_DIAS = 30


def _arq_vereditos(login: str) -> Path:
    return PASTA / f"{_login(login)}_vereditos.json"


def _ler_vereditos(login: str) -> dict:
    try:
        return json.loads(_arq_vereditos(login).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar_vereditos(login: str, novos: dict) -> None:
    """The reviewer's verdicts by hash of exactly what it saw (12/10 review: the same text was approved and later
    held). A cache: losing it only means asking again."""
    if not novos:
        return
    with _exclusivo(login):
        dados = {**_ler_vereditos(login), **novos}
        corte = agora() - VEREDITOS_DIAS * 86400
        dados = dict(sorted(((k, v) for k, v in dados.items() if v.get("em", 0) >= corte), key=lambda kv: kv[1]["em"])[-1000:])
        PASTA.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=PASTA, prefix=f".{_login(login)}_vereditos.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False)
            os.replace(tmp, _arq_vereditos(login))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def revisar_textos(d: dict, acoes: list, login: str = "") -> dict:
    """{id: {"aprovado": bool, "motivo": str}} from a fresh model against the playbook. Fails closed: when the
    reviewer is unreachable or unclear, nothing is approved here (it goes to the person). With `login`, an item the
    reviewer already judged with exactly the same data and text gets the same verdict, without asking again."""
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
    regras = REVISOR + "\n\n# PLAYBOOK\n" + (playbook.read_text(encoding="utf-8")[:20000] if playbook.exists() else "")
    guardados = _ler_vereditos(login) if login else {}
    chaves = {a["id"]: hashlib.sha256(f"{regras}\n{a['tipo']}\n{b.split(chr(10), 1)[1]}".encode()).hexdigest()[:32]
              for a, b in zip(acoes, blocos)}  # the item's id stays out: the same text for the same lead is the same item
    prontos = {a["id"]: {"aprovado": guardados[chaves[a["id"]]]["aprovado"], "motivo": guardados[chaves[a["id"]]]["motivo"]}
               for a in acoes if chaves[a["id"]] in guardados}
    faltam = [(a, b) for a, b in zip(acoes, blocos) if a["id"] not in prontos]
    if not faltam:
        return prontos
    pedido = regras + "\n\n# ITENS\n" + "\n\n".join(b for _, b in faltam)
    try:
        saida = _chamar_revisor(pedido)
        achado = re.search(r"\{.*\}", saida or "", re.S)
        res = json.loads(achado.group(0), strict=False) if achado else {}
    except Exception as exc:
        return {**prontos, **{a["id"]: {"aprovado": False, "motivo": f"revisor indisponível ({str(exc)[:80]})"}
                              for a, _ in faltam}}
    vistos = {str(i.get("id")): i for i in (res.get("itens") or []) if isinstance(i, dict)}
    novos = {a["id"]: {"aprovado": vistos.get(a["id"], {}).get("aprovado") is True,
                       "motivo": str(vistos.get(a["id"], {}).get("motivo") or "revisor não respondeu sobre este item")[:200]}
             for a, _ in faltam}
    if login:  # only what the reviewer really judged is kept
        _guardar_vereditos(login, {chaves[i]: {**v, "em": agora()} for i, v in novos.items() if i in vistos})
    return {**prontos, **novos}


def _auto_aprovar(login: str, out: dict) -> dict:
    """Pre-approved types: follow/like with no text pass straight; any text passes the reviewer first. Whatever the
    reviewer does not pass stays a proposal for the person. out gains "automaticas"; "propostas" keeps only the manual."""
    d = carregar(login)  # a snapshot for the reviewer, who may take minutes: nothing is saved from it
    candidatas = [a for a in out["propostas"] if a["tipo"] in AUTO_TIPOS]
    com_texto = [a for a in candidatas if a["texto"]]
    vereditos = revisar_textos(d, com_texto, login) if com_texto else {}
    # the reviewer claimed something is missing that a plain rule shows is there (11/10: it held a reply "for not
    # introducing Matheus nor linking the calculator" — the text did both): ask once more, pointing at the fact
    contraditos = [a for a in com_texto if not vereditos.get(a["id"], {}).get("aprovado") and _contradiz(a, vereditos[a["id"]]["motivo"])]
    if contraditos:
        for a in contraditos:
            a = {**a, "base": (a.get("base") or "") + f" | CONFERIDO POR REGRA, NÃO PELO MODELO: {_fatos(a)}. "
                 f"Uma revisão anterior disse: «{vereditos[a['id']]['motivo']}» — isso contradiz o texto; reveja só pelo resto."}
            segunda = revisar_textos(d, [a], login).get(a["id"], {})
            vereditos[a["id"]] = {"aprovado": segunda.get("aprovado") is True,
                                  "motivo": f"2ª revisão: {segunda.get('motivo', '')} (a 1ª errou: {vereditos[a['id']]['motivo'][:80]})"[:200]}
    with _exclusivo(login):
        return _aplicar_vereditos(login, out, candidatas, vereditos)


def _aplicar_vereditos(login: str, out: dict, candidatas: list, vereditos: dict) -> dict:
    d = carregar(login)  # the current state, under the lock: what other rounds saved meanwhile is kept
    automaticas, manuais = [], [a for a in out["propostas"] if a["tipo"] not in AUTO_TIPOS]
    recusadas = list(out.get("recusadas", []))
    sem_aprovacao = d["config"].get("sem_aprovacao", True)
    for a in candidatas:
        v = vereditos.get(a["id"], {"aprovado": True, "motivo": "seguir e curtir, sem texto"})
        guardada = next((x for x in d["acoes"] if x["id"] == a["id"]), None)
        if not guardada or guardada["estado"] != "proposta":
            continue  # decided or cancelled meanwhile: leave it as it is
        guardada["revisao"] = v["motivo"]
        if v["aprovado"]:
            _mudar(d, guardada, "aprovada", f"revisor: {v['motivo']}", decidida=agora(), auto=True)
            automaticas.append(guardada)
        elif sem_aprovacao and _revisor_fora(v["motivo"]):
            # the reviewer was down or gave no verdict: not a rejection of the text, so it does not use up a version
            _mudar(d, guardada, "pulada", f"revisor fora do ar: {v['motivo']}", decidida=agora())
            recusadas.append({"lead_id": guardada["lead_id"], "tipo": guardada["tipo"],
                              "motivo": f"o revisor está fora do ar agora ({v['motivo'][:80]}): proponha de novo na próxima rodada, sem mudar o texto"})
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


def _revisor_fora(motivo: str) -> bool:
    return bool(re.match(r"(revisor indispon[ií]vel|revisor n[aã]o respondeu)", motivo or "", re.I))


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


AB_MINIMO = 100      # first messages per variant before the numbers decide (12/10 blind review: 30 was noise)
AB_DIFERENCA = 5.0   # points of answer rate that make one variant the better one


def sugestao_ab(por_variante: dict) -> str:
    """What the weekly report proposes about A × B, from the numbers only ('' while there are too few)."""
    a, b = por_variante.get("A") or {}, por_variante.get("B") or {}
    if min(a.get("abordados", 0), b.get("abordados", 0)) < AB_MINIMO:
        return ""
    ta, tb = a["taxa_resposta"], b["taxa_resposta"]
    if abs(ta - tb) < AB_DIFERENCA:
        return f"A e B respondem parecido ({ta}% × {tb}%, {a['abordados']} e {b['abordados']} abordagens): manter as duas."
    melhor, pior = ("A", "B") if ta > tb else ("B", "A")
    m, p = por_variante[melhor], por_variante[pior]
    return (f"A variante {melhor} responde mais ({m['taxa_resposta']}% × {p['taxa_resposta']}%, {m['abordados']} e "
            f"{p['abordados']} abordagens): proponho usar só a {melhor}.")


@_transacao
def definir_variante(login: str, variante: str) -> str:
    """Fix the first-message variant ("A" or "B") after the person agrees with the numbers; "" goes back to
    alternating. Returns what is in force."""
    v = str(variante or "").strip().upper()[:1]
    d = carregar(login)
    if v in ("A", "B"):
        d["config"]["variante_fixa"] = v
    else:
        d["config"].pop("variante_fixa", None)
        v = ""
    salvar(login, d)
    return v


@_transacao
def definir_auto(login: str, ligado: bool) -> None:
    d = carregar(login)
    d["config"]["auto"] = bool(ligado)
    salvar(login, d)


@_transacao
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


@_transacao
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


@_transacao
def definir_conta(login: str, handle: str) -> str:
    h = normalizar(handle)
    if not h or h in CONTAS_PROIBIDAS:
        return "conta inválida para prospecção"
    d = carregar(login)
    d["config"]["conta_instagram"] = h
    salvar(login, d)
    return ""


CONFERENCIA_VALE = 40 * 60  # an execution round must have read the Direct and the notifications this recently
COMANDO_ESPERA = "for i in $(seq 18); do sleep 10; echo $i; done"  # prints every 10 s: the terminal tool gives up after 15 s of silence (max 240 s)
VARREDURA_H = 4  # 12/10 blind review, item 2: every conversation opened one by one ~3x a day (9h-19h), not every round


def _interagiu_hoje(lead: dict) -> bool:
    quando = float(lead.get("interagiu") or 0)
    return quando > 86400 and _hoje_local(quando) == _hoje_local()


def varredura_devida(d: dict) -> bool:
    return agora() - float(d.get("varredura_em") or 0) >= VARREDURA_H * 3600


@_transacao
def conferido(login: str, direct: str, notificacoes: str, interagiram: list | None = None, varredura: bool = False) -> str:
    """The round says what it read in the Direct and in the notifications (answers are looked for before acting).
    '' when recorded, else why not: the notifications text must be what is on the page, not a one-word claim."""
    direct, notificacoes = (direct or "").strip(), (notificacoes or "").strip()
    if len(direct) < 8 or len(notificacoes) < 25:
        return ("leia de verdade: em `direct`, quantas conversas têm mensagem nova e de quem; em `notificacoes`, copie "
                "as primeiras linhas que aparecem na página de notificações")
    d = carregar(login)
    d["conferencia"] = {"em": agora(), "direct": direct[:500], "notificacoes": notificacoes[:800]}
    if varredura:
        d["varredura_em"] = agora()
    for h in interagiram or []:  # followed back / liked / commented: warmer, goes first for the next message
        lead = next((l for l in d["leads"] if l["handle"] == normalizar(str(h))), None)
        if lead and not lead.get("interagiu"):
            lead["interagiu"] = agora()
            lead["historico"].append({"em": agora(), "tipo": "interagiu", "texto": "seguiu de volta / curtiu / comentou"})
    salvar(login, d)
    return ""


RESERVA = 20 * 60  # an action handed out to a round is that round's; with no result in this time it becomes "incerta"


def _livre(a: dict, quem: str) -> bool:
    """Not reserved by another round (or the reservation ran out)."""
    return (not a.get("em_execucao") or agora() - a["em_execucao"] > RESERVA
            or a.get("reservada_por", "") in ("", quem))


@_transacao
def proxima(login: str, conta_ativa: str = "", repor: bool = True, quem: str = "") -> tuple[dict | None, str]:
    """Next approved action that may run now (right account, hours, pause, spacing, daily limits). The action is
    reserved for the round that asked (`quem`): another round never gets it (12/10 review: two rounds could send the
    same DM). One handed out and never reported may have gone out (the round fell after sending): it becomes
    "incerta" and comes back first as a check on the screen, never as a resend."""
    d = carregar(login)
    esperada, ativa = conta(login), normalizar(conta_ativa)
    if not esperada:
        return None, "a conta de Instagram da prospecção não está configurada: nada é executado"
    if ativa in CONTAS_PROIBIDAS:
        return None, f"a conta ativa é @{ativa} (pessoal): não troque nem execute nada; termine com PRECISA DE VOCÊ (skill, seção 1)"
    if ativa != esperada:
        return None, (f"confirme a conta ATIVA no Instagram (skill, seção 1) e chame `proxima` com conta_ativa; tem que "
                      f"ser @{esperada}")
    if d["config"].get("exigir_conferencia") and agora() - (d.get("conferencia") or {}).get("em", 0) > CONFERENCIA_VALE:
        return None, ("antes de executar, confira as respostas: leia o Direct e a página de notificações e chame "
                      "`prospeccao` acao \"caixa_lida\" com o que viu em cada um")
    if modo_teste(login) and not d["config"].get("executar_em_teste"):
        return None, "modo teste: nada é executado"
    if agora() < d["bloqueio_ate"]:
        return None, "pausado após bloqueio do Instagram até " + dt.datetime.fromtimestamp(d["bloqueio_ate"], _tz()).strftime("%d/%m %H:%M")
    h = _hora_local()
    hm = dt.datetime.fromtimestamp(agora(), _tz()).strftime("%H:%M")
    so_respostas = ""
    if not HORARIO[0] <= h < HORARIO[1]:
        if not (HORARIO[1] <= h and hm < RESPOSTA_ATE):
            return None, f"fora do horário ({HORARIO[0]}h–{HORARIO[1]}h; respostas até {RESPOSTA_ATE})"
        so_respostas = f"depois das {HORARIO[1]}h só respostas a quem escreveu"
    elif dt.datetime.fromtimestamp(agora(), _tz()).weekday() == int(d["config"].get("folga", FOLGA)):
        so_respostas = "dia de folga da conta: só respostas a quem escreveu"
    for x in d["acoes"]:
        if x["estado"] == "aprovada" and x.get("em_execucao") and agora() - x["em_execucao"] > RESERVA:
            _mudar(d, x, "incerta", "entregue a uma rodada e sem resultado: conferir na tela antes de qualquer reenvio")
    incerta = next((x for x in d["acoes"] if x["estado"] == "incerta" and _livre(x, quem)), None)
    if incerta:
        incerta["em_execucao"], incerta["reservada_por"] = agora(), quem
        salvar(login, d)
        return {**incerta, "lead": _lead(d, incerta["lead_id"]) or {}, "conferir": True}, ""
    if so_respostas or agora() < float(d["config"].get("api_pausa_ate") or 0):
        repor = False  # no new warm-up now (rest day, evening, or the account's queries are limited)
    if repor and not any(x["estado"] == "aprovada" for x in d["acoes"]) and not _fila_repor(login):
        # nothing to do at all: say so now, not "wait for the spacing" (11/10 17h20: the round waited on nothing)
        return None, "nenhuma ação aprovada esperando"
    ultima = _ultima_acao(d)  # a catch-up comment also counts for the spacing
    if ultima and agora() - ultima < _espera(ultima):
        return None, f"espaçamento: próxima a partir de {dt.datetime.fromtimestamp(ultima + _espera(ultima), _tz()).strftime('%H:%M')}"
    pico = False
    # replies go first (someone is waiting), then the rest in approval order
    for a in sorted((x for x in d["acoes"] if x["estado"] == "aprovada"), key=lambda x: (x["tipo"] != "resposta", x.get("decidida", 0))):
        lead = _lead(d, a["lead_id"])
        if not lead or (lead["etapa"] in FINAIS and not (a["tipo"] == "resposta" and lead["etapa"] == "descartado")):
            _mudar(d, a, "cancelada", "lead encerrado antes da execução")
            continue
        if lead.get("humano") and not a.get("em_execucao"):
            _mudar(d, a, "cancelada", "o Matheus assumiu a conversa com esse perfil")
            continue
        if not _livre(a, quem):
            continue  # another round has it
        if a["tipo"] in FORA_DO_PICO and _no_pico(segmento=lead.get("segmento", "")):
            pico = max(pico or "", _janela_pico(lead.get("segmento", ""))[1])
            continue  # stays approved for after the peak
        if so_respostas and a["tipo"] != "resposta":
            continue  # stays approved for the next working hours
        if a["tipo"] == "aquecer" and agora() < float(d["config"].get("api_pausa_ate") or 0):
            continue  # 429 on our account: no follow/like until the next day (blind review 2, item 3)
        executadas_hoje = sum(1 for x in d["acoes"] if x["tipo"] == a["tipo"] and x["estado"] == "executada"
                              and _hoje_local(x.get("executada_em")) == _hoje_local())
        if executadas_hoje >= limites(d)[a["tipo"]]:
            continue
        a["em_execucao"], a["reservada_por"] = agora(), quem
        salvar(login, d)
        return {**a, "lead": lead}, ""
    salvar(login, d)
    if repor and repor_aquecer(login):
        return proxima(login, conta_ativa, repor=False, quem=quem)
    if pico:
        return None, (f"primeiras mensagens, lembretes e seguimentos esperam o fim do pico de produção ({pico}); "
                      "nada mais agora")
    if so_respostas:
        return None, f"{so_respostas}; nada mais agora"
    return None, "nenhuma ação aprovada esperando"


# ------------------------------------------------------------------ comment written during the visit
# 11/10: warm-ups from the sources and the automatic refill go with no text (nobody had seen the posts), so the 8
# warm-ups of the day had no comment. Now, on the visit, the agent reads the latest post and may write one; the
# reviewer checks it; only an approved comment is published. Also for warm-ups done in the last days (catch-up).
DIAS_COMENTARIO = 3
TENTATIVAS_COMENTARIO = 2  # the reviewer said no twice: no comment, just follow and like (12/10 blind review, item 3)


def pode_comentar(lead: dict) -> bool:
    """Blind review 5, item 4: a public comment from a software brand is the exception — hot leads only."""
    return (lead.get("nota") or 0) >= NOTA_QUENTE


LIMITE_COMENTARIOS = 10  # a day (blind review 3: public, and among the actions Instagram blocks most); half after a block
POST_COMENTARIO_DIAS = 7  # blind review 2, item 5: a comment on a post weeks old looks like digging and is rarely answered
_MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}


def idade_post(base: str) -> int | None:
    """Days since the post the agent cites in `base`: AAAA-MM-DD, DD/MM[/AAAA], "N de outubro", "ontem", "hoje",
    "há N dias/semanas", "N d", "N sem", "N h". None when it names no date."""
    t = str(base or "").lower()
    hoje = dt.datetime.fromtimestamp(agora(), _tz()).date()

    def antes_de_hoje(data: dt.date) -> int:
        return (hoje - (data.replace(year=data.year - 1) if data > hoje else data)).days

    try:
        m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
        if m:
            return (hoje - dt.date(int(m[1]), int(m[2]), int(m[3]))).days
        m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
        if m:
            if m[3]:
                ano = int(m[3]) + (2000 if int(m[3]) < 100 else 0)
                return (hoje - dt.date(ano, int(m[2]), int(m[1]))).days
            return antes_de_hoje(dt.date(hoje.year, int(m[2]), int(m[1])))
        m = re.search(r"\b(\d{1,2}) de (jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", t)
        if m:
            return antes_de_hoje(dt.date(hoje.year, _MESES[m[2]], int(m[1])))
    except ValueError:
        return None
    if re.search(r"\bontem\b", t):
        return 1
    if re.search(r"\bhoje\b", t):
        return 0
    m = re.search(r"\b(?:h[aá] )?(\d{1,3}) ?(d|dias?|sem|semanas?)\b", t)
    if m:
        return int(m[1]) * (7 if m[2].startswith("sem") else 1)
    if re.search(r"\bh[aá] \d{1,2} ?(h|horas?|min|minutos?)\b", t):
        return 0
    return None


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
    if not pode_comentar(lead):
        return False, f"comentário só em lead quente (nota {NOTA_QUENTE}+): siga sem comentário"
    t = (texto or "").strip()
    motivo = validar_texto("aquecer", t, d, a["lead_id"]) or ("" if len(t) >= 15 else "comentário vazio ou curto demais")
    if not motivo and not em_visita:  # catch-up comments follow the same pace as any action
        h = _hora_local()
        ultima = _ultima_acao(d)
        if not HORARIO[0] <= h < HORARIO[1]:
            motivo = f"fora do horário ({HORARIO[0]}h–{HORARIO[1]}h)"
        elif ultima and agora() - ultima < _espera(ultima):
            motivo = "espaçamento: próxima a partir de " + dt.datetime.fromtimestamp(ultima + _espera(ultima), _tz()).strftime("%H:%M")
    if motivo:
        return False, motivo
    teto = LIMITE_COMENTARIOS // 2 if bloqueio_recente(d) else LIMITE_COMENTARIOS
    feitos = sum(1 for x in d["acoes"] if (x.get("comentario") or {}).get("estado") in ("aprovado", "publicado")
                 and float(x["comentario"].get("em") or 0) > 0 and _hoje_local(x["comentario"]["em"]) == _hoje_local())
    if feitos >= teto:
        return False, f"já saíram {feitos} comentários hoje (teto {teto}): siga sem comentário"
    idade = idade_post(base)
    if idade is None:  # not a reviewer attempt: the text may be fine, the evidence is missing
        return False, ("REESCREVA a base: copie entre aspas o trecho escrito do post que você comenta e ponha a data dele "
                       "(AAAA-MM-DD)")
    if idade > POST_COMENTARIO_DIAS:
        return False, f"o post é de {idade} dias atrás: só comente em post de até {POST_COMENTARIO_DIAS} dias"
    tentativas = (a.get("comentario") or {}).get("tentativas", 0)
    if tentativas >= TENTATIVAS_COMENTARIO:
        return False, f"{TENTATIVAS_COMENTARIO} versões reprovadas pelo revisor: siga sem comentário neste perfil"
    v = revisar_textos(d, [{"id": a["id"], "lead_id": a["lead_id"], "tipo": "aquecer", "texto": t, "base": base}], login)[a["id"]]
    with _exclusivo(login):  # the reviewer ran on a snapshot; the verdict goes into the current state
        return _gravar_comentario(login, aid, t, base, v)


def _gravar_comentario(login: str, aid: str, t: str, base: str, v: dict) -> tuple[bool, str]:
    d = carregar(login)
    a = next((x for x in d["acoes"] if x["id"] == aid), None)
    if not a:
        return False, "ação de aquecer não encontrada"
    if a.get("texto") or (a.get("comentario") or {}).get("estado") in ("aprovado", "publicado"):
        return False, "esse aquecimento já tem comentário"
    tentativas = (a.get("comentario") or {}).get("tentativas", 0)
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


@_transacao
def comentado(login: str, aid: str, ok: bool, detalhe: str = "") -> dict | None:
    """The approved comment was (or was not) published."""
    d = carregar(login)
    a = next((x for x in d["acoes"] if x["id"] == aid), None)
    if not a or (a.get("comentario") or {}).get("estado") != "aprovado":
        return None
    a["comentario"].update({"estado": "publicado" if ok else "falhou", "detalhe": str(detalhe)[:300], "feito_em": agora()})
    lead = _lead(d, a["lead_id"])
    if ok:
        a["comentado_em"] = agora()
        if lead:
            lead["historico"].append({"em": agora(), "tipo": "comentario", "texto": a["comentario"]["texto"][:300]})
    _evento(d, a, a["estado"], a["estado"], f"comentário {'publicado' if ok else 'não saiu'}: {detalhe}")
    salvar(login, d)
    _anotar(login, a, lead, "executada" if ok else "falhou", detalhe, comentario=True)
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


def _espera(ultima: float) -> float:
    """Seconds to wait after the last action: between ESPACO[0] and ESPACO[1], different each time but the same for
    the same action (every `proxima` call agrees on the next time)."""
    lo, hi = ESPACO
    return lo + int(hashlib.sha256(f"{ultima:.3f}".encode()).hexdigest(), 16) % (hi - lo + 1)


def _janela_pico(segmento: str = "") -> tuple:
    return PICO_SEGMENTO.get(segmento_rubrica(segmento), PICO_DM) if segmento else PICO_DM


def _no_pico(ts: float | None = None, segmento: str = "") -> bool:
    janela = _janela_pico(segmento)
    if not janela:
        return False
    agora_hm = dt.datetime.fromtimestamp(ts or agora(), _tz()).strftime("%H:%M")
    return janela[0] <= agora_hm < janela[1]


def _ultima_acao(d: dict) -> float:
    return max([a.get("executada_em", 0) for a in d["acoes"]] + [a.get("comentado_em", 0) for a in d["acoes"]] + [0])


TIPOS_DIRECT = ("dm_abertura", "dm_lembrete", "resposta", "parceiro", "seguimento")


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
        return (f"ESPERE: {motivo}. Aguarde até esse horário com code_execution_tool (terminal): "
                f"`{COMANDO_ESPERA}` espera cerca de 3 min; repita até dar o horário e chame `proxima` de "
                "novo. Se o horário passar do início da próxima rodada (minutos 8 e 38), termine. A rodada só termina com "
                "NADA AGORA ou depois de 3 ações feitas.")
    return f"NADA AGORA: {motivo}. Termine a rodada."


def _registrar_bloqueio(d: dict, detalhe: str = "") -> bool:
    """48 h pause, then half pace for 7 days (limites). A second block within 30 days stops everything until the
    person releases it (blind review 5: blocks escalate from a day to weeks). True when it was the second."""
    segundo = any(agora() - float(b.get("em") or 0) < 30 * 86400 for b in d.get("bloqueios") or [])
    d.setdefault("bloqueios", []).append({"em": agora(), "detalhe": str(detalhe or "")[:300]})
    d["bloqueio_ate"] = agora() + (365 * 86400 if segundo else BLOQUEIO)
    if segundo:
        d["config"]["bloqueio_matheus"] = True
    return segundo


@_transacao
def pausar_por_bloqueio(login: str, detalhe: str = "") -> bool:
    """12/10 blind review, item 9: a block or verification seen with no action in hand (e.g. reading the Direct)
    pauses the prospecting like a blocked action does."""
    d = carregar(login)
    segundo = _registrar_bloqueio(d, detalhe)
    salvar(login, d)
    return segundo


@_transacao
def liberar_bloqueio(login: str) -> None:
    """The person releases the prospecting after a second block (it comes back at half pace for 7 days)."""
    d = carregar(login)
    d["bloqueio_ate"] = agora()
    d["config"].pop("bloqueio_matheus", None)
    salvar(login, d)


@_transacao
def resultado(login: str, aid: str, ok: bool, detalhe: str = "", bloqueio: bool = False, quem: str = "") -> dict | None:
    """What happened to an action handed out by `proxima` (or the check of an "incerta"). Only the round that holds the
    action reports it."""
    d = carregar(login)
    a = next((x for x in d["acoes"] if x["id"] == aid), None)
    if not a or a["estado"] not in ("aprovada", "incerta") or not _livre(a, quem):
        return None
    era_incerta = a["estado"] == "incerta"
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
        _registrar_bloqueio(d, detalhe)
    salvar(login, d)
    _anotar(login, a, lead, "executada" if ok else "falhou",
            ("conferida na tela depois de incerta: " if era_incerta else "") + detalhe, ctx_id=quem)
    return a


@_transacao
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
          "resposta": "↩️ Resposta", "parceiro": "🤝 Parceiro", "seguimento": "🔗 Depois do link"}


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


@_transacao
def guardar_pacote(login: str, ids: list) -> str:
    d = carregar(login)
    pid = _id()
    d.setdefault("pacotes", {})[pid] = {"ids": ids, "em": agora()}
    d["pacotes"] = dict(list(d["pacotes"].items())[-30:])
    salvar(login, d)
    return pid


def ids_do_pacote(login: str, pid: str) -> list:
    return (carregar(login).get("pacotes") or {}).get(pid, {}).get("ids", [])


def enviar(login: str, texto: str, botoes: list | None = None, tipo: str = "progresso", ponte=None, arquivo: str = "",
           legenda: str = "") -> str:
    """Phone message (or a file, e.g. the hot lead's card); in test mode it is recorded instead (no third party is
    ever involved here — it is the owner's phone — but tests must not buzz it)."""
    if modo_teste(login):
        CAIXA_TESTES.parent.mkdir(parents=True, exist_ok=True)
        with CAIXA_TESTES.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"em": agora(), "usuario": _login(login), "texto": texto, "botoes": botoes or [],
                                "tipo": tipo, "origem": "prospeccao", "arquivo": arquivo, "legenda": legenda},
                               ensure_ascii=False) + "\n")
        return ""
    if not ponte:
        return "ponte indisponível"
    if arquivo:
        return ponte.enviar(login, texto, arquivo=arquivo, legenda=legenda, botoes=botoes, tipo=tipo)
    return ponte.enviar(login, texto, botoes=botoes, tipo=tipo)


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
    # 12/10 review (§5, "métrica certa"): the first answers came from comments, which the DM-only rate never counted
    comentou: set = set()
    for a in d["acoes"]:
        c = a.get("comentario") or {}
        if ((a["tipo"] == "aquecer" and a["estado"] == "executada" and a.get("texto") and (a.get("executada_em") or 0) >= corte)
                or (c.get("estado") == "publicado" and (c.get("feito_em") or 0) >= corte)):
            comentou.add(a["lead_id"])
    comentados = [l for l in d["leads"] if l["id"] in comentou]
    pelo_comentario = [l for l in comentados if any((h["tipo"].startswith("etapa:") or h["tipo"] == "interagiu")
                                                    and h.get("onde") == "comentario" and h["tipo"] != "etapa:descartado"
                                                    for h in l["historico"])]
    aprovadas = sum(1 for a in acoes if a["estado"] in ("aprovada", "executada", "falhou"))
    decididas = sum(1 for a in acoes if a["estado"] in ("aprovada", "executada", "falhou", "pulada"))
    return {"dias": dias, "acoes": por_estado, "etapas": etapas, "geral": taxa(abordados),
            "comentarios": {"comentados": len(comentados), "responderam": len(pelo_comentario),
                            "taxa_resposta": round(100 * len(pelo_comentario) / len(comentados), 1) if comentados else 0.0},
            "por_variante": por("variante"), "ab": sugestao_ab(por("variante")),
            "variante_fixa": d["config"].get("variante_fixa", ""), "por_segmento": por("segmento"), "por_cidade": por("cidade"),
            "por_faixa": por("faixa"), "por_fonte": metricas_fontes(login, dias),
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
    pendentes = [(l, h) for l in d["leads"] for h in l["historico"][-3:]
                 if str(h.get("tipo", "")).startswith("etapa:") and str(h.get("texto") or "").lower().startswith("pendente:")
                 and agora() - float(h.get("em") or 0) < 2 * 86400 and not l.get("humano")]
    if not (respostas or feitas or falhas or novos or esperando or pendentes or any(
            h["tipo"] == "interagiu" and h.get("onde") == "comentario" and de_hoje(h["em"])
            for l in d["leads"] for h in l["historico"])):
        return ""
    linhas = [f"🎯 *Prospecção Raiz — {dt.datetime.fromtimestamp(agora(), _tz()).strftime('%d/%m')}*"]
    if respostas:
        linhas.append("\n💬 *Responderam* — olhe primeiro")
        for l in respostas:
            h = next(x for x in reversed(l["historico"]) if x["tipo"].startswith("etapa:") and de_hoje(x["em"]))
            onde = "no comentário" if h.get("onde") == "comentario" else "no Direct"
            linhas.append(f"• {l['nome'][:40]} (@{l['handle']}) — {onde}: «{(h.get('texto') or '')[:160]}» ({l['etapa']})")
    if pendentes:  # blind review 4, item 4: a promise made in his name has an owner and shows up every evening
        linhas.append("\n⏳ *Esperando você* (o agente prometeu voltar)")
        linhas += [f"• @{l['handle']}: {(h.get('texto') or '')[9:].strip()[:140]}" for l, h in pendentes[:8]]
    interacoes = [(l, h) for l in d["leads"] for h in l["historico"]
                  if h["tipo"] == "interagiu" and h.get("onde") == "comentario" and de_hoje(h["em"])]
    if interacoes:  # answers to our comments are no longer notified one by one (12/10 blind review): they show here
        linhas.append("\n👋 *Responderam ao nosso comentário* (vão primeiro na 1ª mensagem)")
        linhas += [f"• @{l['handle']}: «{(h.get('texto') or '')[:120]}»" for l, h in interacoes[:8]]
    if feitas:  # everything that went out today, one line per profile
        n = {t: sum(1 for a in feitas if a["tipo"] == t) for t in TIPOS}
        nomes = {"aquecer": "aquecidos", "dm_abertura": "primeiras mensagens", "dm_lembrete": "lembretes", "seguimento": "seguimentos",
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
        por_o = Counter(origem(l) for l in novos)
        de_onde = f" ({', '.join(f'{o} {n}' for o, n in por_o.most_common())})" if novos else ""
        linhas.append(f"\n🔎 *Leads:* {len(novos)} entraram hoje{de_onde} · estoque {e['prontos']}/{e['alvo']} prontos para aquecer"
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
    conferido = conferencia_livro(login, feitas, comentados)
    if conferido:
        linhas.append("\n" + conferido)
    if agora() < d["bloqueio_ate"]:
        linhas.append("\n⛔ Pausado até " + dt.datetime.fromtimestamp(d["bloqueio_ate"], _tz()).strftime("%d/%m %H:%M"))
    return "\n".join(linhas)


def conferencia_livro(login: str, feitas: list, comentados: list) -> str:
    """'Feito hoje' conferido (12/10 review §7 item 1): what the prospecting file says went out today, checked against
    the append-only ledger. Counted only from the ledger's first record (it started 12/10), so its start never looks
    like a gap. '' when there is no ledger or nothing to compare."""
    try:
        livro = _livro()
        if not livro or not hasattr(livro, "do_periodo"):
            return ""
        meia_noite = dt.datetime.fromtimestamp(agora(), _tz()).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        linhas = [r for r in livro.do_periodo(login, meia_noite) if r["origem"] == "prospeccao"]
        todas = livro.do_periodo(login, 0) if not linhas else linhas
        if not todas:
            return ""
        inicio = max(meia_noite, min(r["em"] for r in todas))
    except Exception as exc:  # the ledger never breaks the summary
        print(f"prospeccao: conferência com o livro falhou: {exc}", flush=True)
        return ""
    no_livro = Counter(r["verbo"] for r in linhas if r["fase"] == "executada" and r["em"] >= inicio)
    aqui = Counter(VERBO_LIVRO.get(a["tipo"], a["tipo"]) for a in feitas if (a.get("executada_em") or 0) >= inicio)
    aqui["comentario"] += sum(1 for a in comentados if (a["comentario"].get("feito_em") or 0) >= inicio)
    nomes = {"dm": "mensagens", "seguir_curtir": "seguir e curtir", "comentario": "comentários"}
    if not (sum(no_livro.values()) or sum(aqui.values())):
        return ""
    diferentes = [v for v in nomes if no_livro[v] != aqui[v]]
    if not diferentes:
        return "📒 Conferido no livro: " + ", ".join(f"{aqui[v]} {nomes[v]}" for v in nomes if aqui[v]) + "."
    return ("📒 ⚠️ O livro não bate: " + "; ".join(f"{nomes[v]} {no_livro[v]} no livro × {aqui[v]} na prospecção"
                                                 for v in diferentes) + ". Confira se algo saiu repetido ou sem registro.")


@_transacao
def assumir_lead(login: str, lid: str) -> dict | None:
    """"🙋 Deixa comigo" (12/10 review §7 item 3): the person takes this @ over. The automation stops for it: what is
    proposed or approved (and not already being executed) is cancelled, and nothing new is accepted until he hands it
    back (`devolver_lead`). Returns the lead, or None when it does not exist."""
    d = carregar(login)
    lead = _lead(d, lid)
    if not lead:
        return None
    if not lead.get("humano"):
        lead["humano"] = {"desde": agora()}
        lead["historico"].append({"em": agora(), "tipo": "humano", "texto": "o Matheus assumiu a conversa"})
    for a in d["acoes"]:
        if a["lead_id"] == lead["id"] and a["estado"] in ("proposta", "aprovada") and not a.get("em_execucao"):
            _mudar(d, a, "cancelada", "o Matheus assumiu a conversa com esse perfil")
    salvar(login, d)
    return lead


@_transacao
def devolver_lead(login: str, lid: str) -> dict | None:
    """The person hands the @ back: the rounds may propose for it again."""
    d = carregar(login)
    lead = _lead(d, lid)
    if not lead or not lead.get("humano"):
        return lead
    lead.pop("humano")
    lead["historico"].append({"em": agora(), "tipo": "humano", "texto": "o Matheus devolveu a conversa ao agente"})
    salvar(login, d)
    return lead


def botao_assumir(login: str, lid: str) -> list:
    return [{"id": f"pl:{_login(login)}:{lid}:eu", "titulo": "🙋 Deixa comigo"}]  # 12/10: "Quero falar eu" soava estranho


FUNIL = (("aquecido", "aquecidos"), ("abordado", "abordados"), ("respondeu", "responderam"), ("lead", "leads"),
         ("demo", "demos"), ("cliente", "clientes"))


def painel(login: str) -> str:
    """/painel (12/10 review §7 item 11): the funnel, the stock and the week in a few lines, from the register (no
    model). The funnel counts who REACHED each stage (a lead who answered was also approached); '' with no leads."""
    d = carregar(login)
    if not d["leads"]:
        return ""
    ordem = {e: i for i, e in enumerate(ETAPAS)}

    def chegou(l, etapa):
        if l["etapa"] in ordem and l["etapa"] not in ("sem_resposta", "descartado") and ordem[l["etapa"]] >= ordem[etapa]:
            return True
        return any(h["tipo"] == f"etapa:{etapa}" or (etapa == "abordado" and h["tipo"] == "dm_abertura")
                   or (etapa == "aquecido" and h["tipo"] in ("aquecer", "dm_abertura")) for h in l["historico"])

    funil = " → ".join(f"{sum(1 for l in d['leads'] if chegou(l, e))} {nome}" for e, nome in FUNIL)
    e = estoque(login)
    pf = e["por_fonte"]
    fontes = " · ".join(f"{o} {pf[o]['prontos']}/{pf[o]['alvo']}" if pf[o]["alvo"] else f"{o} {pf[o]['prontos']}"
                        for o in ORIGENS if pf[o]["alvo"] or pf[o]["prontos"])
    m = metricas(login, 7)
    g, c = m["geral"], m["comentarios"]
    hoje = _hoje_local()
    feitas = Counter(a["tipo"] for a in d["acoes"] if a["estado"] == "executada" and a.get("executada_em")
                     and _hoje_local(a["executada_em"]) == hoje)
    nomes = {"aquecer": "aquecidos", "dm_abertura": "primeiras mensagens", "dm_lembrete": "lembretes", "resposta": "respostas",
             "seguimento": "seguimentos depois do link"}
    linhas = [f"Funil (desde o início): {funil}",
              f"Estoque: {e['prontos']}/{e['alvo']} prontos para aquecer ({fontes})",
              f"Semana: {g['abordados']} abordados, {g['responderam']} responderam ({g['taxa_resposta']:.0f}%)"
              + (f"; comentários: {c['responderam']} de {c['comentados']} responderam" if c["comentados"] else ""),
              "Hoje: " + (", ".join(f"{n} {nomes.get(t, t)}" for t, n in feitas.most_common()) if feitas else "nada saiu ainda")]
    if d["config"].get("crm_planilha"):
        linhas.append(f"Planilha CRM Raiz (todo dia às 20h30): https://docs.google.com/spreadsheets/d/{d['config']['crm_planilha']}")
    comigo = [l["handle"] for l in d["leads"] if l.get("humano")]
    if comigo:
        linhas.append("Com você (a automação não fala): " + ", ".join(f"@{h}" for h in comigo[:5]))
    if agora() < d["bloqueio_ate"]:
        linhas.append("⛔ Pausada por bloqueio do Instagram até "
                      + dt.datetime.fromtimestamp(d["bloqueio_ate"], _tz()).strftime("%d/%m %H:%M"))
    return "\n".join(linhas)


# 12/10 review §5.2 item 10: the "CRM Raiz" sheet, a daily VIEW of the register for the person (the register stays the
# source; nothing is read back from the sheet). Written by extensions/python/job_loop/_46_crm_raiz.py.
CRM_TITULO = "CRM Raiz"
CRM_COLUNAS = ["@", "Nome", "Etapa", "Segmento", "Cidade", "Fonte", "Nota", "Entrou", "Último contato", "O que aconteceu",
               "Próximo passo"]
CRM_ETAPA = {"novo": "novo", "aquecido": "aquecido", "abordado": "abordado (DM)", "lembrado": "lembrete enviado",
             "respondeu": "respondeu", "lead": "lead", "demo": "demo", "teste": "teste grátis", "cliente": "cliente",
             "sem_resposta": "sem resposta"}
CRM_ORDEM = ("cliente", "teste", "demo", "lead", "respondeu", "lembrado", "abordado", "aquecido", "novo", "sem_resposta")


def _proximo_passo(lead: dict, pendente: dict | None) -> str:
    if lead.get("humano"):
        return "com você (a automação não fala com esse @)"
    if pendente:
        return f"{ROTULO.get(pendente['tipo'], pendente['tipo'])}: " + (
            "esperando aprovação" if pendente["estado"] == "proposta" else
            "aprovada, sai na próxima rodada" if pendente["estado"] == "aprovada" else "conferir se saiu")
    dia = lambda dias: (dt.datetime.fromtimestamp(lead["atualizado"], _tz()).date()  # noqa: E731
                        + dt.timedelta(days=dias)).strftime("%d/%m")
    return {"novo": "aquecer (seguir, curtir, comentar)", "aquecido": f"primeira mensagem a partir de {dia(DIAS_DM)}",
            "abordado": f"lembrete a partir de {dia(DIAS_LEMBRETE)}",
            "lembrado": f"encerra sem resposta em {dia(ESPERA_FIM // 86400)}",
            "respondeu": "responder (a rodada propõe)", "lead": "oferecer a conversa de 15 min",
            "demo": "fazer a demo", "teste": "acompanhar o teste", "cliente": "—", "sem_resposta": "—"}.get(lead["etapa"], "—")


def linhas_crm(login: str) -> list:
    """The sheet's rows: the header, then one row per lead (discarded ones out), hottest stage first, then the most
    recent contact."""
    d = carregar(login)
    pendentes = {a["lead_id"]: a for a in d["acoes"] if a["estado"] in ("proposta", "aprovada", "incerta")}
    data = lambda ts: dt.datetime.fromtimestamp(ts, _tz()).strftime("%d/%m/%Y") if ts else ""  # noqa: E731
    leads = [l for l in d["leads"] if l["etapa"] in CRM_ETAPA]
    leads.sort(key=lambda l: (CRM_ORDEM.index(l["etapa"]), -(l.get("atualizado") or 0)))
    linhas = [CRM_COLUNAS]
    for l in leads:
        ultimo = l["historico"][-1] if l["historico"] else None
        linhas.append([f"@{l['handle']}" if l.get("handle") else "", str(l.get("nome") or "")[:60], CRM_ETAPA[l["etapa"]],
                       str(l.get("segmento") or ""), str(l.get("cidade") or ""), origem(l),
                       "" if l.get("nota") is None else str(l["nota"]), data(l.get("criado")),
                       data(ultimo["em"]) if ultimo else "", " ".join(str((ultimo or {}).get("texto") or "").split())[:140],
                       _proximo_passo(l, pendentes.get(l["id"]))])
    return linhas


@_transacao
def definir_crm(login: str, planilha: str) -> None:
    """Where the CRM sheet lives (its id), so every day the same sheet is rewritten."""
    d = carregar(login)
    d["config"]["crm_planilha"] = str(planilha or "")
    salvar(login, d)


def cartao_lead(login: str, lid: str) -> dict | None:
    """The hot lead's card (12/10 review §7 item 3), one page for the person to take over well: who it is, what the
    agent saw on the profile, the whole conversation (both sides, in order) and the next message suggested."""
    d = carregar(login)
    l = _lead(d, lid)
    if not l:
        return None
    acoes = [a for a in d["acoes"] if a["lead_id"] == l["id"]]
    pendente = next((a for a in reversed(acoes) if a["estado"] in ("proposta", "aprovada", "incerta")), None)
    quando = lambda ts: dt.datetime.fromtimestamp(ts, _tz()).strftime("%d/%m %H:%M")  # noqa: E731
    nosso = {"aquecer": "comentário da Raiz", "comentario": "comentário da Raiz", "dm_abertura": "Raiz no Direct",
             "dm_lembrete": "Raiz no Direct (lembrete)", "resposta": "Raiz respondeu",
             "seguimento": "Raiz no Direct (depois do link)"}
    conversa = []
    for h in l["historico"]:
        texto = " ".join(str(h.get("texto") or "").split())
        if not texto or h.get("mesma_fala"):  # the same answer understood better (stage moved up): said once
            continue
        if h["tipo"] in nosso:
            conversa.append({"quando": quando(h["em"]), "quem": nosso[h["tipo"]], "texto": texto[:300]})
        elif h["tipo"].startswith("etapa:") and h["tipo"] not in ("etapa:descartado", "etapa:sem_resposta"):
            onde = "no comentário" if h.get("onde") == "comentario" else "no Direct"
            conversa.append({"quando": quando(h["em"]), "quem": f"{l.get('nome') or l['handle']} {onde}", "texto": texto[:300]})
    vistos = [a["base"] for a in acoes if a.get("base") and not a["base"].startswith("reposição automática")]
    return {"nome": str(l.get("nome") or l["handle"]), "handle": l["handle"], "url": l.get("url", ""),
            "etapa": CRM_ETAPA.get(l["etapa"], l["etapa"]), "segmento": str(l.get("segmento") or ""),
            "cidade": str(l.get("cidade") or ""), "seguidores": str(l.get("seguidores") or ""),
            "nota": "" if l.get("nota") is None else str(l["nota"]), "fonte": origem(l),
            "motivo": str(l.get("motivo") or "")[:400], "post_recente": str(l.get("post_recente") or "")[:200],
            "vistos": [v[:250] for v in vistos[-3:]], "conversa": conversa[-8:],
            "proxima": (pendente or {}).get("texto", "")[:500] if (pendente or {}).get("tipo") != "aquecer" else "",
            "proximo_passo": _proximo_passo(l, pendente), "gerado": quando(agora())}


def resumo_contexto(login: str) -> str:
    """What a search round needs: limits left, leads due a next step, handles already known, pause state."""
    expirar(login)
    fechar_vencidos(login)
    d = carregar(login)
    c = cotas(login)
    dev = devidos(login)
    e = estoque(login)
    pf = e["por_fonte"]
    partes = "; ".join((f"{o} {pf[o]['prontos']}/{pf[o]['alvo']}" + (f" (FALTAM {pf[o]['faltam']})" if pf[o]["faltam"] else ""))
                       if pf[o]["alvo"] else f"{o} {pf[o]['prontos']} (fora da divisão)" for o in ORIGENS)
    linhas = [f"# Prospecção — {dt.datetime.now(_tz()).strftime('%a %d/%m %H:%M')} ({FUSO})",
              "Cotas que ainda cabem hoje (propostas aprovadas contam): " + ", ".join(f"{k} {v}" for k, v in c.items()),
              f"Estoque de leads prontos para aquecer: {e['prontos']} de {e['alvo']}" +
              (f" — FALTAM {e['faltam']}." if e["faltam"] else " (cheio).") + f" Por fonte: {partes}." +
              (" Planilha/catálogo: reponha com `fontes`." if pf["planilha"]["faltam"] or pf["catalogo"]["faltam"] else "") +
              ((f" Instagram: chame `fontes_instagram` (Apify, não usa a nossa conta) até {pf['instagram']['faltam']} novos." if apify_pronto(login)
                else f" Instagram: busque no Instagram (skill, seção 5) até {pf['instagram']['faltam']} novos." if scripts_conta(login)
                else f" Instagram: faltam {pf['instagram']['faltam']} (sem Apify e com os scripts desligados, siga com o que há).")
               if pf["instagram"]["faltam"] else "")]
    if agora() < d["bloqueio_ate"]:
        linhas.append("⛔ PAUSADO após bloqueio do Instagram — não proponha nada " + (
            "até o Matheus liberar (segundo bloqueio em 30 dias)" if d["config"].get("bloqueio_matheus") else
            "até " + dt.datetime.fromtimestamp(d["bloqueio_ate"], _tz()).strftime("%d/%m %H:%M")))
    if d["config"].get("variante_fixa") in ("A", "B"):
        linhas.append(f"Primeira mensagem: só a variante {d['config']['variante_fixa']} (fixada pelos números; não alterne).")
    if api_meta_pronta(login):
        renovar = aviso_acesso_meta(acesso_meta(login), agora())
        if renovar:
            linhas.append(renovar)
    for tipo, lista in dev.items():
        if lista:
            linhas.append(f"\n## Devem receber «{tipo}» agora ({len(lista)})")
            linhas += [f"- [{l['id']}] @{l['handle']} — {l['nome']} ({l['segmento']}, {l['cidade']}; nota {l.get('nota', '—')}); motivo: {l['motivo'][:120]}"
                       + (f"; ESCREVA A VARIANTE {variante_sugerida(d, l)}" if tipo == "dm_abertura" else "")
                       + (f"; seguimento: {MOTIVOS_SEGUIMENTO.get(motivo_seguimento(d, l), '')}" if tipo == "seguimento" else "")
                       + (f"; já recebeu: {l['historico'][-1]['texto'][:160]}" if l["historico"] else "") for l in lista[:25]]
    hoje_txt = [a for a in d["acoes"] if a["tipo"] in ("dm_abertura", "dm_lembrete", "seguimento", "parceiro")
                and a["estado"] in ("proposta", "aprovada", "incerta", "executada") and _hoje_local(a.get("criada")) == _hoje_local()]
    comentarios_hoje = [a["comentario"]["texto"] for a in d["acoes"] if (a.get("comentario") or {}).get("estado") in
                        ("aprovado", "publicado") and float(a["comentario"].get("em") or 0) > 0
                        and _hoje_local(a["comentario"]["em"]) == _hoje_local()]
    if hoje_txt or comentarios_hoje:  # blind review 5, item 9: each round is a new session and cannot see these
        linhas.append("\n## Textos de hoje (não comece igual a nenhum nem repita a estrutura)")
        linhas += [f"- {a['tipo']}: «{a['texto'][:80]}»" for a in hoje_txt[-12:]]
        linhas += [f"- comentário: «{c[:80]}»" for c in comentarios_hoje[-6:]]
    conversas = [l for l in d["leads"] if l["etapa"] in ("abordado", "lembrado", "respondeu", "lead", "demo")]
    if conversas and varredura_devida(d):
        linhas.append(f"\n## VARREDURA COMPLETA do Direct agora ({len(conversas)}) — abra cada uma (perfil → Mensagem), "
                      "depois `caixa_lida` com varredura: true")
        linhas += [f"- [{l['id']}] @{l['handle']} ({l['etapa']}); última nossa: {l['historico'][-1]['texto'][:80] if l['historico'] else ''}"
                   for l in conversas[:20]]
    elif conversas:
        proxima_v = dt.datetime.fromtimestamp((d.get("varredura_em") or 0) + VARREDURA_H * 3600, _tz()).strftime("%H:%M")
        recentes = [l for l in conversas if _interagiu_hoje(l)
                    or any(h["tipo"] in TIPOS_DIRECT and agora() - h["em"] < 72 * 3600 for h in l["historico"])]
        linhas.append(f"\n## Direct nesta rodada (varredura completa a partir das {proxima_v}): veja o contador de não lidas "
                      "e as solicitações"
                      + (f"; abra (perfil → Mensagem) estas {len(recentes)}, as mais recentes:" if recentes else ".")
                      + " Contador acima de zero sem você achar de quem é: faça a varredura completa agora.")
        linhas += [f"- [{l['id']}] @{l['handle']} ({l['etapa']})" for l in recentes[:15]]
        linhas.append(f"Todas as conversas em andamento ({len(conversas)}), para a varredura completa: "
                      + ", ".join("@" + l["handle"] for l in conversas[:40]))
    conhecidos = sorted(l["handle"] for l in d["leads"])
    linhas.append(f"\n## Já conhecidos ({len(conhecidos)}) — não registre de novo\n" + (", ".join(conhecidos[-400:]) or "(nenhum)"))
    rej = d.get("rejeitados") or {}
    if rej:
        linhas.append(f"\n## Já examinados e rejeitados ({len(rej)}) — não abra de novo\n" + ", ".join(sorted(rej)[-400:]))
    m = metricas(login, 14)
    linhas.append(f"\n## Como está indo (14 dias)\n{json.dumps(m['geral'], ensure_ascii=False)}; por variante: "
                  f"{json.dumps(m['por_variante'], ensure_ascii=False)}; aprovação das propostas: {m['taxa_aprovacao']}%")
    rend = linha_fontes(login, 28)
    if rend:
        linhas.append("\n## Rendimento por fonte (28 dias)\n" + rend)
    return "\n".join(linhas)

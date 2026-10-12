"""The personal-assistant layer: e-mail replies drafted in the person's style, meeting briefings and follow-ups,
bills and due dates, and the morning summary as a voice note. State lives in /a0/usr/auxiliar/<login>.json."""

import datetime as dt
import fcntl
import functools
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
import uuid
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path

PASTA = Path("/a0/usr/auxiliar")
FUSO = "America/Bahia"
ANTES_DA_REUNIAO = dt.timedelta(minutes=30)
DEPOIS_DA_REUNIAO = dt.timedelta(minutes=10)


def _login(login: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "", (login or "").lower()) or "matheus"


def _id() -> str:
    return uuid.uuid4().hex[:6]


# ------------------------------------------------------------------ safe state file
# 12/10 review: an unreadable file was read as empty, so the next save wiped bills, drafts and meetings (and their
# reminders); writers shared one temporary name and could overwrite each other. Now: one writer at a time per person
# (a short file lock, never held across an await), a unique temporary file flushed to disk, and unreadable = stop.
ESPERA_TRAVA = 30  # seconds; writes take milliseconds
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
                    raise RuntimeError("o auxiliar está ocupado gravando há mais de 30 s; tente de novo") from None
                time.sleep(0.05)
        travas[chave] = 1
        try:
            yield
        finally:
            travas[chave] = 0
            fcntl.flock(fh, fcntl.LOCK_UN)


def _transacao(fn):
    """Load → change → save as one step for the person in the first argument (sync functions only)."""
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
                    raise EstadoIlegivel(f"o arquivo do auxiliar ({arq.name}) não pôde ser lido ({str(exc)[:60]}); "
                                         "nada foi gravado") from None
                time.sleep(0.1)
    for chave in ("rascunhos", "contas", "reunioes"):
        d.setdefault(chave, [])
    d.setdefault("config", {})
    return d


def salvar(login: str, d: dict) -> None:
    with _exclusivo(login):
        corte = time.time() - 45 * 86400
        d["rascunhos"] = [r for r in d["rascunhos"] if r["criado"] > corte][-100:]
        d["reunioes"] = [r for r in d["reunioes"] if r.get("fim_ts", 0) > corte][-100:]
        d["contas"] = [c for c in d["contas"] if c["estado"] == "aberta" or c.get("fechada_em", 0) > corte][-200:]
        fd, tmp = tempfile.mkstemp(dir=PASTA, prefix=f".{_login(login)}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, PASTA / f"{_login(login)}.json")
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def _tz():
    from zoneinfo import ZoneInfo

    return ZoneInfo(FUSO)


def agora() -> dt.datetime:
    return dt.datetime.now(_tz())


def _data(texto: str) -> dt.datetime | None:
    """ISO date/datetime → aware datetime (naive = America/Bahia)."""
    texto = str(texto or "").strip().replace("Z", "+00:00")
    if not texto:
        return None
    try:
        d = dt.datetime.fromisoformat(texto)
    except ValueError:
        try:
            d = dt.datetime.combine(dt.date.fromisoformat(texto[:10]), dt.time(9))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=_tz())


# ------------------------------------------------------------------ writing style (idea 8)

def arquivo_estilo(login: str) -> Path:
    return PASTA / "estilo" / f"{_login(login)}.md"


def estilo(login: str) -> str:
    try:
        return arquivo_estilo(login).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# 12/10 review: the 2,500-character style went into every prompt (routines, summaries, checks) and cost more than it
# gave. It now goes only into conversations where something will be written in the person's name.
ESCRITA = re.compile(r"e-?mails?\b|respond|respost|mensage|escrev|rascunh|redig|\btexto|\bpost\b|legenda|\bcarta\b|"
                     r"proposta|\bdirect\b|\bdms?\b|coment[aá]r|whats|\bresponda", re.I)


def quer_estilo(pedido) -> bool:
    """The person's own message asks for something written in their name. A routine's prompt (long, full of "responda"
    and "escreva" meant for the agent) never counts: routines read the style with `rascunho` acao "estilo" when they
    write in the person's name."""
    if isinstance(pedido, dict):  # the chat history keeps {"user_message": …, "attachments": …}
        pedido = pedido.get("user_message") or ""
    texto = str(pedido or "")
    return len(texto) <= 600 and bool(ESCRITA.search(texto))


def mensagens_dele(login: str, limite: int = 80) -> list[str]:
    """What the person really typed on the phone (Telegram/WhatsApp chats), newest last — not task prompts, test
    messages or button texts, which are not their voice."""
    saida = []
    for arquivo in sorted(Path("/a0/usr/chats").glob("*/chat.json"), key=lambda p: p.stat().st_mtime):
        try:
            j = json.loads(arquivo.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str((j.get("data") or {}).get("whatsapp_de") or "").lower() != _login(login):
            continue
        for item in (j.get("log") or {}).get("logs", []):
            if item.get("type") != "user":
                continue
            texto = re.sub(r"\n\n\(leitura automática das abreviações.*$", "", str(item.get("content") or ""), flags=re.S).strip()
            if not texto or texto.startswith(("✅", "✏️", "🧵", "💡", "⏰", "🙈", "👍", "👎", "/")) or len(texto) > 600:
                continue
            saida.append(texto)
    return saida[-limite:]


def salvar_estilo(login: str, perfil: str) -> None:
    arquivo_estilo(login).parent.mkdir(parents=True, exist_ok=True)
    arquivo_estilo(login).write_text(perfil.strip()[:6000] + "\n", encoding="utf-8")


# ------------------------------------------------------------------ e-mail replies (idea 1)

def _chave(para: str, assunto: str) -> tuple[str, str]:
    email = re.search(r"[\w.+-]+@[\w.-]+", para or "")
    assunto = re.sub(r"^((re|res|fw|fwd|enc)\s*:\s*)+", "", (assunto or "").strip().lower())
    return (email.group(0).lower() if email else (para or "").strip().lower(), assunto)


def ja_tratado(login: str, para: str, assunto: str) -> dict | None:
    """A draft for the same e-mail conversation in the last 7 days (pending, used or dismissed), so the radar and
    the Google watcher don't deliver it twice."""
    chave, corte = _chave(para, assunto), time.time() - 7 * 86400
    return next((r for r in reversed(carregar(login)["rascunhos"]) if r["criado"] > corte
                 and r["estado"] != "substituido" and _chave(r["para"], r["assunto"]) == chave), None)


@_transacao
def novo_rascunho(login: str, para: str, assunto: str, texto: str, pedido: str = "", referencia: str = "") -> dict:
    d = carregar(login)
    chave = _chave(para, assunto)
    for r in d["rascunhos"]:  # a new version replaces the pending one of the same conversation
        if r["estado"] == "pendente" and _chave(r["para"], r["assunto"]) == chave:
            r["estado"] = "substituido"
    r = {"id": _id(), "criado": time.time(), "para": para.strip()[:200], "assunto": assunto.strip()[:200],
         "texto": texto.strip()[:4000], "pedido": pedido.strip()[:400], "referencia": referencia.strip()[:300],
         "estado": "pendente"}
    d["rascunhos"].append(r)
    salvar(login, d)
    return r


def obter_rascunho(login: str, rid: str) -> dict | None:
    return next((r for r in carregar(login)["rascunhos"] if r["id"] == rid), None)


@_transacao
def marcar_rascunho(login: str, rid: str, estado: str) -> None:
    d = carregar(login)
    for r in d["rascunhos"]:
        if r["id"] == rid:
            r["estado"] = estado
            r["decidido_em"] = time.time()
    salvar(login, d)


def mensagem_rascunho(r: dict) -> str:
    linhas = [f"✉️ *Resposta pronta — {r['assunto']}*", f"_Para: {r['para']}_"]
    if r.get("pedido"):
        linhas += ["", f"O que pediram: {r['pedido']}"]
    linhas += ["", "Rascunho:", r["texto"]]
    return "\n".join(linhas)


def botoes_rascunho(login: str, rid: str) -> list:
    base = f"rd:{_login(login)}:{rid}"
    return [{"id": f"{base}:usar", "titulo": "✅ Usar"}, {"id": f"{base}:ajustar", "titulo": "✏️ Ajustar"},
            {"id": f"{base}:deixa", "titulo": "🙈 Deixa"}]


def gmail_rascunhos(login: str) -> bool:
    """Whether the Google connector may create Gmail drafts (needs the gmail:drafts permission)."""
    return bool(carregar(login)["config"].get("gmail_rascunhos"))


# ------------------------------------------------------------------ bills and due dates (idea 5)

def _valor(valor) -> str:
    """Decimal-safe amount as text ("1234.56"); "" when unknown."""
    texto = str(valor or "").strip().replace("R$", "").replace(" ", "")
    if not texto:
        return ""
    if "," in texto:  # Brazilian format: 1.234,56
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return str(Decimal(texto).quantize(Decimal("0.01")))
    except InvalidOperation:
        return ""


def codigo_pagamento(texto: str) -> str:
    """The boleto's typed line (44-48 digits) or a Pix copy-and-paste code (EMV, starts with 000201), cleaned; '' when
    it is neither. Only for the person to copy (12/10 review): the agent never pays."""
    bruto = str(texto or "").strip()
    if bruto.startswith("000201") and 50 <= len(bruto) <= 512 and " " not in bruto:
        return bruto
    digitos = re.sub(r"[\s.\-]", "", bruto)
    return digitos if digitos.isdigit() and 44 <= len(digitos) <= 48 else ""


# Words that do not tell who charges: "Fatura Vivo" and "Conta da Vivo Fibra - outubro" share only "vivo"
SEM_EMISSOR = {"conta", "contas", "fatura", "boleto", "pagamento", "mensalidade", "parcela", "valor", "vencimento",
               "referente", "ref", "mes", "para", "com", "sua", "seu", "das", "dos", "pix", "cobranca", "janeiro",
               "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro",
               "dezembro", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"}


def _emissor(descricao: str) -> set:
    t = "".join(ch for ch in unicodedata.normalize("NFD", descricao.lower()) if unicodedata.category(ch) != "Mn")
    return {w for w in re.findall(r"[a-z]{3,}", t) if w not in SEM_EMISSOR}


def _mesma_conta(c: dict, descricao: str, venc: str, valor: str, codigo: str) -> str:
    """How an open bill matches the one being saved: "codigo" (the same boleto line or Pix code), "igual" (same
    description and due date), "emissor" (same due date and amount and a word of who charges in common — 12/10 review
    §6: the e-mail and the photo of the same bill came with different descriptions and became two) or "" (another)."""
    if c["estado"] != "aberta":
        return ""
    if codigo and c.get("codigo") == codigo:
        return "codigo"
    if c["vencimento"] != venc:
        return ""
    if c["descricao"].lower() == descricao.lower():
        return "igual"
    if valor and c.get("valor") == valor and _emissor(c["descricao"]) & _emissor(descricao):
        return "emissor"
    return ""


@_transacao
def salvar_conta(login: str, descricao: str, vencimento: str, valor="", moeda: str = "BRL", fonte: str = "",
                 cid: str = "", codigo: str = "") -> tuple[dict | None, str]:
    venc = _data(vencimento)
    if not descricao.strip() or venc is None:
        return None, "Diga `descricao` e `vencimento` (AAAA-MM-DD)."
    d = carregar(login)
    descricao, venc_iso, valor_n, codigo_n = descricao.strip(), venc.date().isoformat(), _valor(valor), codigo_pagamento(codigo)
    conta, como = next((c for c in d["contas"] if cid and c["id"] == cid), None), "id"
    if conta is None:  # same bill seen again (another e-mail, the photo, another round): update it
        conta, como = next(((c, m) for c in d["contas"] if (m := _mesma_conta(c, descricao, venc_iso, valor_n, codigo_n))),
                           (None, ""))
    if conta is None:
        conta = {"id": _id(), "estado": "aberta", "criada": time.time(), "lembrada": {}}
        d["contas"].append(conta)
    if como in ("codigo", "emissor"):  # another description of a bill already known: keep what it had, fill the gaps
        conta.update({"valor": conta.get("valor") or valor_n, "fonte": conta.get("fonte") or fonte.strip()[:300],
                      "codigo": conta.get("codigo") or codigo_n})
    else:
        conta.update({"descricao": descricao[:160], "vencimento": venc_iso, "valor": valor_n or conta.get("valor", ""),
                      "moeda": (moeda or "BRL").upper()[:3], "fonte": (fonte or conta.get("fonte", "")).strip()[:300],
                      "codigo": codigo_n or conta.get("codigo", "")})
    salvar(login, d)
    return conta, ""


@_transacao
def fechar_conta(login: str, cid: str, estado: str = "paga") -> bool:
    d = carregar(login)
    for c in d["contas"]:
        if c["id"] == cid and c["estado"] == "aberta":
            c["estado"], c["fechada_em"] = estado, time.time()
            salvar(login, d)
            return True
    return False


@_transacao
def adiar_conta(login: str, cid: str) -> dict | None:
    d = carregar(login)
    for c in d["contas"]:
        if c["id"] == cid and c["estado"] == "aberta":
            c["lembrar_em"] = (agora().date() + dt.timedelta(days=1)).isoformat()
            salvar(login, d)
            return c
    return None


def mensagem_conta(c: dict, etapa: str) -> str:
    titulo = {"d3": "Conta chegando", "d1": "Conta vence amanhã", "d0": "Conta vence hoje"}.get(etapa, "Lembrete de conta")
    linhas = [f"💳 *{titulo}*", "", linha_conta(c)]
    if c.get("fonte"):
        linhas.append(f"_De: {c['fonte']}_")
    if c.get("codigo"):  # tap to copy in Telegram; paying is always the person's
        nome = "Pix copia e cola" if c["codigo"].startswith("000201") else "Linha digitável do boleto"
        linhas += ["", f"{nome} (toque para copiar):", f"```\n{c['codigo']}\n```"]
    return "\n".join(linhas)


def _dinheiro(c: dict) -> str:
    if not c.get("valor"):
        return ""
    simbolo = {"BRL": "R$", "USD": "US$", "EUR": "€"}.get(c["moeda"], c["moeda"])
    inteiro, _, centavos = c["valor"].partition(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    return f"{simbolo} {inteiro},{centavos or '00'}"


def linha_conta(c: dict) -> str:
    venc = dt.date.fromisoformat(c["vencimento"])
    dias = (venc - agora().date()).days
    quando = "venceu" if dias < 0 else "vence hoje" if dias == 0 else "vence amanhã" if dias == 1 else f"vence em {dias} dias"
    valor = _dinheiro(c)
    return f"{c['descricao']}{' — ' + valor if valor else ''} ({quando}, {venc.strftime('%d/%m')})"


def contas_abertas(login: str, dias: int = 30) -> list[dict]:
    hoje = agora().date()
    return sorted((c for c in carregar(login)["contas"] if c["estado"] == "aberta"
                   and (dt.date.fromisoformat(c["vencimento"]) - hoje).days <= dias),
                  key=lambda c: c["vencimento"])


@_transacao
def lembretes_de_contas(login: str) -> list[tuple[dict, str]]:
    """Bills to remind about now, once per stage: 3 days before, the day before, the day itself."""
    hoje = agora().date()
    d = carregar(login)
    saida = []
    for c in d["contas"]:
        if c["estado"] != "aberta":
            continue
        dias = (dt.date.fromisoformat(c["vencimento"]) - hoje).days
        etapa = "d0" if dias == 0 else "d1" if dias == 1 else "d3" if 2 <= dias <= 3 else ""
        if c.get("lembrar_em") and c["lembrar_em"] <= hoje.isoformat():  # "⏰ Amanhã" on an earlier reminder
            etapa = "adiado-" + c.pop("lembrar_em")
        if etapa and not c["lembrada"].get(etapa):
            c["lembrada"][etapa] = time.time()
            saida.append((c, etapa))
    if saida:
        salvar(login, d)
    return saida


@_transacao
def desfazer_lembrete(login: str, cid: str, etapa: str) -> bool:
    """The reminder did not reach the phone: unmark it so the next pass (2 min) tries again (12/10 review: the stage
    was marked before sending, so a failed send lost the reminder for good)."""
    d = carregar(login)
    for c in d["contas"]:
        if c["id"] == cid and c["lembrada"].pop(etapa, None) is not None:
            if etapa.startswith("adiado-"):
                c["lembrar_em"] = etapa.split("adiado-", 1)[1]
            salvar(login, d)
            return True
    return False


def botoes_conta(login: str, cid: str) -> list:
    base = f"ct:{_login(login)}:{cid}"
    return [{"id": f"{base}:paga", "titulo": "✅ Já paguei"}, {"id": f"{base}:amanha", "titulo": "⏰ Amanhã"},
            {"id": f"{base}:ignorar", "titulo": "🙈 Não é minha"}]


# ------------------------------------------------------------------ meetings (idea 2)

BRIEFING_SISTEMA = ("Você prepara um briefing de reunião em MODO SÓ LEITURA: pode ler e-mails, agenda, fios e memória, "
                    "mas não envia, responde, aceita, recusa nem altera nada.")


def _prompt_briefing(r: dict) -> str:
    return f"""Briefing para a reunião «{r['titulo']}» que começa às {r['inicio_txt']} ({FUSO}).
Participantes: {r.get('participantes') or '(não informados)'} · Local/link: {r.get('local') or '(não informado)'}

1. Com o conector `google` (user_google_email = falhanosistema1111@gmail.com), procure os e-mails recentes com esses participantes ou sobre esse assunto (últimos 60 dias) e a descrição do evento.
2. Veja os fios soltos ligados (ferramenta `fios`, acao "listar") e o que a memória sabe dessas pessoas e do assunto.
3. Resposta final (vai inteira para o celular dele), curta e organizada:
*Com quem:* quem é cada um em 1 linha (o que se sabe; não invente).
*Contexto:* o que já rolou (2–4 linhas).
*Pendências:* o que está em aberto dos dois lados.
*Vale perguntar/levar:* 2–3 pontos concretos.
Se não achar nada além do convite, diga isso em 2 linhas e sugira o que vale confirmar. Sem caminhos de pasta."""


def _prompt_pos(r: dict) -> str:
    return (f"A reunião «{r['titulo']}» acabou. Sua resposta final (vai ao celular dele) deve ser só esta pergunta, curta e "
            f"natural: \"📝 Como foi «{r['titulo']}»? Me conta (pode ser áudio) o que ficou combinado — quem faz o quê e "
            "até quando — que eu organizo os próximos passos e te lembro.\" Não faça mais nada.")


def _contexto_da_tarefa(tarefa, login: str) -> None:
    """Create the planned run's chat now, owned by `login`, so its answer reaches that person's phone (the scheduler
    would create it ownerless at run time, and an ownerless chat belongs to the default user)."""
    from agent import AgentContext
    from helpers.persist_chat import save_tmp_chat
    from initialize import initialize_agent

    ctx = AgentContext(initialize_agent(), id=tarefa.context_id or tarefa.uuid, name=tarefa.name)
    ctx.set_data("dono", _login(login))
    ctx.set_data("usuario", _login(login))
    save_tmp_chat(ctx)


async def _remover_tarefas(r: dict) -> None:
    from agent import AgentContext
    from helpers.task_scheduler import TaskScheduler

    agendador = TaskScheduler.get()
    for chave in ("tarefa_briefing", "tarefa_pos"):
        uid = r.pop(chave, None)
        if uid and agendador.get_task_by_uuid(uid):
            await agendador.remove_task_by_uuid(uid)
        if uid and AgentContext.get(uid):
            AgentContext.remove(uid)


async def cancelar_reuniao(login: str, evento_id: str) -> str:
    d = carregar(login)
    r = next((x for x in d["reunioes"] if x["evento_id"] == evento_id.strip()), None)
    if not r:
        return "Essa reunião não estava agendada."
    await _remover_tarefas(r)
    with _exclusivo(login):  # re-read after the awaits: apply only this change to the current state
        atual = carregar(login)
        atual["reunioes"] = [x for x in atual["reunioes"] if x["evento_id"] != r["evento_id"]]
        salvar(login, atual)
    return f"«{r['titulo']}» cancelada: briefing e pós-reunião removidos."


async def agendar_reuniao(login: str, evento_id: str, titulo: str, inicio: str, fim: str = "", participantes: str = "",
                          local: str = "") -> str:
    from helpers.task_scheduler import PlannedTask, TaskPlan, TaskScheduler

    ini, fim_dt = _data(inicio), _data(fim)
    if not evento_id.strip() or not titulo.strip() or ini is None:
        return "Diga `evento_id`, `titulo` e `inicio` (ISO com hora)."
    fim_dt = fim_dt if fim_dt and fim_dt > ini else ini + dt.timedelta(hours=1)
    agora_dt = agora()
    if fim_dt < agora_dt:
        return "Essa reunião já terminou."
    d = carregar(login)
    r = next((x for x in d["reunioes"] if x["evento_id"] == evento_id.strip()), None)
    agendador = TaskScheduler.get()
    if r and r.get("inicio_ts") == ini.timestamp() and r.get("fim_ts") == fim_dt.timestamp():
        return f"«{titulo}» já estava agendada (briefing e pós-reunião)."
    if r:  # time changed: drop the old runs
        await _remover_tarefas(r)
    else:
        r = {"evento_id": evento_id.strip()}
        d["reunioes"].append(r)
    r.update({"titulo": titulo.strip()[:120], "inicio_ts": ini.timestamp(), "fim_ts": fim_dt.timestamp(),
              "inicio_txt": ini.astimezone(_tz()).strftime("%d/%m %H:%M"), "participantes": participantes.strip()[:500],
              "local": local.strip()[:300], "pos_perguntado": 0, "pos_registrado": False})
    quando_briefing = max(ini - ANTES_DA_REUNIAO, agora_dt + dt.timedelta(minutes=1))
    feito = []
    if quando_briefing < ini - dt.timedelta(minutes=5):
        t = PlannedTask.create(name=f"📅 Briefing: {r['titulo']}"[:80], system_prompt=BRIEFING_SISTEMA,
                               prompt=_prompt_briefing(r), plan=TaskPlan.create(todo=[quando_briefing]))
        _contexto_da_tarefa(t, login)
        await agendador.add_task(t)
        r["tarefa_briefing"] = t.uuid
        feito.append(f"briefing às {quando_briefing.astimezone(_tz()).strftime('%d/%m %H:%M')}")
    t = PlannedTask.create(name=f"📝 Pós-reunião: {r['titulo']}"[:80], system_prompt="Você só faz uma pergunta curta.",
                           prompt=_prompt_pos(r), plan=TaskPlan.create(todo=[fim_dt + DEPOIS_DA_REUNIAO]))
    _contexto_da_tarefa(t, login)
    await agendador.add_task(t)
    r["tarefa_pos"] = t.uuid
    feito.append(f"pergunta do pós às {(fim_dt + DEPOIS_DA_REUNIAO).astimezone(_tz()).strftime('%H:%M')}")
    with _exclusivo(login):  # re-read after the awaits: apply only this meeting to the current state
        atual = carregar(login)
        atual["reunioes"] = [x for x in atual["reunioes"] if x["evento_id"] != r["evento_id"]] + [r]
        salvar(login, atual)
    await limpar_tarefas_antigas()
    return f"«{r['titulo']}»: " + " e ".join(feito) + "."


async def limpar_tarefas_antigas() -> None:
    """Remove finished briefing/follow-up runs older than 2 days so the task list stays readable."""
    from helpers.task_scheduler import PlannedTask, TaskScheduler, TaskState

    agendador = TaskScheduler.get()
    limite = time.time() - 2 * 86400
    for t in list(agendador.get_tasks()):
        if not isinstance(t, PlannedTask) or not t.name.startswith(("📅 Briefing:", "📝 Pós-reunião:")):
            continue
        if t.state != TaskState.RUNNING and not t.plan.todo and t.last_run and t.last_run.timestamp() < limite:
            await agendador.remove_task_by_uuid(t.uuid)


def pos_pendentes(login: str) -> list[dict]:
    """Meetings whose follow-up question went out in the last 24 h and whose answer was not recorded yet."""
    agora_ts = time.time()
    return [r for r in carregar(login)["reunioes"] if not r.get("pos_registrado")
            and 0 < agora_ts - (r["fim_ts"] + DEPOIS_DA_REUNIAO.total_seconds()) < 86400]


@_transacao
def registrar_pos(login: str, evento_id: str) -> bool:
    d = carregar(login)
    for r in d["reunioes"]:
        if r["evento_id"] == evento_id:
            r["pos_registrado"] = True
            salvar(login, d)
            return True
    return False


# ------------------------------------------------------------------ voice (idea 7)

def _falavel(texto: str) -> str:
    t = re.sub(r"https?://\S+", "", texto)
    t = re.sub(r"[*_`#>|~\[\]]", "", t)
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", t)
    t = re.sub(r"^\s*[-•]\s*", "", t, flags=re.M)
    return re.sub(r"\n{2,}", "\n", t).strip()


def vale_audio(texto: str) -> bool:
    """A voice note only when the summary has something to say ("nothing needs you today" is not worth one). 12/10
    review §6: the note repeats the text, so it also needs the day to ask something of him (a question, or a
    "Precisa de você" line) or to have 2+ items; one plain item is read faster than heard."""
    if len(_falavel(texto).split()) < 25 or "nada que precise de você" in texto.lower():
        return False
    linhas = [_falavel(l) for l in texto.splitlines() if _falavel(l)]
    if linhas and re.match(r"\W*bom dia", linhas[0], re.I):  # the title
        linhas = linhas[1:]
    pede = "?" in texto or any(re.match(r"\W*precisa de voc", l, re.I) for l in linhas)
    return pede or len(linhas) >= 2


def roteiro_falado(texto: str) -> str:
    """The summary rewritten to be heard (under a minute) by Luna; the cleaned text when that fails."""
    import urllib.request

    pedido = ("Reescreva este resumo como uma mensagem de voz curta e objetiva que uma assistente gravaria para o "
              "Matheus, em português do Brasil falado — do jeito que se fala, não do jeito que se escreve. Ele quer só o "
              "que importa: diga o que precisa dele e o que é de hoje; corte o resto. Regras: 50 a 110 palavras; comece "
              "com \"Bom dia, Matheus!\"; frases curtas, uma ideia por frase, ligadas como numa conversa (\"Primeiro…\", "
              "\"E hoje…\"); vírgulas onde se respira; nada de listas, símbolos, parênteses, links, siglas soletradas ou "
              "códigos (troque \"ROS-F5-006\" por \"a próxima etapa do IA Business\"); datas, horas e valores como se "
              "fala (\"amanhã às três da tarde\", \"cento e vinte e nove reais\"); termine numa frase curta. Responda "
              "só com o texto a ser falado.\n\n" + texto[:6000])
    body = {"model": "openai.gpt-6-luna", "reasoning": {"effort": "low"}, "input": [{"role": "user", "content": pedido}]}
    try:
        req = urllib.request.Request("http://host.docker.internal:8787/openai/v1/responses", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
        falado = "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                         for c in item.get("content", []) if c.get("type") == "output_text").strip()
        if falado:
            return _falavel(falado)[:2400]
    except Exception:
        pass
    return _falavel(texto)[:1500]


ULTIMA_VOZ: dict = {}  # engine/voice of the last voice note (checked by the tests)

# how the voice should say what it would mispronounce (checked by transcribing it back: "IA" came out as "ea")
PRONUNCIA = [(re.compile(r"\bIA\b"), "I.A."), (re.compile(r"\bIAs\b"), "I.As."), (re.compile(r"\bPDF\b"), "pê dê éfe")]


def pronuncia(texto: str) -> str:
    for padrao, falado in PRONUNCIA:
        texto = padrao.sub(falado, texto)
    return texto


def audio(texto: str, destino: Path) -> str:
    """Synthesize `texto` (Polly, voice Camila) into an OGG/Opus voice note at `destino`; '' or the error."""
    import base64
    import urllib.request

    try:  # the VM's proxy holds the AWS role (Polly); the container has no AWS credentials
        req = urllib.request.Request("http://host.docker.internal:8787/arquivos/voz", data=json.dumps({"texto": pronuncia(texto)}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            resposta = json.loads(r.read())
        destino.parent.mkdir(parents=True, exist_ok=True)
        mp3 = destino.with_suffix(".mp3")
        mp3.write_bytes(base64.b64decode(resposta["mp3"]))
        ULTIMA_VOZ.update({"motor": resposta.get("motor", ""), "voz": resposta.get("voz", ""), "texto": texto})
        saida = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-c:a", "libopus", "-b:a", "32k",
                                str(destino.with_suffix(".ogg"))], capture_output=True, timeout=120)
        mp3.unlink(missing_ok=True)
        return "" if saida.returncode == 0 else saida.stderr.decode()[:200]
    except Exception as exc:
        return str(exc)[:200]

"""Conversations the agent holds with stores, clinics and other businesses on WhatsApp, in the person's own WhatsApp
(WhatsApp Web in that person's browser profile), on the person's behalf (15/10: Ilia — "ache uma loja e use meu
WhatsApp pra perguntar se tem a peça", "procure clínicas e pergunte horários", and the conversation goes on, not only
the first message).

Rules (Matheus, 15/10: "pergunta e informa"):
- the agent asks and informs: prices, stock, hours, simple questions. Booking, reserving, accepting a price, paying or
  giving personal data only with the person's own confirmation (`confirmado`, the person's words), checked here;
- the first message to a business says it is the person's assistant (they talk to a program, they should know);
- limits protect the person's number: new conversations a day, messages a day per conversation, business hours;
- an open conversation is watched by code (job_loop, no model): the model only runs when the business answers.
State: /a0/usr/conversas_externas/<login>.json; every change goes through these functions.
"""

import datetime as dt
import json
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from zoneinfo import ZoneInfo

PASTA = Path(os.environ.get("CONVERSAS_EXTERNAS_PASTA", "/a0/usr/conversas_externas"))
FUSO = ZoneInfo("America/Bahia")
NOVAS_POR_DIA = 8          # new businesses contacted a day (a number that writes to many strangers gets banned)
MENSAGENS_POR_DIA = 20     # messages the agent sends a day in one conversation
HORARIO = (7, 21)          # local hours to write to a business
TAMANHO_MAX = 700
VIGIA = ((2 * 3600, 4 * 60), (24 * 3600, 15 * 60), (72 * 3600, 60 * 60))  # (since last activity, check every)
SILENCIO_ENCERRA = 72 * 3600  # no news for 3 days: closed, the person is told
ABERTAS = ("aberta", "esperando_dono")

_TRAVA = threading.RLock()


class Recusa(Exception):
    """A rule said no; the message says why, in words the agent can act on."""


def agora() -> float:
    return time.time()


def _hora_local(ts: float | None = None) -> int:
    return dt.datetime.fromtimestamp(ts or agora(), FUSO).hour


def _dia(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, FUSO).date().isoformat()


def _arquivo(login: str) -> Path:
    login = re.sub(r"[^a-z0-9_-]", "", str(login or "").lower())
    if not login:
        raise Recusa("conversa sem dono")
    return PASTA / f"{login}.json"


def carregar(login: str) -> dict:
    try:
        d = json.loads(_arquivo(login).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("conversas", [])
    d.setdefault("contexto_whatsapp", "")
    d.setdefault("numero", "")
    return d


def salvar(login: str, d: dict) -> None:
    arq = _arquivo(login)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(arq)


@contextmanager
def transacao(login: str):
    with _TRAVA:
        d = carregar(login)
        yield d
        salvar(login, d)


def telefone(t: str) -> str:
    """Digits with the country code (Brazil when it has none): 71 99735-6521 -> 5571997356521; "+7 916…" stays."""
    bruto = str(t or "").strip()
    dig = re.sub(r"\D", "", bruto)
    internacional = bruto.startswith("+") or dig.startswith("00")
    if dig.startswith("00"):
        dig = dig[2:]
    if len(dig) in (10, 11) and not internacional and not dig.startswith("55"):
        dig = "55" + dig
    if not 11 <= len(dig) <= 15:
        raise Recusa(f"telefone inválido: {t!r} (use DDD + número, ex.: 71 99735-6521)")
    return dig


def _conversa(d: dict, cid: str) -> dict:
    c = next((x for x in d["conversas"] if x["id"] == cid or x["telefone"] == re.sub(r"\D", "", str(cid))), None)
    if not c:
        raise Recusa(f"conversa {cid} não encontrada (veja acao \"listar\")")
    return c


# ------------------------------------------------------------------ what may be said
_DADO_PESSOAL = [
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "CPF"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "e-mail"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "número de cartão"),
    (re.compile(r"(?i)\b(rg|passaporte|cnh|data de nascimento|nascid[oa] em)\b"), "documento pessoal"),
]
_COMPROMISSO = re.compile(
    r"(?i)\b(confirm(o|ado|amos)|pode (marcar|agendar|reservar|separar|fechar|mandar)|quero (marcar|agendar|reservar|"
    r"comprar|fechar)|vou querer|(est[aá] )?fechado|fechamos|reserv[ae] (pra|para) (mim|ele)|pode fazer o pedido|"
    r"(vou|vamos) pagar|segue o pix|paguei|aceito)\b")


def validar(texto: str, primeira: bool, confirmado: str = "", nome_dono: str = "") -> str:
    """'' or why this message cannot go to the business."""
    t = str(texto or "").strip()
    if len(t) < 2:
        return "mensagem vazia"
    if len(t) > TAMANHO_MAX:
        return f"mensagem longa demais ({len(t)} caracteres; até {TAMANHO_MAX}): seja curto, como no WhatsApp"
    if primeira and "assistente" not in t.lower():
        return (f"a primeira mensagem diz que é o assistente de {nome_dono or 'quem pediu'} (ex.: \"Olá! Sou o assistente "
                f"de {nome_dono or 'Fulano'}. Vocês têm...?\")")
    if not str(confirmado or "").strip():
        for padrao, nome in _DADO_PESSOAL:
            if padrao.search(t):
                return (f"a mensagem passa {nome} da pessoa: só com a confirmação dela. Pergunte a ela antes e chame de "
                        "novo com `confirmado` = as palavras dela")
        m = _COMPROMISSO.search(t)
        if m:
            return (f"«{m.group(0)}» compromete a pessoa (marcar, reservar, aceitar preço, pagar): pergunte a ela antes "
                    "e chame de novo com `confirmado` = as palavras dela")
    return ""


# ------------------------------------------------------------------ conversations
def abrir(login: str, nome: str, tel: str, objetivo: str, ts: float | None = None) -> dict:
    """A new conversation (or the open one with the same number). The first message goes with `enviar`."""
    ts = ts or agora()
    numero = telefone(tel)
    nome, objetivo = str(nome or "").strip()[:80], str(objetivo or "").strip()[:400]
    if not objetivo:
        raise Recusa("diga o objetivo da conversa (o que a pessoa quer saber ou resolver)")
    with transacao(login) as d:
        aberta = next((x for x in d["conversas"] if x["telefone"] == numero and x["estado"] in ABERTAS), None)
        if aberta:
            return aberta
        hoje = sum(1 for x in d["conversas"] if _dia(x["criada"]) == _dia(ts))
        if hoje >= NOVAS_POR_DIA:
            raise Recusa(f"já são {hoje} contatos novos hoje (limite {NOVAS_POR_DIA}, protege o número da pessoa): "
                         "continue amanhã ou com os que já estão abertos")
        c = {"id": "ce" + secrets.token_hex(3), "nome": nome or numero, "telefone": numero, "objetivo": objetivo,
             "estado": "aberta", "criada": ts, "ultima_atividade": ts, "ultima_verificacao": 0.0,
             "mensagens": [], "vistas": []}
        d["conversas"].append(c)
        return c


def pode_enviar(login: str, cid: str, texto: str, confirmado: str = "", nome_dono: str = "",
                ts: float | None = None) -> dict:
    """The conversation, when this text may go now; Recusa otherwise."""
    ts = ts or agora()
    d = carregar(login)
    c = _conversa(d, cid)
    if c["estado"] not in ABERTAS:
        raise Recusa(f"a conversa com {c['nome']} está encerrada ({c['estado']}); abra outra se precisar")
    if not HORARIO[0] <= _hora_local(ts) < HORARIO[1]:
        raise Recusa(f"fora do horário comercial ({HORARIO[0]}h–{HORARIO[1]}h): mande a partir das {HORARIO[0]}h")
    hoje = sum(1 for m in c["mensagens"] if m["de"] == "eu" and _dia(m["em"]) == _dia(ts))
    if hoje >= MENSAGENS_POR_DIA:
        raise Recusa(f"já foram {hoje} mensagens hoje para {c['nome']}: espere a resposta ou continue amanhã")
    primeira = not any(m["de"] == "eu" for m in c["mensagens"])
    motivo = validar(texto, primeira, confirmado, nome_dono)
    if motivo:
        raise Recusa(motivo)
    return c


def registrar_envio(login: str, cid: str, texto: str, confirmado: str = "", ts: float | None = None) -> dict:
    ts = ts or agora()
    with transacao(login) as d:
        c = _conversa(d, cid)
        c["mensagens"].append({"de": "eu", "texto": str(texto)[:TAMANHO_MAX], "em": ts,
                               **({"confirmado": str(confirmado)[:300]} if confirmado else {})})
        c["ultima_atividade"], c["estado"] = ts, "aberta"
        return c


def registrar_lidas(login: str, cid: str, lidas: list, ts: float | None = None) -> list:
    """Messages read on the screen ({id, de: eu|eles, texto, hora}); returns the business's ones not seen before.
    The first read of a conversation only marks what was already there (old history is not news)."""
    ts = ts or agora()
    with transacao(login) as d:
        c = _conversa(d, cid)
        vistas = set(c.get("vistas") or [])
        primeira_leitura = not c.get("lida_uma_vez")
        novas = []
        for m in lidas or []:
            mid = str(m.get("id") or "")
            if not mid or mid in vistas:
                continue
            vistas.add(mid)
            if m.get("de") == "eles" and not primeira_leitura:
                texto = str(m.get("texto") or "").strip()[:2000]
                novas.append({"id": mid, "texto": texto, "hora": str(m.get("hora") or "")})
                c["mensagens"].append({"de": "eles", "texto": texto, "em": ts, "id": mid})
        if primeira_leitura and any(m.get("de") == "eu" for m in c["mensagens"]):
            c["lida_uma_vez"] = True  # history before our first message was marked; from now on it is news
        c["vistas"] = sorted(vistas)[-400:]
        c["ultima_verificacao"] = ts
        if novas:
            c["ultima_atividade"] = ts
        return novas


def encerrar(login: str, cid: str, motivo: str = "concluída", ts: float | None = None) -> dict:
    with transacao(login) as d:
        c = _conversa(d, cid)
        c["estado"], c["encerrada_em"], c["motivo"] = "encerrada", ts or agora(), str(motivo)[:200]
        return c


def esperar_dono(login: str, cid: str, pergunta: str, ts: float | None = None) -> dict:
    with transacao(login) as d:
        c = _conversa(d, cid)
        c["estado"], c["pergunta_ao_dono"] = "esperando_dono", str(pergunta)[:400]
        c["ultima_atividade"] = ts or agora()
        return c


def devidas(login: str, ts: float | None = None) -> tuple[list, list]:
    """(conversations to check now, conversations just closed for silence)."""
    ts = ts or agora()
    checar, fechadas = [], []
    with transacao(login) as d:
        for c in d["conversas"]:
            if c["estado"] not in ABERTAS or not any(m["de"] == "eu" for m in c["mensagens"]):
                continue
            parado = ts - float(c.get("ultima_atividade") or c["criada"])
            if parado > SILENCIO_ENCERRA:
                c["estado"], c["encerrada_em"], c["motivo"] = "encerrada", ts, "sem resposta em 3 dias"
                fechadas.append(dict(c))
                continue
            intervalo = next((cada for ate, cada in VIGIA if parado <= ate), VIGIA[-1][1])
            if ts - float(c.get("ultima_verificacao") or 0) >= intervalo:
                checar.append(dict(c))
    return checar, fechadas


def logins() -> list[str]:
    return sorted(p.stem for p in PASTA.glob("*.json")) if PASTA.exists() else []


def resumo(c: dict, n: int = 6) -> str:
    linhas = [f"{'Você' if m['de'] == 'eu' else c['nome']}: {m['texto'][:300]}" for m in c["mensagens"][-n:]]
    return "\n".join(linhas)


def aviso_ao_agente(c: dict, novas: list, nome_dono: str) -> str:
    """What the person's chat receives when the business answered (the model runs only then)."""
    falas = "\n".join(f"«{m['texto']}»" for m in novas)
    return (f"[Conversa externa {c['id']} — {c['nome']} respondeu no WhatsApp de {nome_dono}]\n{falas}\n\n"
            f"Objetivo: {c['objetivo']}\nÚltimas mensagens:\n{resumo(c)}\n\n"
            f"O que fazer: se a resposta pede algo que só {nome_dono} decide (marcar, reservar, aceitar preço, pagar, dado "
            f"pessoal), NÃO responda à loja: conte a {nome_dono} o que disseram e pergunte, e chame `conversa_externa` acao "
            f"\"esperar_dono\". Se der para seguir dentro do objetivo, responda à loja com acao \"enviar\" (curto, na "
            f"língua da loja). Se o objetivo foi atingido, conte o resultado a {nome_dono} (na língua dele) e chame "
            f"acao \"encerrar\". Em todo caso, termine com um resumo curto para {nome_dono}.")


def aviso_silencio(c: dict) -> str:
    return (f"Encerrei a conversa com {c['nome']} ({c['objetivo'][:80]}): sem resposta em 3 dias. "
            "Se quiser, peça para eu tentar outra loja.")


# ------------------------------------------------------------------ scripts run in the WhatsApp Web tab
# Checked on the real WhatsApp Web (15/10, English UI of the agent's browser): the login page says "Log in with phone
# number" / "Link with phone number instead."; a plain .click() does nothing there, the full pointer/mouse sequence
# works; the phone field starts with "+1 " (United States) and typing "+55…" after clearing it switches to Brazil.
_CLICAR = r"""const clicar = (re) => {
  const el = [...document.querySelectorAll('span, div, button, a')].filter(e => re.test((e.innerText || '').trim())
    && ![...e.children].some(c => re.test((c.innerText || '').trim())))[0];
  if (!el) return 'não achei';
  const alvo = el.closest('[role="button"], button, a') || el;
  const r = alvo.getBoundingClientRect(); const x = r.x + r.width / 2, y = r.y + r.height / 2;
  for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'])
    alvo.dispatchEvent(new (t.startsWith('pointer') ? PointerEvent : MouseEvent)(t, {bubbles: true, cancelable: true, clientX: x, clientY: y, view: window}));
  return 'clicado';
};"""

SCRIPT_ESTADO = r"""(() => {
  const txt = (document.body && document.body.innerText) || '';
  const tem = (s) => !!document.querySelector(s);
  const el = document.querySelector('[data-link-code]');
  let codigo = el ? el.getAttribute('data-link-code') : '';
  if (!codigo && /(enter code|insira o c[oó]digo|digite o c[oó]digo|c[oó]digo no (seu )?celular|code on (your )?phone)/i.test(txt)) {
    const m = txt.replace(/\s+/g, ' ').match(/\b([A-Z0-9]{4})[ -]?([A-Z0-9]{4})\b/);
    codigo = m ? m[1] + m[2] : '';
  }
  const invalido = /(inv[aá]lido|invalid)/i.test(txt) && /(url|n[uú]mero|phone)/i.test(txt) && !tem('#main');
  return JSON.stringify({
    logado: tem('#pane-side') || tem('[aria-label="Chat list"]') || tem('[aria-label="Lista de conversas"]') || tem('#side'),
    conversa_aberta: tem('#main'),
    codigo: (codigo || '').replace(/[, -]/g, ''),
    pede_numero: tem('input[aria-label*="phone" i]') || tem('input[aria-label*="telefone" i]'),
    qr: tem('canvas[aria-label]') || tem('[data-ref]') || /scan (the qr|to log in)|escaneie|ler o (c[oó]digo )?qr/i.test(txt),
    invalido: invalido,
    titulo: document.title
  });
})()"""
SCRIPT_MENSAGENS = r"""(() => {
  const main = document.querySelector('#main');
  if (!main) return JSON.stringify({erro: 'conversa não aberta'});
  const linhas = [...main.querySelectorAll('[data-id]')].filter(el => /^(true|false)_/.test(el.getAttribute('data-id')));
  const vistos = new Set(); const out = [];
  for (const el of linhas) {
    const id = el.getAttribute('data-id'); if (vistos.has(id)) continue; vistos.add(id);
    const pre = el.querySelector('[data-pre-plain-text]');
    const corpo = el.querySelector('.selectable-text') || el.querySelector('.copyable-text') || el;
    let texto = (corpo.innerText || '').trim();
    if (!texto) texto = el.querySelector('img') ? '[imagem]' : (el.querySelector('audio,[data-icon*="audio"],[data-icon*="ptt"]') ? '[áudio]' : '');
    if (!texto) continue;
    out.push({id, de: id.startsWith('true_') ? 'eu' : 'eles', texto: texto.slice(0, 2000),
              hora: pre ? pre.getAttribute('data-pre-plain-text').replace(/\].*$/, '').replace('[', '') : ''});
  }
  if (!out.length) return JSON.stringify({mensagens: [], texto_da_tela: (main.innerText || '').slice(-3000)});
  return JSON.stringify({mensagens: out.slice(-40)});
})()"""

SCRIPT_ENVIAR = r"""(() => {
  const main = document.querySelector('#main');
  if (!main) return 'sem conversa';
  const caixa = main.querySelector('footer [contenteditable="true"]');
  if (!caixa || !(caixa.innerText || '').trim()) return 'caixa vazia';
  const alvo = main.querySelector('[data-icon="send"], [data-icon="wds-ic-send-filled"], button[aria-label="Send"], button[aria-label="Enviar"]');
  if (!alvo) { caixa.focus(); return 'foco'; }
  (alvo.closest('button') || alvo).click();
  return 'clicado';
})()"""

SCRIPT_ENTRAR_COM_NUMERO = "(() => {" + _CLICAR + r"""
  return clicar(/^(log in|link) with phone number( instead)?\.?$|^(entrar|conectar)( com o| com)? n[uú]mero de telefone( em vez disso)?\.?$/i);
})()"""

SCRIPT_CAMPO_TELEFONE = r"""(() => {
  const campo = document.querySelector('input[aria-label*="phone" i], input[aria-label*="telefone" i]');
  if (!campo) return 'sem campo';
  campo.focus();
  return 'foco';
})()"""

SCRIPT_VALOR_TELEFONE = r"""(() => { const c = document.querySelector('input[aria-label*="phone" i], input[aria-label*="telefone" i]');
  return c ? c.value : ''; })()"""

SCRIPT_AVANCAR = "(() => {" + _CLICAR + r"""
  return clicar(/^(next|avançar|próximo|seguinte)$/i);
})()"""

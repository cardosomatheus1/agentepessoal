"""Telegram bot channel: always reachable, even while the VM sleeps (same flow as WhatsApp).

POST /telegram/<caminho>  Telegram's webhook (also checked by X-Telegram-Bot-Api-Secret-Token).
                          Messages from linked chats are queued in SQS for ponte_whatsapp and the
                          VM is started if it is off (with an immediate "waking up" reply).
Linking: on the control page (behind the personal key), "Conectar <login>" makes a fresh link t.me/<bot>?start=<code>;
opening it sends "/start <code>", which binds that Telegram chat to the login. Unknown chats are ignored.
12/10 review: the codes never expired and could be reused, so whoever saw a link became that login in the bot. Now a
code is good for one use within 15 minutes, and the chats already linked to the login are told when a new one joins
("Desconectar" on the control page unlinks all of a login's chats).

Settings live in the same SSM SecureString as WhatsApp: "tg_token", "tg_segredo", "tg_bot",
"tg_codigos" {code: {"login", "ate"}}, "tg_chats" {chat_id: login}.
"""

import hmac
import json
import secrets
import time
import urllib.request

import whatsapp

ACORDANDO = "⏳ Acordando o agente… já te respondo (leva cerca de 1 minuto)."
VALIDADE = 15 * 60  # a link code is good for 15 minutes, once


def api(metodo: str, dados: dict) -> dict:
    cfg = whatsapp.config()
    req = urllib.request.Request(f"https://api.telegram.org/bot{cfg['tg_token']}/{metodo}",
                                 data=json.dumps(dados).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def configurar(token: str, base_url: str, logins: list[str]) -> dict:
    """Save the bot token, point Telegram's webhook here and make one link code per login."""
    cfg_novo = dict(whatsapp.save_config({}))  # makes sure the secret path exists
    if token.strip():
        cfg_novo["tg_token"] = token.strip()
    cfg_novo.setdefault("tg_segredo", secrets.token_urlsafe(24))
    cfg_novo.setdefault("tg_chats", {})
    cfg_novo["tg_codigos"] = {}  # links are made on demand now (novo_link), 15 minutes, one use
    whatsapp.gravar(cfg_novo)
    eu = api("getMe", {})
    cfg_novo["tg_bot"] = (eu.get("result") or {}).get("username", "")
    whatsapp.gravar(cfg_novo)
    api("setWebhook", {"url": f"{base_url.rstrip('/')}/telegram/{cfg_novo['caminho']}",
                       "secret_token": cfg_novo["tg_segredo"],
                       "allowed_updates": ["message", "callback_query"], "drop_pending_updates": True})
    return status()


def status(logins: tuple = ("matheus", "fernanda")) -> dict:
    cfg = whatsapp.config()
    chats = list((cfg.get("tg_chats") or {}).values())
    return {"tg_bot": cfg.get("tg_bot", ""), "tg_logins": list(logins), "tg_ligados": sorted(set(chats)),
            "tg_chats_por_login": {l: chats.count(l) for l in sorted(set(chats))},
            "tem_tg_token": bool(cfg.get("tg_token"))}


def _validos(codigos: dict, agora: float) -> dict:
    """Codes still good (the old permanent ones, plain strings, are not)."""
    return {c: v for c, v in (codigos or {}).items() if isinstance(v, dict) and float(v.get("ate") or 0) > agora}


def novo_link(login: str, agora: float | None = None) -> str:
    """A fresh link for the login: one use, 15 minutes. An older unused code of the same login stops working."""
    agora = agora or time.time()
    cfg = dict(whatsapp.config(fresca=True))
    if not cfg.get("tg_bot"):
        raise ValueError("bot do Telegram ainda não configurado")
    codigos = {c: v for c, v in _validos(cfg.get("tg_codigos"), agora).items() if v.get("login") != login}
    codigo = secrets.token_urlsafe(12)  # letters, digits, "-" and "_": what Telegram accepts in ?start=
    codigos[codigo] = {"login": login, "ate": agora + VALIDADE}
    cfg["tg_codigos"] = codigos
    whatsapp.gravar(cfg)
    return f"https://t.me/{cfg['tg_bot']}?start={codigo}"


def desligar(login: str) -> int:
    """Unlink every Telegram chat of the login (control page). Returns how many."""
    cfg = dict(whatsapp.config(fresca=True))
    chats = dict(cfg.get("tg_chats") or {})
    fora = [c for c, l in chats.items() if l == login]
    for c in fora:
        chats.pop(c)
    cfg["tg_chats"] = chats
    whatsapp.gravar(cfg)
    return len(fora)


def vincular(cfg: dict, chat: str, codigo: str, quem: str, agora: float | None = None) -> tuple[str, list]:
    """/start <code>: binds the chat when the code is good, and spends it in the same write. Returns the login (or "")
    and the chats already linked to it, which are told about the new one."""
    agora = agora or time.time()
    codigos = _validos(cfg.get("tg_codigos"), agora)
    dado = codigos.pop(codigo, None) if codigo else None
    if not dado:
        return "", []
    login = dado["login"]
    chats = dict(cfg.get("tg_chats") or {})
    antigos = [c for c, l in chats.items() if l == login and c != chat]
    chats[chat] = login
    cfg["tg_chats"], cfg["tg_codigos"] = chats, codigos
    whatsapp.gravar(cfg)
    for c in antigos:
        try:
            api("sendMessage", {"chat_id": c, "text": f"🔔 Outro chat do Telegram acabou de ser ligado ao seu agente "
                                                      f"({quem}). Se não foi você: página de controle → Telegram → "
                                                      "Desconectar, e conecte de novo só este chat."})
        except Exception as exc:
            print(f"telegram: new-link notice failed: {exc}")
    return login, antigos


def receive(raw: bytes, headers: dict, vm_state, start_vm, start_vm_later) -> dict:
    cfg = whatsapp.config()
    if not cfg.get("tg_segredo") or not hmac.compare_digest(
            headers.get("x-telegram-bot-api-secret-token", ""), cfg["tg_segredo"]):
        return whatsapp._text("forbidden", 403)
    try:
        update = json.loads(raw)
    except ValueError:
        return whatsapp._text("ok")

    msg = update.get("message") or {}
    botao = update.get("callback_query") or {}
    chat = str(((msg.get("chat") or {}).get("id")) or ((botao.get("message") or {}).get("chat") or {}).get("id") or "")
    if not chat:
        return whatsapp._text("ok")

    texto = (msg.get("text") or "").strip()
    if texto.startswith("/start") or chat not in (cfg.get("tg_chats") or {}):
        cfg = whatsapp.config(fresca=True)  # another Lambda instance may have just saved a code or link
    if texto.startswith("/start"):
        codigo = texto.split(" ", 1)[1].strip() if " " in texto else ""
        de = msg.get("from") or {}
        quem = " ".join(x for x in (de.get("first_name"), de.get("last_name")) if x) or "sem nome"
        if de.get("username"):
            quem += f", @{de['username']}"
        login, _ = vincular(dict(cfg), chat, codigo, quem)
        if login:
            api("sendMessage", {"chat_id": chat, "text": f"✅ Pronto, {login}! Este chat agora fala com o seu agente. "
                                                         "Mande texto, áudio, foto ou arquivo. /ajuda mostra os comandos."})
        elif chat not in (cfg.get("tg_chats") or {}):
            api("sendMessage", {"chat_id": chat, "text": "Este bot é privado. Se você é o dono, gere um link novo na "
                                                         "página de controle (vale 15 minutos, uma vez)."})
        return whatsapp._text("ok")

    usuario = (cfg.get("tg_chats") or {}).get(chat)
    if not usuario:
        print(f"telegram: ignored update from unlinked chat …{chat[-4:]}")
        return whatsapp._text("ok")

    whatsapp.sqs.send_message(QueueUrl=whatsapp.QUEUE_URL, MessageBody=json.dumps(
        {"canal": "telegram", "usuario": usuario, "chat": chat, "update": update, "recebida": time.time()},
        ensure_ascii=False))
    estado = vm_state()
    if estado in ("stopped", "stopping"):
        start_vm() if estado == "stopped" else start_vm_later()
        try:
            api("sendMessage", {"chat_id": chat, "text": ACORDANDO})
        except Exception as exc:
            print(f"telegram: waking notice failed: {exc}")
    return whatsapp._text("ok")

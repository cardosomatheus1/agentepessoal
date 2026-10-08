"""Telegram bot channel: always reachable, even while the VM sleeps (same flow as WhatsApp).

POST /telegram/<caminho>  Telegram's webhook (also checked by X-Telegram-Bot-Api-Secret-Token).
                          Messages from linked chats are queued in SQS for ponte_whatsapp and the
                          VM is started if it is off (with an immediate "waking up" reply).
Linking: the control page shows one link per login, t.me/<bot>?start=<code>; opening it sends
"/start <code>", which binds that Telegram chat to the login. Unknown chats are ignored.

Settings live in the same SSM SecureString as WhatsApp: "tg_token", "tg_segredo", "tg_bot",
"tg_codigos" {code: login}, "tg_chats" {chat_id: login}.
"""

import hmac
import json
import secrets
import time
import urllib.request

import whatsapp

ACORDANDO = "⏳ Acordando o agente… já te respondo (leva cerca de 1 minuto)."


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
    codigos = cfg_novo.get("tg_codigos") or {}
    for login in logins:
        if login not in codigos.values():
            codigos[secrets.token_hex(6)] = login
    cfg_novo["tg_codigos"] = codigos
    whatsapp.gravar(cfg_novo)
    eu = api("getMe", {})
    cfg_novo["tg_bot"] = (eu.get("result") or {}).get("username", "")
    whatsapp.gravar(cfg_novo)
    api("setWebhook", {"url": f"{base_url.rstrip('/')}/telegram/{cfg_novo['caminho']}",
                       "secret_token": cfg_novo["tg_segredo"],
                       "allowed_updates": ["message", "callback_query"], "drop_pending_updates": True})
    return status()


def status() -> dict:
    cfg = whatsapp.config()
    bot = cfg.get("tg_bot", "")
    links = {login: f"https://t.me/{bot}?start={codigo}" for codigo, login in (cfg.get("tg_codigos") or {}).items()} if bot else {}
    ligados = sorted(set((cfg.get("tg_chats") or {}).values()))
    return {"tg_bot": bot, "tg_links": links, "tg_ligados": ligados, "tem_tg_token": bool(cfg.get("tg_token"))}


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
    if texto.startswith("/start"):
        codigo = texto.split(" ", 1)[1].strip() if " " in texto else ""
        login = (cfg.get("tg_codigos") or {}).get(codigo)
        if login:
            chats = dict(cfg.get("tg_chats") or {})
            chats[chat] = login
            cfg["tg_chats"] = chats
            whatsapp.gravar(cfg)
            api("sendMessage", {"chat_id": chat, "text": f"✅ Pronto, {login}! Este chat agora fala com o seu agente. "
                                                         "Mande texto, áudio, foto ou arquivo. /ajuda mostra os comandos."})
        elif chat not in (cfg.get("tg_chats") or {}):
            api("sendMessage", {"chat_id": chat, "text": "Este bot é privado."})
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

"""WhatsApp Cloud API webhook: always reachable, even while the VM sleeps.

GET  /whatsapp/<caminho>  Meta's subscription check (hub.verify_token).
POST /whatsapp/<caminho>  Messages: kept only from registered numbers, queued in SQS for the VM's
                          ponte_whatsapp, and the VM is started if it is off (with an immediate
                          "waking up" reply so the user is not left waiting in silence).

<caminho> is a random secret only Meta knows (set in the app's webhook settings); when the app
secret is configured too, Meta's X-Hub-Signature-256 is also checked.

Settings live in the SSM SecureString CONFIG_PARAM, filled from the control page (behind the
personal key), so the token, the app secret and the numbers never go through any chat:
{"token", "app_secret", "phone_number_id", "verify_token", "caminho", "numeros": {"5571...": "matheus"}}
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import time
import urllib.request

import boto3

CONFIG_PARAM = os.environ.get("WHATSAPP_PARAM", "/agentepessoal/whatsapp/config")
QUEUE_URL = os.environ.get("WHATSAPP_QUEUE_URL", "")
GRAPH = "https://graph.facebook.com/v23.0"
ACORDANDO = "⏳ Acordando o agente… já te respondo (leva cerca de 1 minuto)."

ssm = boto3.client("ssm")
sqs = boto3.client("sqs")
_config: dict = {}
_config_at = 0.0


def config() -> dict:
    global _config, _config_at
    if not _config or time.time() - _config_at > 300:
        try:
            raw = ssm.get_parameter(Name=CONFIG_PARAM, WithDecryption=True)["Parameter"]["Value"]
            _config, _config_at = json.loads(raw), time.time()
        except Exception as exc:
            print(f"whatsapp: no config: {exc}")
            _config = {}
    return _config


def save_config(updates: dict) -> dict:
    """Merge the control page's fields into the settings; blank fields keep what is there."""
    global _config, _config_at
    cfg = dict(config())
    cfg.setdefault("verify_token", secrets.token_urlsafe(24))
    cfg.setdefault("caminho", secrets.token_urlsafe(24))
    cfg.setdefault("caminho_gatilhos", secrets.token_urlsafe(24))
    for campo in ("token", "app_secret", "phone_number_id", "modelo_aviso", "base_url"):
        valor = str(updates.get(campo) or "").strip()
        if valor:
            cfg[campo] = valor
    if str(updates.get("numeros") or "").strip():
        numeros = {}
        for linha in str(updates["numeros"]).splitlines():  # "matheus = +55 71 99999-0000"
            if "=" not in linha:
                continue
            login, numero = (x.strip() for x in linha.split("=", 1))
            numero = re.sub(r"\D", "", numero)
            if login and len(numero) >= 10:
                numeros[numero] = login.lower()
        cfg["numeros"] = numeros
    ssm.put_parameter(Name=CONFIG_PARAM, Value=json.dumps(cfg), Type="SecureString", Overwrite=True)
    _config, _config_at = cfg, time.time()
    return cfg


def status(base_url: str) -> dict:
    cfg = config()
    if not cfg.get("caminho_gatilhos") or cfg.get("base_url") != base_url.rstrip("/"):
        cfg = save_config({"base_url": base_url.rstrip("/")})  # the VM builds trigger URLs from it
    return {
        "webhook": f"{base_url.rstrip('/')}/whatsapp/{cfg['caminho']}",
        "verify_token": cfg["verify_token"],
        "tem_token": bool(cfg.get("token")),
        "tem_segredo": bool(cfg.get("app_secret")),
        "phone_number_id": cfg.get("phone_number_id", ""),
        "numeros": "\n".join(f"{login} = …{numero[-4:]}" for numero, login in (cfg.get("numeros") or {}).items()),
    }


def caminho_ok(path: str) -> bool:
    esperado = config().get("caminho", "")
    return bool(esperado) and hmac.compare_digest(path.rstrip("/").rsplit("/", 1)[-1], esperado)


def gatilho(path: str, raw: bytes, vm_state, start_vm, start_vm_later) -> dict:
    """POST /gatilho/<caminho_gatilhos>/<login>/<nome>: any service fires one of the agent's
    triggers; the body (up to 20k chars) goes to that person's "Gatilhos" chat and the VM wakes."""
    partes = path.strip("/").split("/")
    cfg = config()
    esperado = cfg.get("caminho_gatilhos", "")
    if len(partes) != 4 or not esperado or not hmac.compare_digest(partes[1], esperado):
        return _text("not found", 404)
    usuario, nome = partes[2].lower(), partes[3]
    if not re.fullmatch(r"[a-z0-9_]{1,40}", usuario) or not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", nome):
        return _text("bad request", 400)
    conteudo = raw.decode("utf-8", "replace")[:20000]
    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(
        {"gatilho": nome, "usuario": usuario, "conteudo": conteudo, "recebida": time.time()}, ensure_ascii=False))
    estado = vm_state()
    if estado == "stopped":
        start_vm()
    elif estado == "stopping":
        start_vm_later()
    return _text("ok")


def _text(body: str, code: int = 200) -> dict:
    return {"statusCode": code, "headers": {"Content-Type": "text/plain"}, "body": body}


def verify(params: dict) -> dict:
    cfg = config()
    if (params.get("hub.mode") == "subscribe" and cfg.get("verify_token")
            and hmac.compare_digest(params.get("hub.verify_token", ""), cfg["verify_token"])):
        return _text(params.get("hub.challenge", ""))
    return _text("forbidden", 403)


def _signed(raw: bytes, header: str, secret: str) -> bool:
    if not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[len("sha256="):], expected)


def send_text(numero: str, texto: str) -> None:
    cfg = config()
    body = {"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": texto}}
    req = urllib.request.Request(
        f"{GRAPH}/{cfg['phone_number_id']}/messages",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=8).read()
    except Exception as exc:
        print(f"whatsapp: reply failed: {exc}")


def receive(raw: bytes, headers: dict, vm_state, start_vm, start_vm_later) -> dict:
    """vm_state() -> EC2 state name; start_vm() starts the instance now; start_vm_later() once
    it has finished hibernating (a stopping instance cannot be started)."""
    cfg = config()
    if cfg.get("app_secret") and not _signed(raw, headers.get("x-hub-signature-256", ""), cfg["app_secret"]):
        return _text("bad signature", 401)
    try:
        payload = json.loads(raw)
    except ValueError:
        return _text("bad request", 400)

    numeros = cfg.get("numeros") or {}
    novos = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            nomes = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in value.get("contacts", [])}
            for msg in value.get("messages", []):
                numero = msg.get("from", "")
                usuario = numeros.get(numero)
                if not usuario:  # only the registered people talk to the agent
                    print(f"whatsapp: ignored message from unregistered number ending {numero[-4:]}")
                    continue
                novos.append({"usuario": usuario, "numero": numero, "nome": nomes.get(numero, ""),
                              "mensagem": msg, "recebida": time.time()})
    if not novos:
        return _text("ok")

    for item in novos:
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(item, ensure_ascii=False))

    estado = vm_state()
    if estado in ("stopped", "stopping"):
        start_vm() if estado == "stopped" else start_vm_later()
        for numero in {i["numero"] for i in novos}:
            send_text(numero, ACORDANDO)
    return _text("ok")

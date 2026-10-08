"""Bridge between WhatsApp (Meta Cloud API) and Agent Zero, running on the VM host.

In:  the control function queues each message from a registered number in SQS (it works with
     the VM asleep and starts it). Here the queue is long-polled; media (audio, photos, files)
     is downloaded next to the chats and the message goes to the whatsapp plugin inside Agent
     Zero (POST /api/plugins/whatsapp/receber), which transcribes audio and talks to the agent.
Out: the plugin asks for messages to be sent through POST :8789/enviar. Only registered
     people are reachable, by user name: the agent never sees numbers or the Meta token.

Both directions carry a shared key (/opt/a0/usr/whatsapp/.chave, created here). Settings (token,
phone number id, numbers) come from the SSM SecureString /agentepessoal/whatsapp/config.
"""

import http.server
import json
import mimetypes
import os
import secrets
import threading
import time
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
PARAM = os.environ.get("WHATSAPP_PARAM", "/agentepessoal/whatsapp/config")
QUEUE = os.environ.get("WHATSAPP_QUEUE", "agentepessoal-whatsapp")
A0 = os.environ.get("A0_URL", "http://127.0.0.1:50080")
LISTEN = ("0.0.0.0", 8789)  # reached from the container as host.docker.internal; no inbound rule
GRAPH = "https://graph.facebook.com/v23.0"
USR_HOST, USR_A0 = Path("/opt/a0/usr"), "/a0/usr"
PASTA = USR_HOST / "whatsapp"
CHAVE = PASTA / ".chave"
VISTOS = Path("/var/lib/agentepessoal/whatsapp_vistos.json")
ATIVIDADE = Path("/var/lib/agentepessoal/last-activity")
LIMITE_TEXTO = 3800  # WhatsApp allows 4096 per message
USO = Path("/var/lib/agentepessoal/uso.jsonl")  # every model call, written by bedrock_proxy
ALERTA = Path("/var/lib/agentepessoal/alerta_gasto.json")
# US$ per million tokens: input, cached input (1/10), output; cache writes cost 1.25x input
PRECOS = {"sol": (2.20, 0.22, 11.0), "luna": (0.11, 0.011, 0.55)}
LIMITE_DIA_PADRAO = 15.0  # US$; cfg "limite_dia_usd" overrides

ssm = boto3.client("ssm", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)
_cfg: dict = {}
_cfg_em = 0.0


def log(msg: str) -> None:
    print(f"ponte_whatsapp: {msg}", flush=True)


def cfg() -> dict:
    global _cfg, _cfg_em
    if not _cfg or time.time() - _cfg_em > 300:
        raw = ssm.get_parameter(Name=PARAM, WithDecryption=True)["Parameter"]["Value"]
        _cfg, _cfg_em = json.loads(raw), time.time()
    return _cfg


def chave() -> str:
    PASTA.mkdir(parents=True, exist_ok=True)
    if not CHAVE.exists():
        CHAVE.write_text(secrets.token_urlsafe(32))
        CHAVE.chmod(0o600)
    return CHAVE.read_text().strip()


def ativo() -> None:
    try:
        ATIVIDADE.touch()
    except OSError:
        pass


# ------------------------------------------------------------------ Graph API

def graph(path: str, body: dict | None = None, data: bytes | None = None, ctype: str = "") -> dict:
    headers = {"Authorization": f"Bearer {cfg()['token']}"}
    if body is not None:
        data, ctype = json.dumps(body).encode(), "application/json"
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(f"{GRAPH}/{path}", data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            erro = json.loads(e.read()).get("error", {})
        except Exception:
            erro = {"message": str(e)}
        raise RuntimeError(json.dumps(erro, ensure_ascii=False)) from None


def baixar_midia(media_id: str, destino: Path) -> Path:
    info = graph(media_id)
    req = urllib.request.Request(info["url"], headers={"Authorization": f"Bearer {cfg()['token']}"})
    ext = mimetypes.guess_extension((info.get("mime_type") or "").split(";")[0]) or ""
    destino = destino.with_suffix(".ogg" if "ogg" in (info.get("mime_type") or "") else ext)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=120) as r:
        destino.write_bytes(r.read())
    return destino


def lido_e_digitando(message_id: str) -> None:
    try:
        graph(f"{cfg()['phone_number_id']}/messages", {
            "messaging_product": "whatsapp", "status": "read", "message_id": message_id,
            "typing_indicator": {"type": "text"},
        })
    except Exception as exc:
        log(f"read receipt failed: {exc}")


def _mensagem(numero: str, conteudo: dict) -> None:
    graph(f"{cfg()['phone_number_id']}/messages",
          {"messaging_product": "whatsapp", "recipient_type": "individual", "to": numero, **conteudo})


def dividir(texto: str) -> list[str]:
    partes, atual = [], ""
    for bloco in texto.split("\n\n"):
        while len(bloco) > LIMITE_TEXTO:
            partes.append(bloco[:LIMITE_TEXTO])
            bloco = bloco[LIMITE_TEXTO:]
        if len(atual) + len(bloco) + 2 > LIMITE_TEXTO:
            partes.append(atual)
            atual = bloco
        else:
            atual = f"{atual}\n\n{bloco}" if atual else bloco
    if atual:
        partes.append(atual)
    return [p for p in partes if p.strip()]


def enviar_texto(numero: str, texto: str) -> None:
    try:
        for parte in dividir(texto):
            _mensagem(numero, {"type": "text", "text": {"body": parte, "preview_url": False}})
    except RuntimeError as exc:
        # 131047: more than 24 h since the person last wrote; only an approved template goes out.
        modelo = cfg().get("modelo_aviso")
        if "131047" not in str(exc) or not modelo:
            raise
        resumo = " ".join(texto.split())[:900]
        _mensagem(numero, {"type": "template", "template": {
            "name": modelo, "language": {"code": cfg().get("modelo_idioma", "pt_BR")},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": resumo}]}],
        }})


def enviar_botoes(numero: str, texto: str, botoes: list) -> None:
    """Up to 3 reply buttons (titles up to 20 characters); the reply comes back as its id."""
    _mensagem(numero, {"type": "interactive", "interactive": {
        "type": "button", "body": {"text": texto[:1000]},
        "action": {"buttons": [{"type": "reply", "reply": {"id": str(b["id"])[:256], "title": str(b["titulo"])[:20]}}
                               for b in botoes[:3]]},
    }})


def enviar_arquivo(numero: str, caminho: Path, legenda: str = "") -> None:
    mime = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
    limite = uuid.uuid4().hex
    corpo = b"".join([
        f"--{limite}\r\nContent-Disposition: form-data; name=\"messaging_product\"\r\n\r\nwhatsapp\r\n".encode(),
        f"--{limite}\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\n{mime}\r\n".encode(),
        f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{caminho.name}\"\r\n"
        f"Content-Type: {mime}\r\n\r\n".encode(), caminho.read_bytes(), f"\r\n--{limite}--\r\n".encode(),
    ])
    media = graph(f"{cfg()['phone_number_id']}/media", data=corpo, ctype=f"multipart/form-data; boundary={limite}")
    tipo = "image" if mime in ("image/jpeg", "image/png") else "video" if mime.startswith("video/") else "document"
    item = {"id": media["id"]}
    if legenda:
        item["caption"] = legenda[:1000]
    if tipo == "document":
        item["filename"] = caminho.name
    _mensagem(numero, {"type": tipo, tipo: item})


# ------------------------------------------------------------------ Telegram

TG_LIMITE = 4000  # Telegram allows 4096 per message


def tg(metodo: str, dados: dict | None = None, arquivo: tuple[str, Path] | None = None) -> dict:
    url = f"https://api.telegram.org/bot{cfg()['tg_token']}/{metodo}"
    if arquivo:
        campo, caminho = arquivo
        limite = uuid.uuid4().hex
        partes = [f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
                  for k, v in (dados or {}).items()]
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{campo}\"; filename=\"{caminho.name}\"\r\n"
                      f"Content-Type: application/octet-stream\r\n\r\n".encode() + caminho.read_bytes() + b"\r\n")
        corpo, tipo = b"".join(partes) + f"--{limite}--\r\n".encode(), f"multipart/form-data; boundary={limite}"
    else:
        corpo, tipo = json.dumps(dados or {}).encode(), "application/json"
    req = urllib.request.Request(url, data=corpo, headers={"Content-Type": tipo})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(e.read().decode()[:300]) from None


def tg_chat(usuario: str) -> str:
    return next((c for c, u in (cfg().get("tg_chats") or {}).items() if u == usuario), "")


def tg_texto(chat: str, texto: str, botoes: list | None = None) -> None:
    if not texto.startswith("🎤"):  # the echo of a voice note is not the answer: keep "typing…"
        DIGITANDO.pop(chat, None)
    partes = [texto[i:i + TG_LIMITE] for i in range(0, len(texto), TG_LIMITE)] or [""]
    for i, parte in enumerate(partes):
        dados = {"chat_id": chat, "text": parte, "parse_mode": "Markdown", "disable_web_page_preview": True}
        if botoes and i == len(partes) - 1:
            dados["reply_markup"] = {"inline_keyboard": [[{"text": b["titulo"], "callback_data": str(b["id"])[:64]}
                                                          for b in botoes[:3]]]}
        try:
            tg("sendMessage", dados)
        except RuntimeError:  # unbalanced * or _ in the text: send it plain
            dados.pop("parse_mode")
            tg("sendMessage", dados)


def tg_arquivo(chat: str, caminho: Path, legenda: str = "") -> None:
    foto = caminho.suffix.lower() in (".jpg", ".jpeg", ".png")
    tg("sendPhoto" if foto else "sendDocument", {"chat_id": chat, "caption": legenda[:1000]},
       ("photo" if foto else "document", caminho))


def tg_baixar(file_id: str, destino: Path) -> Path:
    info = tg("getFile", {"file_id": file_id})["result"]
    destino = destino.with_suffix(Path(info["file_path"]).suffix or destino.suffix)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{cfg()['tg_token']}/{info['file_path']}", timeout=120) as r:
        destino.write_bytes(r.read())
    return destino


def preparar_tg(item: dict) -> dict:
    """Telegram update -> what the plugin needs (same shape as preparar)."""
    update = item["update"]
    if update.get("callback_query"):
        q = update["callback_query"]
        try:
            tg("answerCallbackQuery", {"callback_query_id": q["id"]})
        except Exception:
            pass
        return {"usuario": item["usuario"], "texto": "", "botao": q.get("data", ""), "anexos": [], "audio": "",
                "id": f"tg-{update.get('update_id')}"}
    msg = update.get("message") or {}
    try:
        tg("sendChatAction", {"chat_id": item["chat"], "action": "typing"})
    except Exception:
        pass
    pasta = PASTA / item["usuario"] / time.strftime("%Y-%m")
    base = pasta / f"{time.strftime('%d-%H%M%S')}-tg{msg.get('message_id', '')}"
    no_a0 = lambda p: USR_A0 + str(p)[len(str(USR_HOST)):]
    texto, anexos, audio = msg.get("text") or msg.get("caption") or "", [], ""
    if msg.get("voice") or msg.get("audio"):
        audio = no_a0(tg_baixar((msg.get("voice") or msg.get("audio"))["file_id"], base.with_suffix(".ogg")))
    for chave in ("document", "video", "video_note"):
        if msg.get(chave):
            nome = msg[chave].get("file_name") or ""
            anexos.append(no_a0(tg_baixar(msg[chave]["file_id"], pasta / nome if nome else base)))
    if msg.get("photo"):
        anexos.append(no_a0(tg_baixar(msg["photo"][-1]["file_id"], base.with_suffix(".jpg"))))
    if msg.get("location"):
        texto = f"Minha localização: {msg['location'].get('latitude')}, {msg['location'].get('longitude')}"
    if not (texto or anexos or audio):
        texto = "(mensagem de um tipo que eu ainda não sei abrir)"
    return {"usuario": item["usuario"], "texto": texto, "audio": audio, "anexos": anexos, "botao": "",
            "id": f"tg-{update.get('update_id')}"}


DIGITANDO: dict[str, float] = {}  # chat -> until when to keep "typing…" on


def ciclo_digitando() -> None:
    """Keep Telegram's "typing…" on while the agent works (it lasts 5 s per call); stops when an
    answer goes out or after 2 minutes."""
    while True:
        agora = time.time()
        for chat, ate in list(DIGITANDO.items()):
            if agora > ate:
                DIGITANDO.pop(chat, None)
                continue
            try:
                tg("sendChatAction", {"chat_id": chat, "action": "typing"})
            except Exception:
                pass
        time.sleep(4)


def avisar(usuario: str, texto: str) -> None:
    """Plain notice to a person on their channel: Telegram when linked, else WhatsApp."""
    chat = tg_chat(usuario)
    if chat:
        return tg_texto(chat, texto)
    numero = next((n for n, u in (cfg().get("numeros") or {}).items() if u == usuario), "")
    if numero:
        enviar_texto(numero, texto)


# ------------------------------------------------------------------ spending

def gasto() -> tuple[float, float]:
    """(today, this month) in US$, by Bahia time, from the proxy's usage log."""
    from zoneinfo import ZoneInfo
    import datetime as dt

    agora = dt.datetime.now(ZoneInfo("America/Bahia"))
    hoje, mes = 0.0, 0.0
    try:
        linhas = USO.read_text().splitlines()
    except OSError:
        return 0.0, 0.0
    for linha in linhas:
        try:
            u = json.loads(linha)
            quando = dt.datetime.fromisoformat(u["em"].replace("Z", "+00:00")).astimezone(ZoneInfo("America/Bahia"))
        except Exception:
            continue
        if (quando.year, quando.month) != (agora.year, agora.month):
            continue
        p_in, p_cache, p_out = PRECOS["sol"] if "sol" in u.get("modelo", "") else PRECOS["luna"]
        cache, gravado = u.get("cache", 0) or 0, u.get("cache_gravado", 0) or 0
        normal = max(0, (u.get("entrada", 0) or 0) - cache - gravado)
        custo = (normal * p_in + cache * p_cache + gravado * p_in * 1.25 + (u.get("saida", 0) or 0) * p_out) / 1e6
        mes += custo
        if quando.date() == agora.date():
            hoje += custo
    return hoje, mes


def texto_gasto() -> str:
    hoje, mes = gasto()
    limite = float(cfg().get("limite_dia_usd") or LIMITE_DIA_PADRAO)
    return (f"💰 *Gasto com modelos*\nHoje: US$ {hoje:.2f} (limite de alerta: US$ {limite:.0f})\n"
            f"Este mês: US$ {mes:.2f}\n_(estimativa pelo uso registrado; a VM é cobrada à parte)_")


def ciclo_alerta() -> None:
    """Once a day, warn the owner when today's model spending passes the limit."""
    while True:
        time.sleep(600)
        try:
            hoje, _ = gasto()
            limite = float(cfg().get("limite_dia_usd") or LIMITE_DIA_PADRAO)
            dia = time.strftime("%Y-%m-%d")
            ja = json.loads(ALERTA.read_text()).get("dia") if ALERTA.exists() else ""
            if hoje > limite and ja != dia:
                if True:
                    avisar("matheus", f"⚠️ O agente já gastou US$ {hoje:.2f} hoje (limite de alerta US$ {limite:.0f}). "
                                       "Mande /parar para parar tudo ou /gasto para ver o total.")
                ALERTA.write_text(json.dumps({"dia": dia}))
            expira = float(cfg().get("token_expira") or 0)
            aviso_token = Path("/var/lib/agentepessoal/alerta_token.json")
            ja_token = json.loads(aviso_token.read_text()).get("dia") if aviso_token.exists() else ""
            if expira and expira - time.time() < 7 * 86400 and ja_token != dia:
                if True:
                    dias = max(0, int((expira - time.time()) / 86400))
                    avisar("matheus", f"🔑 O acesso do agente ao WhatsApp vence em {dias} dia(s). Peça ao agente: "
                                       "\"gere um token novo na Configuração da API do app Agente Pessoal e guarde com "
                                       "whatsapp_guardar_token\".")
                aviso_token.write_text(json.dumps({"dia": dia}))
        except Exception as exc:
            log(f"spending check failed: {exc}")


# ------------------------------------------------------------------ in: queue -> agent

def _vistos() -> list[str]:
    try:
        return json.loads(VISTOS.read_text())
    except Exception:
        return []


def _lembrar(mid: str) -> None:
    VISTOS.parent.mkdir(parents=True, exist_ok=True)
    VISTOS.write_text(json.dumps((_vistos() + [mid])[-500:]))


def preparar(item: dict) -> dict:
    """WhatsApp message -> what the plugin needs (text, audio, attachments as container paths)."""
    msg = item["mensagem"]
    tipo = msg.get("type", "")
    pasta = PASTA / item["usuario"] / time.strftime("%Y-%m")
    base = pasta / f"{time.strftime('%d-%H%M%S')}-{msg.get('id', '')[-8:]}"
    texto, anexos, audio, botao = "", [], "", ""

    def no_a0(p: Path) -> str:
        return USR_A0 + str(p)[len(str(USR_HOST)):]

    if tipo == "text":
        texto = msg["text"].get("body", "")
    elif tipo in ("audio", "voice"):
        audio = no_a0(baixar_midia(msg[tipo]["id"], base))
    elif tipo in ("image", "document", "video", "sticker"):
        dados = msg[tipo]
        nome = dados.get("filename") or ""
        destino = pasta / nome if nome else base
        anexos.append(no_a0(baixar_midia(dados["id"], destino)))
        texto = dados.get("caption", "")
    elif tipo == "location":
        loc = msg["location"]
        texto = f"Minha localização: {loc.get('latitude')}, {loc.get('longitude')} {loc.get('name', '')} {loc.get('address', '')}".strip()
    elif tipo == "interactive":
        resp = msg["interactive"].get("button_reply") or msg["interactive"].get("list_reply") or {}
        texto = resp.get("title", "")
        botao = resp.get("id", "")
    elif tipo == "button":
        texto = msg["button"].get("text", "")
    elif tipo == "reaction":
        return {}
    else:
        texto = f"(mensagem do tipo «{tipo}», que eu ainda não sei abrir)"

    contexto = msg.get("context") or {}
    return {"usuario": item["usuario"], "nome": item.get("nome", ""), "texto": texto, "audio": audio,
            "anexos": anexos, "id": msg.get("id", ""), "responde_a": contexto.get("id", ""), "botao": botao}


def entregar(dados: dict) -> None:
    req = urllib.request.Request(
        f"{A0}/api/plugins/whatsapp/receber", data=json.dumps(dados).encode(),
        headers={"Content-Type": "application/json", "X-Chave": chave()},
    )
    with urllib.request.urlopen(req, timeout=600) as r:  # audio transcription can take a while
        resposta = json.loads(r.read() or b"{}")
    if not resposta.get("ok"):
        raise RuntimeError(resposta.get("erro") or "agente recusou")


def ciclo_entrada() -> None:
    while True:  # keep going even before the queue/settings exist (set up later by deploy)
        try:
            url = sqs.get_queue_url(QueueName=QUEUE)["QueueUrl"]
            break
        except Exception as exc:
            log(f"queue not available yet: {exc}")
            time.sleep(60)
    while True:
        try:
            r = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=5, WaitTimeSeconds=20, VisibilityTimeout=300)
        except Exception as exc:
            log(f"queue read failed: {exc}")
            time.sleep(5)
            continue
        for m in r.get("Messages", []):
            item = json.loads(m["Body"])
            ativo()
            if item.get("canal") == "telegram":
                try:
                    msg = (item["update"].get("message") or {})
                    if (msg.get("text") or "").strip().lower() == "/gasto":
                        tg_texto(item["chat"], texto_gasto())
                    else:
                        DIGITANDO[item["chat"]] = time.time() + 120
                        dados = preparar_tg(item)
                        for tentativa in range(30):  # right after waking, Agent Zero may still be starting
                            try:
                                entregar(dados)
                                break
                            except (urllib.error.URLError, ConnectionError) as exc:
                                if tentativa == 29:
                                    raise
                                time.sleep(5)
                except Exception as exc:
                    log(f"telegram message failed: {exc}")
                    try:
                        tg_texto(item["chat"], "⚠️ Não consegui entregar sua mensagem ao agente. Tente de novo em instantes.")
                    except Exception:
                        pass
                sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
                continue
            if "gatilho" in item:  # an event trigger fired from outside (control function /gatilho)
                try:
                    entregar({"usuario": item["usuario"], "conversa": "gatilhos", "gatilho": item["gatilho"],
                              "texto": item.get("conteudo", ""), "id": f"gatilho-{m['MessageId']}"})
                    sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
                except Exception as exc:  # stays in the queue and is retried after the visibility timeout
                    log(f"trigger {item.get('gatilho')} not delivered: {exc}")
                continue
            mid = item["mensagem"].get("id", "")
            try:
                if mid and mid in _vistos():
                    sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
                    continue
                lido_e_digitando(mid)
                if (item["mensagem"].get("text") or {}).get("body", "").strip().lower() == "/gasto":
                    enviar_texto(item["numero"], texto_gasto())  # answered here: the usage log is on the host
                    _lembrar(mid)
                    sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
                    continue
                dados = preparar(item)
                if dados:
                    for tentativa in range(30):  # right after waking, Agent Zero may still be starting
                        try:
                            entregar(dados)
                            break
                        except (urllib.error.URLError, ConnectionError) as exc:
                            if tentativa == 29:
                                raise
                            log(f"agent not ready ({exc}); retrying")
                            time.sleep(5)
                _lembrar(mid)
                sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
            except Exception as exc:
                log(f"message {mid[-8:]} failed: {exc}")
                try:
                    enviar_texto(item["numero"], "⚠️ Não consegui entregar sua mensagem ao agente. Tente de novo em instantes.")
                except Exception:
                    pass
                sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])


# ------------------------------------------------------------------ out: agent -> WhatsApp

class Saida(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _responder(self, code: int, corpo: dict) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_POST(self):
        if self.path not in ("/enviar", "/gatilho_url", "/configurar") or not secrets.compare_digest(self.headers.get("X-Chave", ""), chave()):
            return self._responder(403, {"erro": "sem acesso"})
        if self.path == "/configurar":  # the token, read from the Meta page by a tool (never by the model)
            global _cfg
            pedido = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            atual = json.loads(ssm.get_parameter(Name=PARAM, WithDecryption=True)["Parameter"]["Value"])
            token = str(pedido.get("token") or "").strip()
            segredo = str(pedido.get("app_secret") or "").strip()
            if token and (not token.startswith("EAA") or len(token) < 80):
                return self._responder(400, {"erro": "token inválido"})
            if segredo and not re.fullmatch(r"[0-9a-f]{32}", segredo):
                return self._responder(400, {"erro": "chave do app inválida"})
            if token:  # only token/app secret: numbers are set on the control page alone
                atual["token"] = token
            if segredo:
                atual["app_secret"] = segredo
            aviso = ""
            if atual.get("token") and atual.get("app_secret") and atual.get("app_id"):
                try:  # the API Setup token lasts ~1 h: trade it for a 60-day one
                    q = urllib.parse.urlencode({"grant_type": "fb_exchange_token", "client_id": atual["app_id"],
                                                "client_secret": atual["app_secret"], "fb_exchange_token": atual["token"]})
                    with urllib.request.urlopen(f"{GRAPH}/oauth/access_token?{q}", timeout=30) as r:
                        longo = json.loads(r.read())
                    atual["token"] = longo["access_token"]
                    atual["token_expira"] = int(time.time()) + int(longo.get("expires_in") or 60 * 86400)
                    aviso = "token trocado pelo de longa duração"
                except Exception as exc:
                    aviso = f"troca pelo token longo falhou: {str(exc)[:120]}"
            ssm.put_parameter(Name=PARAM, Value=json.dumps(atual), Type="SecureString", Overwrite=True)
            _cfg = atual
            return self._responder(200, {"ok": True, "final": atual.get("token", "")[-4:], "aviso": aviso})
        if self.path == "/gatilho_url":  # the address a service calls to fire one of the agent's triggers
            pedido = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            c = cfg()
            if not c.get("base_url") or not c.get("caminho_gatilhos"):
                return self._responder(503, {"erro": "abra a caixa WhatsApp da página de controle uma vez para ativar os gatilhos"})
            return self._responder(200, {"url": f"{c['base_url']}/gatilho/{c['caminho_gatilhos']}/{pedido.get('usuario')}/{pedido.get('nome')}"})
        try:
            pedido = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            usuario = str(pedido.get("usuario", "")).lower()
            numeros = {u: n for n, u in (cfg().get("numeros") or {}).items()}
            numero = numeros.get(usuario)
            chat = tg_chat(usuario)  # Telegram, when linked, is where this person is answered
            if not (numero or chat):
                return self._responder(404, {"erro": "pessoa sem WhatsApp/Telegram cadastrado"})
            ativo()
            if chat:
                if pedido.get("texto"):
                    tg_texto(chat, str(pedido["texto"]), pedido.get("botoes") or None)
                if pedido.get("arquivo"):
                    caminho = Path(str(pedido["arquivo"]))
                    if str(caminho).startswith(USR_A0 + "/"):
                        caminho = USR_HOST / str(caminho)[len(USR_A0) + 1:]
                    caminho = caminho.resolve()
                    if not str(caminho).startswith(str(USR_HOST) + "/") or not caminho.is_file():
                        return self._responder(400, {"erro": "arquivo não encontrado em /a0/usr"})
                    tg_arquivo(chat, caminho, str(pedido.get("legenda") or ""))
                return self._responder(200, {"ok": True})
            if pedido.get("texto") and pedido.get("botoes"):
                try:
                    enviar_botoes(numero, str(pedido["texto"]), pedido["botoes"])
                except RuntimeError:  # outside the 24 h window buttons cannot go: plain notice
                    enviar_texto(numero, str(pedido["texto"]) + "\n\nResponda: aprovar, sempre ou recusar.")
            elif pedido.get("texto"):
                enviar_texto(numero, str(pedido["texto"]))
            if pedido.get("arquivo"):
                caminho = Path(str(pedido["arquivo"]))
                if str(caminho).startswith(USR_A0 + "/"):
                    caminho = USR_HOST / str(caminho)[len(USR_A0) + 1:]
                caminho = caminho.resolve()
                if not str(caminho).startswith(str(USR_HOST) + "/") or not caminho.is_file():
                    return self._responder(400, {"erro": "arquivo não encontrado em /a0/usr"})
                if caminho.stat().st_size > 95 * 1024 * 1024:
                    return self._responder(400, {"erro": "arquivo maior que 95 MB"})
                enviar_arquivo(numero, caminho, str(pedido.get("legenda") or ""))
            self._responder(200, {"ok": True})
        except Exception as exc:
            log(f"send failed: {exc}")
            self._responder(502, {"erro": str(exc)[:500]})


def main() -> None:
    chave()
    threading.Thread(target=ciclo_entrada, daemon=True).start()
    threading.Thread(target=ciclo_alerta, daemon=True).start()
    threading.Thread(target=ciclo_digitando, daemon=True).start()
    log("ready")
    http.server.ThreadingHTTPServer(LISTEN, Saida).serve_forever()


if __name__ == "__main__":
    main()

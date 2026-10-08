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
import urllib.error
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
        if self.path not in ("/enviar", "/gatilho_url") or not secrets.compare_digest(self.headers.get("X-Chave", ""), chave()):
            return self._responder(403, {"erro": "sem acesso"})
        if self.path == "/gatilho_url":  # the address a service calls to fire one of the agent's triggers
            pedido = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            c = cfg()
            if not c.get("base_url") or not c.get("caminho_gatilhos"):
                return self._responder(503, {"erro": "abra a caixa WhatsApp da página de controle uma vez para ativar os gatilhos"})
            return self._responder(200, {"url": f"{c['base_url']}/gatilho/{c['caminho_gatilhos']}/{pedido.get('usuario')}/{pedido.get('nome')}"})
        try:
            pedido = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            numeros = {u: n for n, u in (cfg().get("numeros") or {}).items()}
            numero = numeros.get(str(pedido.get("usuario", "")).lower())
            if not numero:
                return self._responder(404, {"erro": "pessoa sem WhatsApp cadastrado"})
            ativo()
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
    log("ready")
    http.server.ThreadingHTTPServer(LISTEN, Saida).serve_forever()


if __name__ == "__main__":
    main()

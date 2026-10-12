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

import fcntl
import hashlib
import http.server
import json
import mimetypes
import os
import secrets
import tempfile
import threading
import time
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
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
    tipo = ("image" if mime in ("image/jpeg", "image/png") else "video" if mime.startswith("video/")
            else "audio" if mime in ("audio/ogg", "audio/mpeg") else "document")
    item = {"id": media["id"]}
    if legenda and tipo != "audio":  # WhatsApp audio takes no caption
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
    DIGITANDO.pop(chat, None)  # an answer went out: stop "typing…"
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
    sufixo = caminho.suffix.lower()
    if sufixo in (".ogg", ".oga", ".opus"):  # OGG/Opus plays as a voice note
        tg("sendVoice", {"chat_id": chat, "caption": legenda[:1000]}, ("voice", caminho))
        return
    foto = sufixo in (".jpg", ".jpeg", ".png")
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


COFRE = USR_HOST / "segredos"  # same per-person vault as plugins/cofre (/a0/usr/segredos/<login>.json)
AJUDA_SENHA = ("🔒 Para guardar uma senha no seu cofre (o agente usa pelo nome e nunca vê o valor):\n"
               "/senha NOME valor\nex.: /senha GMAIL_SENHA minhaSenha123\n\n"
               "/senhas lista os nomes guardados · /apagarsenha NOME apaga uma.\n"
               "Sua mensagem é apagada do chat logo depois.")


SILENCIO = Path("/opt/a0/usr/whatsapp/silencio.json")  # {login: {"inicio": "23:00", "fim": "07:00"} | {"desligado": true}}
FILA = Path("/opt/a0/usr/whatsapp/fila")  # progress notices held during quiet hours, one .jsonl per person
SILENCIO_PADRAO = {"inicio": "23:00", "fim": "07:00"}
ACORDADO = 30 * 60  # wrote in the last 30 min: awake, progress goes out at once
ULTIMA_ENTRADA: dict[str, float] = {}


def _silencio(usuario: str) -> dict:
    try:
        return json.loads(SILENCIO.read_text(encoding="utf-8")).get(usuario) or SILENCIO_PADRAO
    except Exception:
        return SILENCIO_PADRAO


def em_silencio(usuario: str) -> bool:
    """Quiet hours (America/Bahia) and the person has not written recently."""
    regra = _silencio(usuario)
    if regra.get("desligado") or time.time() - ULTIMA_ENTRADA.get(usuario, 0) < ACORDADO:
        return False
    from datetime import datetime
    from zoneinfo import ZoneInfo

    agora = datetime.now(ZoneInfo("America/Bahia")).strftime("%H:%M")
    inicio, fim = regra.get("inicio", "23:00"), regra.get("fim", "07:00")
    return (inicio <= agora or agora < fim) if inicio > fim else (inicio <= agora < fim)


def guardar_para_depois(usuario: str, texto: str) -> None:
    FILA.mkdir(parents=True, exist_ok=True)
    with (FILA / f"{re.sub(r'[^a-z0-9_.-]', '', usuario)}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"em": time.time(), "texto": texto}, ensure_ascii=False) + "\n")


def ciclo_fila() -> None:
    """When quiet hours end (or the person writes), deliver what was held as one summary."""
    while True:
        time.sleep(60)
        try:
            for arq in sorted(FILA.glob("*.jsonl")) if FILA.is_dir() else []:
                usuario = arq.stem
                if em_silencio(usuario):
                    continue
                itens = [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()]
                arq.unlink()
                if not itens:
                    continue
                partes, total = [], 0
                for it in itens:
                    from datetime import datetime
                    from zoneinfo import ZoneInfo

                    hora = datetime.fromtimestamp(it["em"], ZoneInfo("America/Bahia")).strftime("%H:%M")
                    trecho = f"• {hora} — {it['texto'].strip()[:700]}"
                    if total + len(trecho) > LIMITE_TEXTO - 200:
                        partes.append(f"… e mais {len(itens) - len(partes)} avisos (veja no app).")
                        break
                    partes.append(trecho)
                    total += len(trecho)
                avisar(usuario, "🌅 *Enquanto você descansava* (avisos de progresso guardados):\n\n" + "\n\n".join(partes))
                log(f"quiet hours over: delivered {len(itens)} held notices to {usuario}")
        except Exception as exc:
            log(f"held notices failed: {exc}")


def comando_silencio(usuario: str, texto: str) -> str | None:
    """/silencio 23-7 | /silencio off | /silencio : quiet hours for progress notices."""
    partes = texto.strip().split()
    if not partes or partes[0].lower().split("@")[0] != "/silencio":
        return None
    try:
        todos = json.loads(SILENCIO.read_text(encoding="utf-8"))
    except Exception:
        todos = {}
    if len(partes) > 1:
        arg = partes[1].lower()
        if arg in ("off", "desligar", "nao", "não"):
            todos[usuario] = {"desligado": True}
        else:
            m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?-(\d{1,2})(?::(\d{2}))?", arg)
            if not m:
                return "Use /silencio 23-7 (das 23h às 7h), /silencio 22:30-6:30 ou /silencio off."
            todos[usuario] = {"inicio": f"{int(m[1]):02d}:{m[2] or '00'}", "fim": f"{int(m[3]):02d}:{m[4] or '00'}"}
        SILENCIO.parent.mkdir(parents=True, exist_ok=True)
        SILENCIO.write_text(json.dumps(todos, ensure_ascii=False, indent=1), encoding="utf-8")
    regra = todos.get(usuario) or SILENCIO_PADRAO
    if regra.get("desligado"):
        return "🔔 Horário de silêncio desligado: todos os avisos chegam na hora."
    return (f"🌙 Horário de silêncio: {regra['inicio']}–{regra['fim']}. Nesse horário, avisos de progresso ficam "
            "guardados e chegam juntos quando acabar; o que precisa de você (aprovação, código, decisão, erro) "
            "chega na hora. Se você escrever, entende que está acordado. Mude com /silencio 23-7 ou /silencio off.")


DESCREVER: dict[str, tuple[str, float]] = {}  # login -> (secret just saved, when): its "which account?" is pending
DESCREVER_PRAZO = 10 * 60


class CofreIlegivel(RuntimeError):
    pass


def _cofre_ler(arquivo: Path) -> dict:
    """{} only when the file does not exist; unreadable after 3 tries = CofreIlegivel (never "no secrets")."""
    if not arquivo.exists():
        return {}
    for tentativa in range(3):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            if isinstance(dados, dict):
                return dados
            raise ValueError("não é um objeto JSON")
        except (OSError, ValueError) as exc:
            if tentativa == 2:
                raise CofreIlegivel(str(exc)[:60]) from None
            time.sleep(0.1)
    return {}


@contextmanager
def _cofre_transacao(arquivo: Path):
    """Read → change → write as one step, under the same lock as plugins/cofre (flock on <file>.lock, the same file
    seen from the container): 12/10 review, the agent and this bridge could overwrite each other, and a read in the
    middle of a write took the vault as empty. The file is replaced whole (temp file, mode 600, fsync, rename)."""
    COFRE.mkdir(parents=True, exist_ok=True)
    os.chmod(COFRE, 0o700)
    with open(arquivo.with_name(arquivo.name + ".lock"), "a") as trava:
        limite = time.time() + 30
        while True:
            try:
                fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() > limite:
                    raise CofreIlegivel("ocupado há mais de 30 s") from None
                time.sleep(0.05)
        try:
            dados = _cofre_ler(arquivo)
            yield dados
            fd, tmp = tempfile.mkstemp(dir=arquivo.parent, prefix=f".{arquivo.name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(dados, f, ensure_ascii=False, indent=1 if arquivo.name.endswith(".descricoes.json") else None)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, arquivo)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        finally:
            fcntl.flock(trava, fcntl.LOCK_UN)


def _arquivo_descricoes(usuario: str) -> Path:
    return COFRE / f"{re.sub(r'[^a-z0-9_.-]', '', usuario.lower())}.descricoes.json"


def comando_cofre(usuario: str, texto: str) -> str | None:
    """/senha, /senhas, /apagarsenha: handled here and never delivered to the agent — and the answer to
    "which site/account is it?" right after a /senha (so the agent knows where to use it without asking).
    Returns the reply, or None when the text is not a vault command."""
    pendente = DESCREVER.get(usuario)
    if pendente and time.time() - pendente[1] < DESCREVER_PRAZO:
        linha = texto.strip()
        if linha.lower() in ("/pular", "pular"):
            DESCREVER.pop(usuario, None)
            return f"Ok, {pendente[0]} fica sem descrição."
        if linha and not linha.startswith("/") and "\n" not in linha and len(linha) <= 160:
            try:
                with _cofre_transacao(_arquivo_descricoes(usuario)) as desc:
                    desc[pendente[0]] = linha
            except CofreIlegivel:
                return "Não consegui ler o cofre agora (nada foi mudado). Mande a descrição de novo em 1 minuto."
            DESCREVER.pop(usuario, None)
            log(f"vault: {usuario} described {pendente[0]}")
            return f"📝 Anotado: {pendente[0]} = {linha}. O agente usa essa senha sozinho quando esse site pedir."
    partes = texto.strip().split(maxsplit=2)
    if not partes or partes[0].lower().split("@")[0] not in ("/senha", "/senhas", "/apagarsenha", "/cofre"):
        return None
    comando = partes[0].lower().split("@")[0]
    arquivo = COFRE / f"{re.sub(r'[^a-z0-9_.-]', '', usuario.lower())}.json"
    ilegivel = "Não consegui ler o cofre agora (nada foi mudado). Tente de novo em 1 minuto."
    if comando in ("/senhas", "/cofre") or (comando == "/senha" and len(partes) < 3):
        try:
            dados = _cofre_ler(arquivo)
        except CofreIlegivel:
            return ilegivel
        try:
            desc = _cofre_ler(_arquivo_descricoes(usuario))
        except CofreIlegivel:
            desc = {}
        nomes = "\n".join(f"• {n}" + (f" — {desc[n]}" if desc.get(n) else " — (de qual conta? mande /senha de novo ou fale ao agente)")
                          for n in sorted(dados)) or "nenhuma ainda"
        return f"{AJUDA_SENHA}\n\nGuardadas:\n{nomes}"
    nome = re.sub(r"[^A-Z0-9_]", "_", partes[1].upper())
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", nome):
        return "Nome inválido: use letras, números e _ começando com letra (ex.: GMAIL_SENHA)."
    try:
        with _cofre_transacao(arquivo) as dados:
            if comando == "/apagarsenha":
                dados.pop(nome, None)
            else:
                dados[nome] = partes[2].strip()
    except CofreIlegivel:
        return ilegivel
    if comando == "/apagarsenha":
        try:
            with _cofre_transacao(_arquivo_descricoes(usuario)) as desc:
                desc.pop(nome, None)
        except CofreIlegivel:
            pass  # the secret is gone; a leftover description is harmless
        resposta = f"🗑️ {nome} apagada do cofre."
    else:
        DESCREVER[usuario] = (nome, time.time())
        resposta = (f"🔒 Guardada no cofre como {nome}. O agente usa pelo nome e nunca vê o valor.\n\n"
                    f"De qual site e conta é essa senha? Responda numa linha (ex.: Instagram @minhaconta) — "
                    f"assim o agente sabe onde usar sem te perguntar. /pular deixa sem.")
    log(f"vault: {usuario} {comando} {nome}")
    return resposta


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


def texto_painel(usuario: str) -> str:
    """/painel: one screen of activity (from Agent Zero) plus today's spend (from the usage log here)."""
    try:
        req = urllib.request.Request(f"{A0}/api/plugins/whatsapp/painel", data=json.dumps({"usuario": usuario}).encode(),
                                     headers={"Content-Type": "application/json", "X-Chave": chave()})
        with urllib.request.urlopen(req, timeout=60) as r:
            corpo = json.loads(r.read() or b"{}").get("texto") or ""
    except Exception as exc:
        corpo = f"(não consegui ler o agente agora: {str(exc)[:120]})"
    return "📊 *Painel*\n\n" + corpo + "\n\n" + texto_gasto()


DECISOES = USR_HOST / "memoria" / "decisoes"  # plugins/memoria_pessoal (helpers/decisoes.py)
LIVRO = USR_HOST / "central" / "agente.db"  # plugins/central (helpers/livro.py)
ROTULO_TIPO = {"proibicao": "🚫", "permissao": "✅", "decisao": "📌", "preferencia": "💬"}
ROTULO_VERBO = {"dm": "💬 DM", "comentario": "🗨️ comentário", "seguir_curtir": "➕ seguir e curtir", "aviso": "📣 aviso"}


def _login_arquivo(usuario: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "", (usuario or "").lower()) or "matheus"


def texto_decisoes(usuario: str, agora: float | None = None) -> str:
    """/decisoes: the decisions in force, straight from the register (no model; the file is replaced whole)."""
    agora = agora or time.time()
    try:
        dados = json.loads((DECISOES / f"{_login_arquivo(usuario)}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "📋 Nenhuma decisão registrada ainda."
    except (OSError, ValueError):
        return "Não consegui ler o registro de decisões agora. Tente de novo em 1 minuto."
    vivas = [x for x in dados.get("decisoes", []) if x.get("estado") == "ativa"
             and not (x.get("valido_ate") and x["valido_ate"] < agora)]
    if not vivas:
        return "📋 Nenhuma decisão em vigor."
    ordem = list(ROTULO_TIPO)
    vivas.sort(key=lambda x: (ordem.index(x["tipo"]) if x.get("tipo") in ordem else 9, x.get("tema", "")))
    linhas = [f"{ROTULO_TIPO.get(x.get('tipo'), '📌')} #{x['id']} {x['valor']}" for x in vivas]
    return ("📋 *Suas decisões em vigor* (o agente segue sem perguntar)\n\n" + "\n".join(linhas)[:3500]
            + "\n\nPara mudar ou desfazer uma, diga ao agente (ex.: \"revoga a 7\").")


def texto_livro(usuario: str, agora: float | None = None) -> str:
    """/livro: what the agent did today, from the action ledger (read-only; no model)."""
    import sqlite3
    from datetime import datetime
    from zoneinfo import ZoneInfo

    if not LIVRO.exists():
        return "📒 O livro de ações ainda está vazio."
    fuso = ZoneInfo("America/Bahia")
    inicio = datetime.fromtimestamp(agora or time.time(), fuso).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    try:
        con = sqlite3.connect(f"file:{LIVRO}?mode=ro", uri=True, timeout=5)
        try:
            linhas = con.execute("SELECT em, fase, verbo, alvo, conteudo_previa, resultado FROM acao WHERE login = ? AND em >= ? "
                                 "AND fase IN ('executada','falhou','cancelada','divergente') ORDER BY em",
                                 (_login_arquivo(usuario), inicio)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return "Não consegui ler o livro de ações agora. Tente de novo em 1 minuto."
    if not linhas:
        return "📒 *Livro de hoje*: nada registrado ainda."
    contagem: dict = {}
    for _, fase, verbo, *_ in linhas:
        contagem[(verbo, fase)] = contagem.get((verbo, fase), 0) + 1
    topo = " · ".join(f"{ROTULO_VERBO.get(v, v)}: {n}" + ("" if f == "executada" else f" ({f})")
                      for (v, f), n in sorted(contagem.items()))
    detalhe = [f"{datetime.fromtimestamp(em, fuso).strftime('%H:%M')} {ROTULO_VERBO.get(verbo, verbo)} "
               f"{alvo.split(':', 1)[-1]}" + ("" if fase == "executada" else f" — {fase}: {(resultado or '')[:60]}")
               + (f" «{previa[:60]}»" if previa and fase == "executada" else "")
               for em, fase, verbo, alvo, previa, resultado in linhas[-15:]]
    return f"📒 *Livro de hoje* (registrado na hora; não se altera)\n{topo}\n\n" + "\n".join(detalhe)


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


# 12/10 review: the shared key (.chave) sits in the agent's own volume, so the agent could post a fake "phone message"
# or button press (an "aprovar") to the plugin. Every delivery now carries a one-time ticket that lives only here, in
# this process on the host; the plugin asks back (POST /conferir) before acting, and the ticket is spent on the spot.
BILHETES: dict[str, tuple[float, str]] = {}  # ticket -> (valid until, digest of what was delivered)
_TRAVA_BILHETES = threading.Lock()
CAMPOS_BILHETE = ("usuario", "conversa", "gatilho", "botao", "texto", "audio", "anexos")  # same in plugin ponte.py
VALIDADE_BILHETE = 300


def resumo_entrega(dados: dict) -> str:
    return hashlib.sha256(json.dumps({k: dados.get(k) for k in CAMPOS_BILHETE}, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()


def novo_bilhete(dados: dict, agora: float | None = None) -> str:
    agora = agora or time.time()
    bilhete = secrets.token_urlsafe(24)
    with _TRAVA_BILHETES:
        for velho in [b for b, (ate, _) in BILHETES.items() if ate < agora]:
            BILHETES.pop(velho, None)
        BILHETES[bilhete] = (agora + VALIDADE_BILHETE, resumo_entrega(dados))
    return bilhete


def conferir_bilhete(bilhete: str, resumo: str, agora: float | None = None) -> bool:
    """True once: the ticket was made here for exactly this delivery and has not expired."""
    with _TRAVA_BILHETES:
        dado = BILHETES.pop(bilhete or "", None)
    return bool(dado) and dado[0] >= (agora or time.time()) and secrets.compare_digest(dado[1], resumo or "")


def entregar(dados: dict) -> None:
    req = urllib.request.Request(
        f"{A0}/api/plugins/whatsapp/receber", data=json.dumps({**dados, "bilhete": novo_bilhete(dados)}).encode(),
        headers={"Content-Type": "application/json", "X-Chave": chave()},
    )
    with urllib.request.urlopen(req, timeout=600) as r:  # audio transcription can take a while
        resposta = json.loads(r.read() or b"{}")
    if not resposta.get("ok"):
        raise RuntimeError(resposta.get("erro") or "agente recusou")


class AgenteFora(Exception):
    """Agent Zero did not answer (off, starting, restarting): the message goes back to the queue, never away."""


# 12/10 review: a message was deleted after ~150 s of retries if the agent was still starting. Now it stays in the queue
# (back in 2 min) for about 25 minutes, the person is told once that it is queued, and only then is it given up: kept in
# NAO_ENTREGUES (host) and the person is told to send it again.
TENTATIVAS_FILA = 8
VOLTA_FILA = 120
NAO_ENTREGUES = Path("/var/lib/agentepessoal/mensagens_nao_entregues.jsonl")
TENTATIVAS_ENTREGA, PAUSA_ENTREGA = 12, 5.0  # about a minute per turn in the queue


def entregar_esperando(dados: dict) -> None:
    """entregar(), waiting up to a minute for an agent that is starting. A 4xx answer or a refusal is final."""
    tentativas, erro = TENTATIVAS_ENTREGA, None
    for tentativa in range(tentativas):
        try:
            return entregar(dados)
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise
            erro = exc
        except (urllib.error.URLError, ConnectionError) as exc:  # not a read timeout: the agent may have it already
            erro = exc
        if tentativa < tentativas - 1:
            time.sleep(PAUSA_ENTREGA)
    raise AgenteFora(str(erro))


def recebida_vezes(m: dict) -> int:
    try:
        return int((m.get("Attributes") or {}).get("ApproximateReceiveCount") or 1)
    except ValueError:
        return 1


def segurar_na_fila(url: str, m: dict, item: dict, avisar, erro: Exception) -> None:
    """The agent is not answering: back to the queue (said once), or, after TENTATIVAS_FILA, kept aside and said so."""
    vezes = recebida_vezes(m)
    if vezes < TENTATIVAS_FILA:
        log(f"agent not answering ({erro}); message back to the queue ({vezes}/{TENTATIVAS_FILA})")
        if vezes == 1:
            try:
                avisar("⏳ O agente está acordando. Sua mensagem ficou na fila e chega sozinha assim que ele subir "
                       "(não precisa mandar de novo).")
            except Exception:
                pass
        sqs.change_message_visibility(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"], VisibilityTimeout=VOLTA_FILA)
        return
    log(f"message given up after {vezes} tries: {erro}")
    try:
        NAO_ENTREGUES.parent.mkdir(parents=True, exist_ok=True)
        with NAO_ENTREGUES.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"em": time.time(), "erro": str(erro)[:300], "item": item}, ensure_ascii=False) + "\n")
    except OSError as exc:
        log(f"could not keep the undelivered message: {exc}")
    try:
        avisar("⚠️ Sua mensagem não chegou ao agente: ele não respondeu por uns 25 minutos. Mande de novo quando quiser.")
    except Exception:
        pass
    sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])


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
            r = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=5, WaitTimeSeconds=20, VisibilityTimeout=300,
                                    AttributeNames=["ApproximateReceiveCount"])
        except Exception as exc:
            log(f"queue read failed: {exc}")
            time.sleep(5)
            continue
        for m in r.get("Messages", []):
            try:
                tratar(url, m)
            except Exception as exc:  # one bad message never stops the loop (it comes back after the timeout)
                log(f"queued message {m.get('MessageId', '')[:8]} failed: {exc}")


def tratar(url: str, m: dict) -> None:
    """One queued message: phone (WhatsApp/Telegram) or trigger; deleted only when done or given up."""
    item = json.loads(m["Body"])
    ativo()
    if item.get("canal") == "telegram":
        tid = f"tg-{item['update'].get('update_id')}" if item["update"].get("update_id") is not None else ""
        if tid and tid in _vistos():  # Telegram re-sends an update when the webhook was slow: once only
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
            return
        try:
            msg = (item["update"].get("message") or {})
            ULTIMA_ENTRADA[item["usuario"]] = time.time()
            resposta_cofre = comando_cofre(item["usuario"], msg.get("text") or "")
            if resposta_cofre is None:
                resposta_cofre = comando_silencio(item["usuario"], msg.get("text") or "")
            if resposta_cofre is not None:  # passwords never reach the agent
                if (msg.get("text") or "").split()[0].lower().startswith("/senha") and len((msg.get("text") or "").split()) > 2:
                    try:
                        tg("deleteMessage", {"chat_id": item["chat"], "message_id": msg.get("message_id")})
                    except Exception:
                        resposta_cofre += "\n(Não consegui apagar sua mensagem: apague você no chat.)"
                tg_texto(item["chat"], resposta_cofre)
            elif (msg.get("text") or "").strip().lower() == "/gasto":
                tg_texto(item["chat"], texto_gasto())
            elif (msg.get("text") or "").strip().lower().split("@")[0] in ("/decisoes", "/decisões"):
                tg_texto(item["chat"], texto_decisoes(item["usuario"]))
            elif (msg.get("text") or "").strip().lower().split("@")[0] == "/livro":
                tg_texto(item["chat"], texto_livro(item["usuario"]))
            elif (msg.get("text") or "").strip().lower().split("@")[0] in ("/painel", "/status"):
                tg_texto(item["chat"], texto_painel(item["usuario"]))
            else:
                DIGITANDO[item["chat"]] = time.time() + 120
                entregar_esperando(preparar_tg(item))  # right after waking, Agent Zero may still be starting
        except AgenteFora as exc:
            segurar_na_fila(url, m, item, lambda t: tg_texto(item["chat"], t), exc)
            return
        except Exception as exc:
            log(f"telegram message failed: {exc}")
            try:
                tg_texto(item["chat"], "⚠️ Não consegui entregar sua mensagem ao agente. Tente de novo em instantes.")
            except Exception:
                pass
        if tid:
            _lembrar(tid)
        sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
        return
    if "gatilho" in item:  # an event trigger fired from outside (control function /gatilho)
        try:
            entregar({"usuario": item["usuario"], "conversa": "gatilhos", "gatilho": item["gatilho"],
                      "texto": item.get("conteudo", ""), "id": f"gatilho-{m['MessageId']}"})
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
        except Exception as exc:  # stays in the queue and is retried after the visibility timeout
            log(f"trigger {item.get('gatilho')} not delivered: {exc}")
            if recebida_vezes(m) >= 3 * TENTATIVAS_FILA:
                segurar_na_fila(url, m, item, lambda t: None, exc)
        return
    mid = item["mensagem"].get("id", "")
    try:
        if mid and mid in _vistos():
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
            return
        lido_e_digitando(mid)
        ULTIMA_ENTRADA[item["usuario"]] = time.time()
        resposta_cofre = comando_cofre(item["usuario"], (item["mensagem"].get("text") or {}).get("body", ""))
        if resposta_cofre is None:
            resposta_cofre = comando_silencio(item["usuario"], (item["mensagem"].get("text") or {}).get("body", ""))
        if resposta_cofre is not None:  # passwords never reach the agent (WhatsApp cannot delete it)
            enviar_texto(item["numero"], resposta_cofre + "\nApague sua mensagem com a senha deste chat.")
            _lembrar(mid)
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
            return
        if (item["mensagem"].get("text") or {}).get("body", "").strip().lower() in ("/painel", "/status"):
            enviar_texto(item["numero"], texto_painel(item["usuario"]))
            _lembrar(mid)
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
            return
        if (item["mensagem"].get("text") or {}).get("body", "").strip().lower() == "/gasto":
            enviar_texto(item["numero"], texto_gasto())  # answered here: the usage log is on the host
            _lembrar(mid)
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
            return
        comando = (item["mensagem"].get("text") or {}).get("body", "").strip().lower()
        if comando in ("/decisoes", "/decisões", "/livro"):  # answered here, from the files (no model)
            enviar_texto(item["numero"], texto_livro(item["usuario"]) if comando == "/livro"
                         else texto_decisoes(item["usuario"]))
            _lembrar(mid)
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
            return
        dados = preparar(item)
        if dados:
            entregar_esperando(dados)  # right after waking, Agent Zero may still be starting
        _lembrar(mid)
        sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
    except AgenteFora as exc:
        segurar_na_fila(url, m, item, lambda t: enviar_texto(item["numero"], t), exc)
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
        if self.path not in ("/enviar", "/gatilho_url", "/configurar", "/conferir") or not secrets.compare_digest(self.headers.get("X-Chave", ""), chave()):
            return self._responder(403, {"erro": "sem acesso"})
        if self.path == "/conferir":  # the plugin asks whether a delivery really came from here (ticket spent now)
            pedido = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            return self._responder(200, {"ok": conferir_bilhete(str(pedido.get("bilhete") or ""),
                                                                 str(pedido.get("resumo") or ""))})
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
            tipo = str(pedido.get("tipo") or ("urgente" if pedido.get("botoes") else "resposta"))
            if tipo == "progresso" and pedido.get("texto") and not pedido.get("arquivo") and em_silencio(usuario):
                guardar_para_depois(usuario, str(pedido["texto"]))
                return self._responder(200, {"ok": True, "adiado": True})
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


def ciclo_destravar() -> None:
    """Every minute, ask the whatsapp plugin to nudge chats stuck on a model call."""
    while True:
        time.sleep(60)
        try:
            req = urllib.request.Request(f"{A0}/api/plugins/whatsapp/destravar", data=b"{}",
                                         headers={"Content-Type": "application/json", "X-Chave": chave()})
            with urllib.request.urlopen(req, timeout=30) as r:
                feitos = json.loads(r.read() or b"{}").get("destravados") or []
            if feitos:
                log(f"nudged stuck chats: {feitos}")
        except Exception:
            pass  # Agent Zero starting or restarting


def main() -> None:
    chave()
    threading.Thread(target=ciclo_entrada, daemon=True).start()
    threading.Thread(target=ciclo_alerta, daemon=True).start()
    threading.Thread(target=ciclo_digitando, daemon=True).start()
    threading.Thread(target=ciclo_destravar, daemon=True).start()
    threading.Thread(target=ciclo_fila, daemon=True).start()
    log("ready")
    http.server.ThreadingHTTPServer(LISTEN, Saida).serve_forever()


if __name__ == "__main__":
    main()

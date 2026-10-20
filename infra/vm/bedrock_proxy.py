"""Local proxy for the agent's model APIs, so no keys live inside the Agent Zero container.

- /openai/...   -> Bedrock's OpenAI-compatible endpoint (bedrock-mantle), short-term token from the VM role
- /bedrock/...  -> Bedrock runtime (Converse API, for the Claude models), same token
- /typesafe/... -> TypeSafe (Jev), API key read from SSM /agentepessoal/typesafe-api-key
- /arquivos/...  -> big-file uploads into a chat: presigned S3 PUT (from the VM role), GET links for post files and
                    an on-demand run of entrada.sh, which moves the file into the chat's anexos/

Agent Zero only reads its API key at startup, while Bedrock short-term API keys
expire. This proxy injects a fresh bearer token (generated from the VM's IAM
role) into every request and streams the response back unchanged. It also
records the time of the last model call, which the idle watchdog reads, and appends each
call's token usage (input, cached, output) to /var/lib/agentepessoal/uso.jsonl.

12/10 review: GET /health answers here (no upstream call, no "activity"), with whether a Bedrock token can be made;
and a call refused for a moment (connection refused/reset, 429 or 5xx before any byte went to the agent) is tried once
more after a short wait, instead of failing the agent's turn. A hung call (no byte for 240 s) is not repeated here: the
agent retries it itself.
"""

import http.client
import http.server
import json
import os
import re
import ssl
import subprocess
import threading
import time
from datetime import timedelta
from pathlib import Path

from aws_bedrock_token_generator import provide_token

REGION = os.environ.get("AWS_REGION", "us-east-1")
UPSTREAM = os.environ.get("UPSTREAM_HOST", f"bedrock-mantle.{REGION}.api.aws")
RUNTIME = f"bedrock-runtime.{REGION}.amazonaws.com"
LISTEN = (os.environ.get("LISTEN_HOST", "0.0.0.0"), int(os.environ.get("LISTEN_PORT", "8787")))
ACTIVITY_FILE = Path(os.environ.get("ACTIVITY_FILE", "/var/lib/agentepessoal/last-activity"))
TOKEN_TTL = 30 * 60  # refresh well before the 1h token expiry
TYPESAFE_HOST = "api.typesafe.ai"
TYPESAFE_PARAM = "/agentepessoal/typesafe-api-key"
BUCKET = os.environ.get("BACKUP_BUCKET", "")
ENTRADA = "/opt/agentepessoal/entrada.sh"
CHAT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_UPLOAD = 5 * 1024**3

# X-A0-*: whose chat made the call and (20/10) which chat, routine, agent and role, set by the login_usuarios plugin;
# logged here, never sent upstream
HOP_HEADERS = {"host", "authorization", "content-length", "connection", "accept-encoding", "transfer-encoding",
               "x-a0-dono", "x-a0-conversa", "x-a0-rotina", "x-a0-agente", "x-a0-papel"}
SKIP_RESPONSE_HEADERS = {"transfer-encoding", "connection", "content-length", "content-encoding"}

_token = {"value": "", "at": 0.0}
_typesafe = {"value": "", "at": 0.0}
_lock = threading.Lock()
_ssl = ssl.create_default_context()


def bearer_token() -> str:
    with _lock:
        if not _token["value"] or time.time() - _token["at"] > TOKEN_TTL:
            _token["value"] = provide_token(region=REGION, expiry=timedelta(hours=1))
            _token["at"] = time.time()
        return _token["value"]


def typesafe_key() -> str:
    with _lock:
        if time.time() - _typesafe["at"] > 300:
            import boto3  # only needed for this route

            try:
                _typesafe["value"] = boto3.client("ssm", region_name=REGION).get_parameter(
                    Name=TYPESAFE_PARAM, WithDecryption=True)["Parameter"]["Value"]
            except Exception:
                _typesafe["value"] = ""
            _typesafe["at"] = time.time()
        return _typesafe["value"]


def safe_name(name: str) -> str:
    name = os.path.basename(str(name or "").replace("\\", "/")).strip()
    name = re.sub(r"[\x00-\x1f/]", "", name)[:180]
    return name if name not in ("", ".", "..") else "arquivo"


_s3 = {}
_pull = {"thread": None}
_pull_lock = threading.Lock()


def presign(chat: str, name: str, size: int) -> dict:
    if not BUCKET:
        return {"error": "bucket não configurado"}
    if not CHAT_ID.match(chat or ""):
        return {"error": "conversa inválida"}
    if not 0 <= int(size or 0) <= MAX_UPLOAD:
        return {"error": "arquivo maior que 5 GB"}
    if "client" not in _s3:
        import boto3
        from botocore.config import Config

        _s3["client"] = boto3.client("s3", region_name=REGION,
                                     config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    name = safe_name(name)
    key = f"entrada/chats/{chat}/{name}"
    url = _s3["client"].generate_presigned_url("put_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=6 * 3600)
    return {"url": url, "name": name}


def pull(wait: float) -> bool:
    """Run entrada.sh now (one run at a time); True once it finished within `wait` seconds."""
    with _pull_lock:
        t = _pull["thread"]
        if t is None or not t.is_alive():
            t = threading.Thread(target=lambda: subprocess.run([ENTRADA], timeout=3600), daemon=True)
            t.start()
            _pull["thread"] = t
    t.join(wait)
    return not t.is_alive()


def link_conteudo(chave: str) -> dict:
    """1-hour GET link for a @raiz.connect post file under conteudo/ in the bucket, for Meta to fetch: the agent
    container has no AWS credentials of its own (13/10: s1-pov failed with "Unable to locate credentials")."""
    if not BUCKET:
        return {"error": "bucket não configurado"}
    chave = str(chave or "")
    if not chave.startswith("conteudo/") or ".." in chave or chave.endswith("/") or len(chave) > 300:
        return {"error": "só arquivos de conteudo/"}
    if "client" not in _s3:
        import boto3
        from botocore.config import Config

        _s3["client"] = boto3.client("s3", region_name=REGION,
                                     config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    try:
        _s3["client"].head_object(Bucket=BUCKET, Key=chave)
    except Exception:
        return {"error": f"arquivo não encontrado: {chave}"}
    return {"url": _s3["client"].generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": chave}, ExpiresIn=3600)}


VIDEOS = Path("/opt/a0/usr/workdir/videos")  # /a0/usr/workdir/videos inside the agent container
PEGASUS = "us.twelvelabs.pegasus-1-5-v1:0"
_aws = {}


def pegasus(arquivo: str, prompt: str) -> dict:
    """Pegasus watches a video the agent downloaded: sent through S3, so long videos need no re-encoding
    to fit the ~20 MB inline limit (the agent container has no AWS credentials of its own)."""
    if not BUCKET:
        return {"error": "bucket não configurado"}
    caminho = (VIDEOS / str(arquivo or "").replace("/a0/usr/workdir/videos/", "", 1)).resolve()
    if VIDEOS.resolve() not in caminho.parents or not caminho.is_file():
        return {"error": "vídeo não encontrado na pasta de vídeos"}
    import boto3

    if "s3" not in _aws:
        _aws["s3"] = boto3.client("s3", region_name=REGION)
        _aws["br"] = boto3.client("bedrock-runtime", region_name=REGION)
        _aws["conta"] = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
    chave = f"tmp/videos/{caminho.parent.name}-{int(time.time())}{caminho.suffix}"
    _aws["s3"].upload_file(str(caminho), BUCKET, chave)
    try:
        r = _aws["br"].invoke_model(modelId=PEGASUS, body=json.dumps({
            "inputPrompt": str(prompt or "")[:4000], "temperature": 0,
            "mediaSource": {"s3Location": {"uri": f"s3://{BUCKET}/{chave}", "bucketOwner": _aws["conta"]}}}))
        return {"message": str(json.loads(r["body"].read()).get("message") or "")}
    finally:
        _aws["s3"].delete_object(Bucket=BUCKET, Key=chave)


# 15/10: answers in the language the person spoke. (voice, language code, engines tried in order). pt-BR keeps only
# the generative Camila (the neural one reads like a robot); Russian has only standard voices on Polly.
VOZES = {"pt": ("Camila", "pt-BR", ("generative",)), "ru": ("Tatyana", "ru-RU", ("standard",)),
         "en": ("Danielle", "en-US", ("generative", "neural")), "es": ("Lupe", "es-US", ("generative", "neural")),
         "fr": ("Lea", "fr-FR", ("generative", "neural")), "de": ("Vicki", "de-DE", ("generative", "neural")),
         "it": ("Bianca", "it-IT", ("generative", "neural"))}


def voz(texto: str, idioma: str = "pt") -> dict:
    """Text → MP3 (Polly, the voice of `idioma`) for voice notes; the agent container has no AWS credentials."""
    texto = str(texto or "").strip()[:2900]
    if not texto:
        return {"error": "texto vazio"}
    import base64

    import boto3

    if "polly" not in _aws:
        _aws["polly"] = boto3.client("polly", region_name=REGION)
    if str(idioma or "pt") not in VOZES:
        return {"error": f"sem voz para o idioma {str(idioma)[:8]}"}
    nome, lingua, motores = VOZES[str(idioma or "pt")]
    # two tries per engine, then an error (the text answer still goes)
    erro = ""
    for motor in motores:
        for tentativa in range(2):
            try:
                r = _aws["polly"].synthesize_speech(Text=texto, VoiceId=nome, LanguageCode=lingua, Engine=motor,
                                                    OutputFormat="mp3", SampleRate="24000" if motor != "standard" else "22050")
                return {"mp3": base64.b64encode(r["AudioStream"].read()).decode(), "motor": motor, "voz": nome}
            except Exception as exc:
                erro = str(exc)[:200]
                time.sleep(1 + tentativa)
    return {"error": f"voz indisponível ({nome}): {erro}"}


GCP_WIF = Path("/opt/a0/usr/segredos/vertex_matheus_wif.json")  # external_account config (no secret in it)
_gcp = {"cred": None}
_gcp_lock = threading.Lock()  # its own lock: a slow Google call must never hold up the Bedrock token


def gcp_token() -> dict:
    """Short-lived Google Cloud token for Vertex AI, from this VM's AWS role through Workload Identity
    Federation: the organization blocks service-account keys, and no long-lived secret is kept here."""
    if not GCP_WIF.is_file():
        return {"error": "federação AWS→Google não configurada"}
    import google.auth
    import google.auth.transport.requests

    with _gcp_lock:
        if _gcp["cred"] is None:
            _gcp["cred"], _ = google.auth.load_credentials_from_file(
                str(GCP_WIF), scopes=["https://www.googleapis.com/auth/cloud-platform"])
        cred = _gcp["cred"]
        if not cred.valid:
            cred.refresh(google.auth.transport.requests.Request())
    return {"token": cred.token, "expira": cred.expiry.timestamp() if cred.expiry else time.time() + 1800}


USAGE_FILE = Path(os.environ.get("USAGE_FILE", "/var/lib/agentepessoal/uso.jsonl"))
USAGE_TAIL = 256 * 1024  # the usage block is in the last event of a response
DUMP_DIR = USAGE_FILE.parent / "pedidos"  # exists only while debugging the prompt cache
_usage_lock = threading.Lock()


def _last_usage(tail: bytes) -> dict:
    """The last `"usage": {...}` object in a (streamed) response, whatever the API flavour."""
    text = tail.decode("utf-8", "ignore")
    decoder = json.JSONDecoder()
    for m in reversed(list(re.finditer(r'"usage"\s*:\s*\{', text))):
        try:
            return decoder.raw_decode(text, m.end() - 1)[0]
        except ValueError:
            continue
    return {}


_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
PAPEIS = {"chat", "util"}


def rastreio_de(headers) -> dict:
    """20/10: which chat (conversa), scheduled task (rotina), agent (0 = main, n = helper) and role (chat model or
    utility model) made the call, from the X-A0-* headers (login_usuarios plugin). Only well-formed ids are kept."""
    out = {}
    for campo, nome in (("conversa", "X-A0-Conversa"), ("rotina", "X-A0-Rotina")):
        v = (headers.get(nome) or "").strip()
        if _ID.fullmatch(v):
            out[campo] = v
    agente = (headers.get("X-A0-Agente") or "").strip()
    if re.fullmatch(r"\d{1,2}", agente):
        out["agente"] = int(agente)
    papel = (headers.get("X-A0-Papel") or "").strip().lower()
    if papel in PAPEIS:
        out["papel"] = papel
    return out


def _sem_cache(valor):
    """The request without the cache markers (ours or the caller's), so they never change a fingerprint."""
    if isinstance(valor, dict):
        return {k: _sem_cache(v) for k, v in valor.items() if k not in ("cache_control", "cachePoint")}
    if isinstance(valor, list):
        return [_sem_cache(v) for v in valor if not (isinstance(v, dict) and set(v) == {"cachePoint"})]
    return valor


def _digital(parte) -> dict:
    """Size, hash of the first 2,000 characters and hash of the whole of one part of the prompt: never its text."""
    import hashlib

    texto = json.dumps(_sem_cache(parte), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    h = lambda t: hashlib.sha256(t.encode("utf-8", "ignore")).hexdigest()[:10]  # noqa: E731
    return {"n": len(texto), "ini": h(texto[:2000]), "todo": h(texto)}


def impressao(dados, converse: bool = False) -> dict:
    """20/10 (cache diagnosis): fingerprints of the start of the prompt, by part, so a cache miss shows what changed.
    instrucoes = system prompt (Converse `system`; Responses `instructions` + leading system/developer items; Chat
    leading system messages); ferramentas = the tool list; primeira = the first message after the instructions;
    mensagens = how many messages (a drop means the history was summarized)."""
    if not isinstance(dados, dict):
        return {}
    if converse:
        instr, msgs = dados.get("system"), dados.get("messages") or []
        ferr = (dados.get("toolConfig") or {}).get("tools")
    else:
        msgs = dados.get("input") if "input" in dados else dados.get("messages")
        msgs = msgs if isinstance(msgs, list) else ([msgs] if msgs else [])
        i = 0
        while i < len(msgs) and isinstance(msgs[i], dict) and msgs[i].get("role") in ("system", "developer"):
            i += 1
        instr = ([dados["instructions"]] if dados.get("instructions") else []) + msgs[:i]
        msgs, ferr = msgs[i:], dados.get("tools")
    out = {"mensagens": len(msgs)}
    for nome, parte in (("instrucoes", instr), ("ferramentas", ferr), ("primeira", msgs[0] if msgs else None)):
        if parte:
            out[nome] = _digital(parte)
    return out


def _gravado_1h(u: dict) -> int:
    """Converse reports the cache writes by lifetime (cacheDetails); the 1-hour ones cost more (2x instead of 1.25x)."""
    return sum(int(d.get("inputTokens") or 0) for d in (u.get("cacheDetails") or [])
               if isinstance(d, dict) and d.get("ttl") == "1h")


def log_usage(path: str, body: bytes | None, status: int, tail: bytes, seconds: float, dono: str = "",
              rastreio: dict | None = None) -> None:
    """One JSON line per model call: model, input/cached/output tokens and duration (for the
    context-economy measurements), and (20/10) which chat/routine/agent made it plus fingerprints of the start of the
    prompt (sizes and hashes only, never text). Never breaks the proxied call."""
    try:
        u = _last_usage(tail)
        if not u:
            return
        model, dados = "", None
        if body:
            try:
                dados = json.loads(body)
                model = dados.get("model", "") if isinstance(dados, dict) else ""
            except ValueError:
                pass
        if not model and "/model/" in path:
            model = path.split("/model/", 1)[1].split("/", 1)[0]
        details = u.get("input_tokens_details") or u.get("prompt_tokens_details") or {}
        row = {
            "em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "modelo": model,
            "status": status,
            # Converse (Claude) counts inputTokens WITHOUT the cached part; the log keeps entrada = everything sent
            "entrada": (u.get("inputTokens", 0) + (u.get("cacheReadInputTokens") or 0) + (u.get("cacheWriteInputTokens") or 0)
                        if "inputTokens" in u else u.get("input_tokens", u.get("prompt_tokens", 0))),
            "cache": details.get("cached_tokens", u.get("cacheReadInputTokens", 0)) or 0,
            "cache_gravado": details.get("cache_write_tokens", u.get("cacheWriteInputTokens", 0)) or 0,
            "saida": u.get("output_tokens", u.get("completion_tokens", u.get("outputTokens", 0))),
            "segundos": round(seconds, 1),
            "bytes_pedido": len(body or b""),
        }
        if _gravado_1h(u):  # part of cache_gravado (not added to it) written with the 1-hour lifetime
            row["cache_gravado_1h"] = _gravado_1h(u)
        if re.fullmatch(r"[a-z0-9_-]{1,32}", dono or ""):  # whose chat (login_usuarios: spending per person)
            row["dono"] = dono
        row.update(rastreio or {})
        if isinstance(dados, dict):
            row["api"] = "converse" if "/converse" in path else "responses" if "/responses" in path else "chat"
            for campo in ("prompt_cache_key", "prompt_cache_retention"):
                if isinstance(dados.get(campo), str):
                    row[campo.replace("prompt_", "")] = dados[campo][:80]
            row.update(impressao(dados, "/converse" in path))
        with _usage_lock, USAGE_FILE.open("a") as f:
            f.write(json.dumps(row) + "\n")
        if body and DUMP_DIR.is_dir():  # debugging only: `mkdir` the folder to capture request bodies
            names = sorted(DUMP_DIR.glob("*.json"))
            for old in names[:-9]:
                old.unlink(missing_ok=True)
            (DUMP_DIR / f"{time.time():.3f}.json").write_bytes(body)
    except Exception:
        pass


CACHE_PONTO = {"cachePoint": {"type": "default"}}
CACHE_PONTO_1H = {"cachePoint": {"type": "default", "ttl": "1h"}}
_CONVERSE = re.compile(r"^/model/[^/]*anthropic[^/]*/converse(-stream)?$")


def conversa_humana(rastreio: dict | None) -> bool:
    """20/10: a person's chat (main agent, chat model, not a scheduled task): someone who may answer 5 to 60 minutes
    later. Routines, helpers and the utility model run step after step and keep the 5-minute cache."""
    r = rastreio or {}
    return bool(r.get("conversa")) and not r.get("rotina") and r.get("agente") == 0 and r.get("papel") == "chat"


def com_cache(path: str, body: bytes | None, longo: bool = False) -> bytes | None:
    """20/10: Claude on Bedrock only caches up to an explicit cachePoint (the OpenAI-style models cache by themselves).
    For a Converse call to a Claude model with no cachePoint of its own, mark the end of the system prompt and the end
    of the last message: the next call of the same chat reads all of that from the cache and only pays the new part.
    `longo` (a person's chat, see conversa_humana): both points live 1 hour instead of 5 minutes — writing costs 2x
    instead of 1.25x the input price, but an answer after a 5-60 min pause reads the whole history (0.1x) instead of
    writing it all again. Anything that does not parse, or already has cache points, goes through unchanged."""
    if not body or not _CONVERSE.match(path.split("?", 1)[0]):
        return body
    try:
        dados = json.loads(body)
        if "cachePoint" in body.decode("utf-8", "ignore"):
            return body
        ponto = CACHE_PONTO_1H if longo else CACHE_PONTO
        sistema, mensagens = dados.get("system"), dados.get("messages")
        mudou = False
        if isinstance(sistema, list) and sistema:
            sistema.append(json.loads(json.dumps(ponto)))
            mudou = True
        if isinstance(mensagens, list) and mensagens and isinstance(mensagens[-1].get("content"), list) \
                and mensagens[-1]["content"]:
            mensagens[-1]["content"].append(json.loads(json.dumps(ponto)))
            mudou = True
        return json.dumps(dados, ensure_ascii=False).encode() if mudou else body
    except Exception:
        return body


_OPENAI_CACHE = re.compile(r"^/(openai/)?v1/(responses|chat/completions)$")
RETENCAO = "24h"  # tested 20/10 on Bedrock: accepted values are "in_memory" and "24h"


def chave_cache(rastreio: dict | None) -> str:
    """A stable prompt_cache_key per routine (all its runs share the instructions and tools) or per chat, and per
    agent and role (helpers and the utility model have prompts of their own). Empty when the caller is unknown."""
    r = rastreio or {}
    dono = f"r-{r['rotina']}" if r.get("rotina") else f"c-{r['conversa']}" if r.get("conversa") else ""
    if not dono:
        return ""
    return f"a0-{dono}-a{r.get('agente', 0)}" + ("-u" if r.get("papel") == "util" else "")


def com_chave(path: str, body: bytes | None, rastreio: dict | None) -> bytes | None:
    """20/10: for the OpenAI-style models (GPT on Bedrock, Responses and Chat Completions) of a known chat or routine,
    add prompt_cache_key (calls sharing a start go to the same cache machine) and prompt_cache_retention 24h (the
    cache outlives the 30-minute default between a routine's runs) — each only when the request does not bring its
    own. Anything else, or anything that does not parse, goes through unchanged."""
    chave = chave_cache(rastreio)
    if not body or not chave or not _OPENAI_CACHE.match(path.split("?", 1)[0]):
        return body
    try:
        dados = json.loads(body)
        if not isinstance(dados, dict):
            return body
        mudou = False
        if "prompt_cache_key" not in dados:
            dados["prompt_cache_key"] = chave
            mudou = True
        if "prompt_cache_retention" not in dados:
            dados["prompt_cache_retention"] = RETENCAO
            mudou = True
        return json.dumps(dados, ensure_ascii=False).encode() if mudou else body
    except Exception:
        return body


def mark_activity() -> None:
    try:
        ACTIVITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACTIVITY_FILE.touch()
    except OSError:
        pass


PASSAGEIRO = (429, 500, 502, 503, 504)
TENTATIVAS, ESPERA_MAX, ESPERA_CONEXAO = 2, 10.0, 2.0
_conexao = http.client.HTTPSConnection  # tests put a fake upstream here


def abrir_upstream(upstream: str, metodo: str, path: str, body: bytes | None, headers: dict):
    """(connection, response) of the upstream call, tried once more when it was refused for a moment; on a final
    connection failure, (the error, None). The response is returned before any byte is read, so nothing went out yet."""
    for tentativa in range(TENTATIVAS):
        ultima = tentativa + 1 == TENTATIVAS
        conn = _conexao(upstream, timeout=240, context=_ssl)
        try:
            conn.request(metodo, path, body=body, headers=headers)
            resp = conn.getresponse()
        except TimeoutError:
            conn.close()
            raise  # hung: the agent retries it, not us (another 240 s here would only double the wait)
        except (OSError, http.client.HTTPException) as exc:
            conn.close()
            if ultima:
                return exc, None
            print(f"bedrock_proxy: {upstream} unreachable ({exc}); trying once more", flush=True)
            time.sleep(ESPERA_CONEXAO)
            continue
        if resp.status in PASSAGEIRO and not ultima:
            try:
                espera = min(float(resp.getheader("Retry-After") or 0) or 2.0, ESPERA_MAX)
            except ValueError:
                espera = 2.0
            resp.read()
            conn.close()
            print(f"bedrock_proxy: {upstream} answered {resp.status}; trying once more in {espera:.0f} s", flush=True)
            time.sleep(espera)
            continue
        return conn, resp
    return RuntimeError("no attempt left"), None


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _reply(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _arquivos(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}") if length else {}
            if self.path == "/arquivos/presign":
                out = presign(data.get("chat", ""), data.get("name", ""), data.get("size", 0))
                return self._reply(400 if "error" in out else 200, out)
            if self.path == "/arquivos/puxar":
                return self._reply(200, {"done": pull(float(data.get("wait", 40)))})
            if self.path == "/arquivos/gcp_token":
                out = gcp_token()
                return self._reply(400 if "error" in out else 200, out)
            if self.path == "/arquivos/pegasus":
                mark_activity()
                out = pegasus(data.get("arquivo", ""), data.get("prompt", ""))
                return self._reply(400 if "error" in out else 200, out)
            if self.path == "/arquivos/conteudo":
                out = link_conteudo(data.get("chave", ""))
                return self._reply(400 if "error" in out else 200, out)
            if self.path == "/arquivos/voz":
                out = voz(data.get("texto", ""), str(data.get("idioma") or "pt"))
                return self._reply(400 if "error" in out else 200, out)
            return self._reply(404, {"error": "not found"})
        except Exception as exc:
            return self._reply(500, {"error": str(exc)[:300]})

    def _proxy(self) -> None:
        if self.path.startswith("/arquivos/"):
            return self._arquivos()
        if self.path == "/health":  # for saude.py: no upstream call, and not an "activity" for the idle watchdog
            try:
                token = bool(bearer_token())
            except Exception:
                token = False
            return self._reply(200 if token else 503, {"ok": token, "token": token})
        mark_activity()
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
        upstream, path = UPSTREAM, self.path
        rastreio = rastreio_de(self.headers)
        if path.startswith("/typesafe/"):
            key = typesafe_key()
            if not key:
                msg = b'{"error": "TypeSafe API key not configured (SSM /agentepessoal/typesafe-api-key)"}'
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
                return
            upstream, path = TYPESAFE_HOST, path[len("/typesafe"):]
            headers["Authorization"] = f"Bearer {key}"
        elif path.startswith("/bedrock/"):
            upstream, path = RUNTIME, path[len("/bedrock"):]
            headers["Authorization"] = f"Bearer {bearer_token()}"
            body = com_cache(path, body, conversa_humana(rastreio))
        else:
            headers["Authorization"] = f"Bearer {bearer_token()}"
            body = com_chave(path, body, rastreio)
        if body is not None:
            headers["Content-Length"] = str(len(body))

        # 240 s without a byte from upstream = hung call: fail it so Agent Zero retries (with 900 s a
        # stuck model call left a Telegram request "Calling LLM…" for 15 minutes).
        started = time.time()
        conn, resp = abrir_upstream(upstream, self.command, path, body, headers)
        if resp is None:
            return self._reply(502, {"error": f"model upstream unreachable: {conn}"})
        try:
            self.send_response(resp.status)
            for key, value in resp.getheaders():
                if key.lower() not in SKIP_RESPONSE_HEADERS:
                    self.send_header(key, value)
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Connection", "close")
            self.end_headers()
            tail = b""
            while True:
                chunk = resp.read1(65536)
                if not chunk:
                    break
                tail = (tail + chunk)[-USAGE_TAIL:]
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            if upstream != TYPESAFE_HOST:
                log_usage(path, body, resp.status, tail, time.time() - started,
                          (self.headers.get("X-A0-Dono") or "").strip().lower(), rastreio)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            conn.close()
            self.close_connection = True

    do_GET = do_POST = do_DELETE = _proxy

    def log_message(self, fmt, *args):  # keep journald quiet
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(LISTEN, Handler).serve_forever()

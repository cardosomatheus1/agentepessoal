"""Local proxy for the agent's model APIs, so no keys live inside the Agent Zero container.

- /openai/...   -> Bedrock's OpenAI-compatible endpoint (bedrock-mantle), short-term token from the VM role
- /bedrock/...  -> Bedrock runtime (Converse API, for the Claude models), same token
- /typesafe/... -> TypeSafe (Jev), API key read from SSM /agentepessoal/typesafe-api-key
- /arquivos/...  -> big-file uploads into a chat: presigned S3 PUT (from the VM role) and
                    an on-demand run of entrada.sh, which moves the file into the chat's anexos/

Agent Zero only reads its API key at startup, while Bedrock short-term API keys
expire. This proxy injects a fresh bearer token (generated from the VM's IAM
role) into every request and streams the response back unchanged. It also
records the time of the last model call, which the idle watchdog reads, and appends each
call's token usage (input, cached, output) to /var/lib/agentepessoal/uso.jsonl.
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

HOP_HEADERS = {"host", "authorization", "content-length", "connection", "accept-encoding", "transfer-encoding"}
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


def log_usage(path: str, body: bytes | None, status: int, tail: bytes, seconds: float) -> None:
    """One JSON line per model call: model, input/cached/output tokens and duration (for the
    context-economy measurements). Never breaks the proxied call."""
    try:
        u = _last_usage(tail)
        if not u:
            return
        model = ""
        if body:
            try:
                model = json.loads(body).get("model", "")
            except ValueError:
                pass
        if not model and "/model/" in path:
            model = path.split("/model/", 1)[1].split("/", 1)[0]
        details = u.get("input_tokens_details") or u.get("prompt_tokens_details") or {}
        row = {
            "em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "modelo": model,
            "status": status,
            "entrada": u.get("input_tokens", u.get("prompt_tokens", u.get("inputTokens", 0))),
            "cache": details.get("cached_tokens", u.get("cacheReadInputTokens", 0)) or 0,
            "cache_gravado": details.get("cache_write_tokens", u.get("cacheWriteInputTokens", 0)) or 0,
            "saida": u.get("output_tokens", u.get("completion_tokens", u.get("outputTokens", 0))),
            "segundos": round(seconds, 1),
            "bytes_pedido": len(body or b""),
        }
        with _usage_lock, USAGE_FILE.open("a") as f:
            f.write(json.dumps(row) + "\n")
        if body and DUMP_DIR.is_dir():  # debugging only: `mkdir` the folder to capture request bodies
            names = sorted(DUMP_DIR.glob("*.json"))
            for old in names[:-9]:
                old.unlink(missing_ok=True)
            (DUMP_DIR / f"{time.time():.3f}.json").write_bytes(body)
    except Exception:
        pass


def mark_activity() -> None:
    try:
        ACTIVITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACTIVITY_FILE.touch()
    except OSError:
        pass


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
            if self.path == "/arquivos/pegasus":
                mark_activity()
                out = pegasus(data.get("arquivo", ""), data.get("prompt", ""))
                return self._reply(400 if "error" in out else 200, out)
            return self._reply(404, {"error": "not found"})
        except Exception as exc:
            return self._reply(500, {"error": str(exc)[:300]})

    def _proxy(self) -> None:
        if self.path.startswith("/arquivos/"):
            return self._arquivos()
        mark_activity()
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
        upstream, path = UPSTREAM, self.path
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
        else:
            headers["Authorization"] = f"Bearer {bearer_token()}"
        if body is not None:
            headers["Content-Length"] = str(len(body))

        # 240 s without a byte from upstream = hung call: fail it so Agent Zero retries (with 900 s a
        # stuck model call left a Telegram request "Calling LLM…" for 15 minutes).
        conn = http.client.HTTPSConnection(upstream, timeout=240, context=_ssl)
        started = time.time()
        try:
            conn.request(self.command, path, body=body, headers=headers)
            resp = conn.getresponse()
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
                log_usage(path, body, resp.status, tail, time.time() - started)
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

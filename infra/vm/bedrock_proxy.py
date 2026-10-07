"""Local proxy for the agent's model APIs, so no keys live inside the Agent Zero container.

- /openai/...   -> Bedrock's OpenAI-compatible endpoint (bedrock-mantle), short-term token from the VM role
- /typesafe/... -> TypeSafe (Jev), API key read from SSM /agentepessoal/typesafe-api-key

Agent Zero only reads its API key at startup, while Bedrock short-term API keys
expire. This proxy injects a fresh bearer token (generated from the VM's IAM
role) into every request and streams the response back unchanged. It also
records the time of the last model call, which the idle watchdog reads.
"""

import http.client
import http.server
import os
import ssl
import threading
import time
from datetime import timedelta
from pathlib import Path

from aws_bedrock_token_generator import provide_token

REGION = os.environ.get("AWS_REGION", "us-east-1")
UPSTREAM = os.environ.get("UPSTREAM_HOST", f"bedrock-mantle.{REGION}.api.aws")
LISTEN = (os.environ.get("LISTEN_HOST", "0.0.0.0"), int(os.environ.get("LISTEN_PORT", "8787")))
ACTIVITY_FILE = Path(os.environ.get("ACTIVITY_FILE", "/var/lib/agentepessoal/last-activity"))
TOKEN_TTL = 30 * 60  # refresh well before the 1h token expiry
TYPESAFE_HOST = "api.typesafe.ai"
TYPESAFE_PARAM = "/agentepessoal/typesafe-api-key"

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


def mark_activity() -> None:
    try:
        ACTIVITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACTIVITY_FILE.touch()
    except OSError:
        pass


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _proxy(self) -> None:
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
        else:
            headers["Authorization"] = f"Bearer {bearer_token()}"
        if body is not None:
            headers["Content-Length"] = str(len(body))

        conn = http.client.HTTPSConnection(upstream, timeout=900, context=_ssl)
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
            while True:
                chunk = resp.read1(65536)
                if not chunk:
                    break
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
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

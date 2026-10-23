"""Repasse do MCP do GitHub para o Hermes (mcp.sh): recebe as chamadas do Hermes na porta 8766 e as manda a
https://api.githubcopilot.com com os cabeçalhos do A0 (o token, lido de /segredos/github_headers.json, que só este
container vê). A resposta volta em pedaços, como chega (o MCP responde em SSE). Só a biblioteca padrão."""
import http.client
import http.server
import json
import ssl
import sys

DESTINO = "api.githubcopilot.com"
CABECALHOS = "/segredos/github_headers.json"
FORA = {"host", "connection", "content-length", "transfer-encoding", "accept-encoding", "authorization"}
_ssl = ssl.create_default_context()


def cabecalhos_do_token() -> dict:
    try:
        with open(CABECALHOS, encoding="utf-8") as f:
            d = json.load(f)
        return {str(k): str(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


class Repasse(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _repassar(self):
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(tamanho) if tamanho else None
        cab = {k: v for k, v in self.headers.items() if k.lower() not in FORA}
        cab.update(cabecalhos_do_token())
        if corpo is not None:
            cab["Content-Length"] = str(len(corpo))
        conn = http.client.HTTPSConnection(DESTINO, timeout=300, context=_ssl)
        try:
            conn.request(self.command, self.path, body=corpo, headers=cab)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                    self.send_header(k, v)
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                pedaco = resp.read1(65536)
                if not pedaco:
                    break
                self.wfile.write(b"%x\r\n%s\r\n" % (len(pedaco), pedaco))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
        except (OSError, http.client.HTTPException) as exc:
            try:
                msg = json.dumps({"error": f"github indisponível: {type(exc).__name__}"}).encode()
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
            except OSError:
                pass
        finally:
            conn.close()
            self.close_connection = True

    do_GET = do_POST = do_DELETE = _repassar

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    http.server.ThreadingHTTPServer(("0.0.0.0", porta), Repasse).serve_forever()

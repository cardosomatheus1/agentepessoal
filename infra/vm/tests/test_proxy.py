"""The model proxy: /health answers locally; a call refused for a moment (connection refused, 429, 5xx) is tried once
more, anything else passes straight through. Fake upstream and token, local port only. Run from the repository root:
python3 infra/vm/tests/test_proxy.py"""

import http.server
import importlib.util
import json
import sys
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


class RespostaFalsa:
    def __init__(self, status, corpo=b"", cabecalhos=None):
        self.status, self._corpo, self._cab = status, corpo, cabecalhos or {}
        self._lido = False

    def getheader(self, nome, padrao=None):
        return self._cab.get(nome, padrao)

    def getheaders(self):
        return [("Content-Type", "application/json"), *self._cab.items()]

    def read(self, n=-1):
        corpo, self._corpo = self._corpo, b""
        return corpo

    def read1(self, n=-1):
        return self.read()


def main() -> int:
    estado = {"token_ok": True}
    gerador = types.ModuleType("aws_bedrock_token_generator")

    def provide_token(region, expiry):
        if not estado["token_ok"]:
            raise RuntimeError("sem credencial")
        return "tok"

    gerador.provide_token = provide_token
    sys.modules["aws_bedrock_token_generator"] = gerador
    spec = importlib.util.spec_from_file_location("proxy_teste", RAIZ / "infra" / "vm" / "bedrock_proxy.py")
    p = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)
    p.ESPERA_MAX = p.ESPERA_CONEXAO = 0
    p.mark_activity = p.log_usage = lambda *a, **k: None
    roteiro, pedidos = [], []

    class ConexaoFalsa:
        def __init__(self, host, timeout=0, context=None):
            self.host = host

        def request(self, metodo, path, body=None, headers=None):
            pedidos.append((self.host, path, headers.get("Authorization")))
            self._proximo = roteiro.pop(0)
            if isinstance(self._proximo, Exception):
                raise self._proximo

        def getresponse(self):
            return self._proximo

        def close(self):
            pass

    p._conexao = ConexaoFalsa
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), p.Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{servidor.server_address[1]}"
    falhas = []

    def ok(cond, msg):
        if not cond:
            falhas.append(msg)

    def chamar(caminho="/openai/v1/chat/completions"):
        req = urllib.request.Request(base + caminho, data=b'{"model": "luna"}' if caminho != "/health" else None,
                                     method="POST" if caminho != "/health" else "GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    try:
        roteiro[:] = [RespostaFalsa(503), RespostaFalsa(200, b'{"ok": 1}')]
        pedidos.clear()
        ok(chamar() == (200, b'{"ok": 1}') and len(pedidos) == 2, f"503 passageiro: tenta de novo e entrega ({pedidos})")
        ok(pedidos[0][2] == "Bearer tok", "leva a chave gerada aqui")
        roteiro[:] = [RespostaFalsa(429, cabecalhos={"Retry-After": "1"}), RespostaFalsa(429, b'{"erro": "limite"}')]
        pedidos.clear()
        ok(chamar()[0] == 429 and len(pedidos) == 2, "429 de novo: só uma nova tentativa, e o agente vê o 429")
        roteiro[:] = [ConnectionRefusedError("recusada"), RespostaFalsa(200, b"{}")]
        pedidos.clear()
        ok(chamar()[0] == 200 and len(pedidos) == 2, "conexão recusada por um instante: tenta de novo")
        roteiro[:] = [ConnectionRefusedError("recusada"), ConnectionRefusedError("recusada")]
        status, corpo = chamar()
        ok(status == 502 and b"unreachable" in corpo, f"fora do ar: 502 claro ({status} {corpo[:60]})")
        roteiro[:] = [RespostaFalsa(400, b'{"erro": "pedido ruim"}')]
        pedidos.clear()
        ok(chamar()[0] == 400 and len(pedidos) == 1, "erro do pedido (400) passa direto, sem repetir")
        pedidos.clear()
        status, corpo = chamar("/health")
        ok(status == 200 and json.loads(corpo)["token"] and not pedidos, "saúde responde aqui, sem chamar a AWS")
        estado["token_ok"] = False
        p._token.update(value="", at=0.0)
        ok(chamar("/health")[0] == 503, "sem conseguir a chave, a saúde diz que não está bem")
        # links for post files (13/10: the agent container has no AWS credentials)
        class S3Falso:
            def head_object(self, Bucket, Key):
                if "falta" in Key:
                    raise RuntimeError("404")

            def generate_presigned_url(self, op, Params, ExpiresIn):
                return f"https://s3/{Params['Bucket']}/{Params['Key']}?{op}&{ExpiresIn}"
        p.BUCKET, p._s3["client"] = "balde", S3Falso()
        r = p.link_conteudo("conteudo/semana1/pov.mp4")
        ok(r.get("url") == "https://s3/balde/conteudo/semana1/pov.mp4?get_object&3600", f"link de 1 h para ler ({r})")
        for ruim in ("entrada/chats/x/y.mp4", "conteudo/../segredo", "conteudo/", ""):
            ok("error" in p.link_conteudo(ruim), f"fora de conteudo/ é recusado: {ruim!r}")
        ok("não encontrado" in p.link_conteudo("conteudo/falta.mp4").get("error", ""), "arquivo que não existe")
        req = urllib.request.Request(f"{base}/arquivos/conteudo", data=b'{"chave": "conteudo/a.mp4"}', method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            ok(json.loads(r.read())["url"].endswith("conteudo/a.mp4?get_object&3600"), "rota /arquivos/conteudo")
    finally:
        servidor.shutdown()
    for f in falhas:
        print("FALHA", f)
    print("proxy:", "ok" if not falhas else f"{len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

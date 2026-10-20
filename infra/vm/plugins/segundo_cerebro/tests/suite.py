"""Tests of the Segundo Cérebro gateway and its Node process (synthetic data only; temporary folders; a fake "Next"
server written in Python that echoes what it received). Flask sessions are real signed test-client sessions.
Run with rodar_suites_locais.py, implantar.py (staging copy on the VM) or directly."""

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HASH = hashlib.sha256(b"login-teste:senha-teste").hexdigest()

SERVIDOR_FALSO = r'''
import hashlib, json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
AQUI = os.path.dirname(os.path.abspath(__file__))
MODO = open(os.path.join(AQUI, "modo")).read().strip() if os.path.exists(os.path.join(AQUI, "modo")) else "ok"
if MODO == "morre":
    sys.exit(3)
class H(BaseHTTPRequestHandler):
    def _responder(self, corpo_ok):
        if MODO == "mudo":
            return
        auth = self.headers.get("Authorization", "")
        valido = auth.startswith("Bearer ") and hashlib.sha256(auth[7:].encode()).hexdigest() == os.environ["SECOND_BRAIN_TOKEN_SHA256"]
        if self.path.startswith("/api/") and (not valido or MODO == "recusa") and MODO != "aberto":
            st, corpo, tipo = 401, b'{"erro":"nao autorizado"}', "application/json"
        elif self.path == "/segundo-cerebro/":
            st, corpo, tipo = 308, b"", "text/plain"
        else:
            cab = {k.lower(): v for k, v in self.headers.items()}
            if "authorization" in cab:  # say whether it matched, never echo the bearer itself
                cab["authorization"] = "valido" if valido else "invalido"
            eco = {"caminho": self.path, "metodo": self.command, "cabecalhos": cab, "ambiente": dict(os.environ),
                   "dono": "matheus"}
            corpo = json.dumps(eco).encode() if MODO != "grande" else b"x" * (9 * 1024 * 1024)
            st, tipo = 200, "application/json" if self.path.startswith("/api/") else "text/html; charset=utf-8"
        self.send_response(st)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Set-Cookie", "next-interno=1")
        self.send_header("X-Powered-By", "Next.js")
        if st == 308:
            self.send_header("Location", "/segundo-cerebro")
        self.end_headers()
        if corpo_ok:
            self.wfile.write(corpo)
    def do_GET(self): self._responder(True)
    def do_HEAD(self): self._responder(False)
    def log_message(self, *a): pass
HTTPServer((os.environ["HOSTNAME"], int(os.environ["PORT"])), H).serve_forever()
'''


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Suite:
    def __init__(self):
        self.g = _carregar("segundo_cerebro_gateway_teste", RAIZ / "helpers" / "gateway.py")
        self.p = _carregar("segundo_cerebro_processo_teste", RAIZ / "helpers" / "processo.py")
        self.resultados = []
        self._tmp = []
        self._procs = []

    # ---------- fixtures ----------
    def _pasta(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="segundo-cerebro-teste-"))
        self._tmp.append(d)
        return d

    def _instalacao(self, modo: str = "ok", nome: str = "a" * 40):
        """state root with releases/<nome>/server.js (the fake server) and atual -> nome; a synthetic data root."""
        base = self._pasta()
        estado, dados = base / "estado", base / "dados"
        rel = estado / "releases" / nome
        rel.mkdir(parents=True)
        (rel / "server.js").write_text(SERVIDOR_FALSO)
        if modo != "ok":
            (rel / "modo").write_text(modo)
        (estado / "atual").write_text(nome + "\n")
        for arq, conteudo in (("memoria/decisoes/matheus.json", '{"decisoes": []}'), ("memoria/usuarios/matheus.md", "- x\n"),
                              ("fios/matheus.json", '{"fios": []}'), ("fios/fernanda.json", '{"fios": [{"titulo": "SENTINELA"}]}')):
            (dados / arq).parent.mkdir(parents=True, exist_ok=True)
            (dados / arq).write_text(conteudo)
        proc = self.p.Processo(raiz_estado=estado, raiz_dados=str(dados), node=sys.executable, prazo=8, espera_falha=30)
        self._procs.append(proc)
        return proc, estado, dados

    def _app(self, processo, obter_hash=lambda: HASH):
        from flask import Flask

        app = Flask("teste_segundo_cerebro")
        app.secret_key = "chave-de-teste-nao-real"
        app.config["SESSION_COOKIE_NAME"] = "session_teste"

        @app.route("/")
        def inicio():
            return "inicio-core"

        @app.route("/api/chat", methods=["GET", "POST"])
        def chat():
            return "chat-core"

        @app.route("/login")
        def login():
            return "login-core"

        @app.route("/segundo-cerebroX")
        def parecido():
            return "parecido-core"

        ok(self.g.registrar(app, obter_hash=obter_hash, processo=processo), "gateway registrado")
        ok(not self.g.registrar(app, obter_hash=obter_hash, processo=processo), "registrar de novo não duplica")
        return app

    @staticmethod
    def _cliente(app, sessao: dict | None):
        c = app.test_client()
        if sessao is not None:
            with c.session_transaction() as s:
                s.update(sessao)
        return c

    MATHEUS = {"authentication": HASH, "usuario": "matheus", "user_id": "matheus"}

    def _matheus(self, modo="ok"):
        proc, estado, dados = self._instalacao(modo)
        return self._cliente(self._app(proc), dict(self.MATHEUS)), proc, estado, dados

    # ---------- decision (pure) ----------
    def t_classificar_caminhos(self):
        g = self.g
        for c, tipo in (("/segundo-cerebro", "pagina"), ("/segundo-cerebro/", "pagina"), ("/api/segundo-cerebro", "api"),
                        ("/_next/static/chunks/0kfq499m55zc7.js", "estatico"), ("/_next/static/chunks/19421y8fe8o5n.css", "estatico"),
                        ("/_next/static/PQgxccOV4fZ3HKO9L_iRd/_buildManifest.js", "estatico"),
                        ("/icon.svg", "publico"), ("/manifest.webmanifest", "publico"),
                        ("/icon.svg.backup", None), ("/manifest.webmanifest/", None),
                        ("/_next/static/media/fef07dbb0973bf53-s.3p2_lha1f2xer.woff2", "estatico"),
                        ("/", None), ("/api/chat", None), ("/login", None), ("/segundo-cerebroX", None), ("/api/segundo", None),
                        ("/segundo-cerebro/x", "invalido"), ("/api/segundo-cerebro/", "invalido"), ("/_next/image", "invalido"),
                        ("/_next/static/../../etc/passwd", "invalido"), ("/_next/static/a/../b.js", "invalido"),
                        ("/_next/static//a.js", "invalido"), ("/_next/static/a\\b.js", "invalido"),
                        ("/_next/static/%2e%2e/x.js", "invalido"), ("/_next/static/chunks/a.js.map", "invalido"),
                        ("/_next/static/chunks/a.html", "invalido"), ("/_next/static/", "invalido"),
                        ("/_next/static/.env", "invalido"), ("/_next/data/x.json", "invalido")):
            ok(g.classificar(c) == tipo, f"{c!r}: {g.classificar(c)!r} != {tipo!r}")

    def t_decidir_ordem(self):
        g, m = self.g, dict(self.MATHEUS)
        d = lambda **k: g.decidir(k.get("metodo", "GET"), k.get("caminho", "/api/segundo-cerebro"), k.get("cab", {}),
                                  k.get("q", []), k.get("s", m), k.get("h", HASH), k.get("corpo", 0)).status
        ok(d() == 200, "Matheus com sessão válida passa")
        ok(d(h=None) == 401 and d(h="") == 401, "login global desligado: 401 (nunca aberto)")
        ok(d(s={**m, "authentication": ""}, h="") == 401, "hash vazio na sessão e global vazio: 401")
        ok(d(s={}) == 401 and d(s={**m, "authentication": "velho"}) == 401, "sem sessão / sessão velha: 401")
        ok(d(s={**m, "authentication": None}) == 401, "authentication não-texto: 401")
        ok(d(s={**m, "usuario": "fernanda", "user_id": "fernanda"}) == 403, "outra pessoa: 403")
        ok(d(s={**m, "user_id": "fernanda"}) == 403 and d(s={**m, "usuario": "Matheus "}) == 403, "um campo errado: 403")
        ok(d(s={"authentication": HASH}) == 403, "sessão do login mestre (sem usuario): 403")
        ok(d(cab={"x-user": "matheus"}) == 403 and d(cab={"x-forwarded-user": "f"}) == 403 and d(cab={"remote-user": "f"}) == 403,
           "cabeçalho de identidade: 403")
        ok(d(q=[("user", "fernanda")]) == 403 and d(q=[("USUARIO", "x")]) == 403 and d(q=[("tenant", "x")]) == 403,
           "consulta de identidade: 403")
        ok(d(q=[("x", "1")]) == 400, "API não aceita consulta")
        ok(d(caminho="/segundo-cerebro", q=[("_rsc", "1")]) == 200, "página aceita consulta inofensiva (não repassada)")
        ok(d(metodo="POST") == 405 and d(metodo="HEAD") == 405 and d(caminho="/segundo-cerebro", metodo="HEAD") == 200,
           "métodos por tipo")
        ok(d(corpo=10) == 413, "GET com corpo: 413")
        ok(d(s={}, cab={"x-user": "matheus"}) == 401, "forjar identidade sem sessão: 401")

    # ---------- Flask: auth ----------
    def t_sem_sessao_401(self):
        proc, *_ = self._instalacao()
        c = self._cliente(self._app(proc), None)
        for caminho in ("/segundo-cerebro", "/segundo-cerebro/", "/api/segundo-cerebro", "/_next/static/chunks/a.js",
                        "/icon.svg", "/manifest.webmanifest"):
            r = c.get(caminho)
            ok(r.status_code == 401, f"{caminho}: {r.status_code}")
            ok(r.headers["Cache-Control"] == "private, no-store" and "Cookie" in r.headers["Vary"], f"{caminho}: cabeçalhos")
        r = c.get("/segundo-cerebro")
        ok("/login?next=/segundo-cerebro" in r.get_data(as_text=True) and r.mimetype == "text/html", "página 401 leva ao login")
        ok(c.get("/api/segundo-cerebro").get_json() == {"erro": "Não autorizado."}, "API 401 em JSON")
        ok(not proc.rodando, "sem sessão, o Node nem sobe")

    def t_outro_usuario_403(self):
        proc, *_ = self._instalacao()
        app = self._app(proc)
        for sessao in ({"authentication": HASH, "usuario": "fernanda", "user_id": "fernanda"},
                       {"authentication": HASH, "usuario": "matheus", "user_id": "fernanda"},
                       {"authentication": HASH, "usuario": "fernanda", "user_id": "matheus"},
                       {"authentication": HASH}):
            c = self._cliente(app, sessao)
            ok(c.get("/api/segundo-cerebro").status_code == 403, f"API {sessao}")
            r = c.get("/segundo-cerebro")
            ok(r.status_code == 403 and "/logout" in r.get_data(as_text=True), f"página {sessao}")
        ok(not proc.rodando, "outra pessoa não faz o Node subir")

    def t_sessao_velha_401(self):
        proc, *_ = self._instalacao()
        app = self._app(proc)
        velho = hashlib.sha256(b"login-teste:senha-antiga").hexdigest()
        c = self._cliente(app, {**self.MATHEUS, "authentication": velho})
        ok(c.get("/api/segundo-cerebro").status_code == 401, "senha trocada: a sessão antiga não vale")

    def t_hash_global_vazio_401(self):
        proc, *_ = self._instalacao()
        for h in (lambda: None, lambda: "", lambda: (_ for _ in ()).throw(RuntimeError("dotenv"))):
            app = self._app(proc, obter_hash=h)
            c = self._cliente(app, {**self.MATHEUS, "authentication": ""})
            ok(c.get("/api/segundo-cerebro").status_code == 401, "sem login global: 401, nunca aberto")
            c = self._cliente(app, dict(self.MATHEUS))
            ok(c.get("/segundo-cerebro").status_code == 401, "nem com sessão antiga")

    def t_identidade_forjada(self):
        proc, *_ = self._instalacao()
        app = self._app(proc)
        anonimo, matheus = self._cliente(app, None), self._cliente(app, dict(self.MATHEUS))
        for h in ({"X-User": "matheus"}, {"X-Login": "matheus"}, {"X-Tenant": "matheus"}, {"X-Forwarded-User": "matheus"},
                  {"Authorization": "Bearer qualquer"}):
            ok(anonimo.get("/api/segundo-cerebro", headers=h).status_code == 401, f"sem sessão + {h}: 401")
        for h in ({"X-User": "fernanda"}, {"X-Login": "fernanda"}, {"X-Tenant": "fernanda"}, {"X-User-Id": "fernanda"},
                  {"X-Remote-User": "f"}, {"X-A0-Usuario": "f"}, {"Remote-User": "f"}, {"X-Auth-Request-User": "f"}):
            ok(matheus.get("/api/segundo-cerebro", headers=h).status_code == 403, f"Matheus + {h}: 403")
            ok(matheus.get("/segundo-cerebro", headers=h).status_code == 403, f"página + {h}: 403")
        for q in ("user=fernanda", "usuario=fernanda", "user_id=fernanda", "tenant=x", "login=x", "dono=x"):
            ok(matheus.get(f"/api/segundo-cerebro?{q}").status_code == 403, f"?{q}: 403")
            ok(matheus.get(f"/segundo-cerebro?{q}").status_code == 403, f"página ?{q}: 403")
        ok(matheus.get("/api/segundo-cerebro?x=1").status_code == 400, "outra consulta na API: 400")
        ok(not proc.rodando, "nenhuma tentativa chegou ao Node")

    def t_metodos_405(self):
        proc, *_ = self._instalacao()
        c = self._cliente(self._app(proc), dict(self.MATHEUS))
        for caminho, permitidos in (("/segundo-cerebro", "GET, HEAD"), ("/_next/static/chunks/a.js", "GET, HEAD"),
                                    ("/icon.svg", "GET, HEAD"), ("/manifest.webmanifest", "GET, HEAD"),
                                    ("/api/segundo-cerebro", "GET")):
            for metodo in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE") + (("HEAD",) if "HEAD" not in permitidos else ()):
                r = c.open(caminho, method=metodo)
                ok(r.status_code == 405 and r.headers.get("Allow") == permitidos, f"{metodo} {caminho}: {r.status_code}")
        ok(c.get("/api/segundo-cerebro", data=b"x" * 10).status_code == 413, "GET com corpo: 413")
        ok(not proc.rodando, "métodos recusados não sobem o Node")

    # ---------- Flask: forwarding ----------
    def t_caminhos_permitidos(self):
        c, proc, *_ = self._matheus()
        r = c.get("/api/segundo-cerebro")
        ok(r.status_code == 200, f"API: {r.status_code} {r.get_data(as_text=True)[:200]}")
        eco = r.get_json()
        ok(eco["caminho"] == "/api/segundo-cerebro" and eco["metodo"] == "GET", f"repassado: {eco['caminho']}")
        r = c.get("/segundo-cerebro", headers={"Accept": "text/html"})
        ok(r.status_code == 200 and r.mimetype == "text/html", "página")
        ok(json.loads(r.get_data())["cabecalhos"].get("accept") == "text/html", "Accept repassado")
        ok(c.get("/segundo-cerebro?_rsc=abc").get_json(force=True)["caminho"] == "/segundo-cerebro", "consulta não repassada")
        r = c.get("/segundo-cerebro/")
        ok(r.status_code == 308 and r.headers["Location"] == "/segundo-cerebro", "barra final: redireciona do Next")
        r = c.get("/_next/static/chunks/0kfq499m55zc7.js")
        ok(r.status_code == 200 and r.get_json(force=True)["caminho"] == "/_next/static/chunks/0kfq499m55zc7.js", "asset")
        for caminho in ("/icon.svg", "/manifest.webmanifest"):
            r = c.get(caminho)
            ok(r.status_code == 200 and r.get_json(force=True)["caminho"] == caminho, f"recurso público permitido: {caminho}")
            ok(c.head(caminho).status_code == 200, f"HEAD {caminho}")
        r = c.head("/segundo-cerebro")
        ok(r.status_code == 200 and r.get_data() == b"", "HEAD sem corpo")
        for caminho in ("/segundo-cerebro", "/api/segundo-cerebro", "/_next/static/chunks/a.js",
                        "/icon.svg", "/manifest.webmanifest"):
            r = c.get(caminho)
            for k, v in (("Cache-Control", "private, no-store"), ("Content-Security-Policy", "frame-ancestors 'self'"),
                         ("X-Content-Type-Options", "nosniff")):
                ok(r.headers.get(k) == v, f"{caminho}: {k}={r.headers.get(k)!r}")
            ok("Cookie" in r.headers.get("Vary", ""), f"{caminho}: Vary Cookie")
            ok("next-interno" not in str(r.headers) and "X-Powered-By" not in r.headers, f"{caminho}: cabeçalhos do Next filtrados")
        ok(proc.rodando, "o Node subiu sob demanda")

    def t_travessia(self):
        c, proc, *_ = self._matheus()
        for caminho in ("/_next/static/../../etc/passwd", "/_next/static/%2e%2e/%2e%2e/etc/passwd", "/_next/static/%252e%252e/x.js",
                        "/segundo-cerebro/../api/chat", "/segundo-cerebro/x", "/api/segundo-cerebro/../../x",
                        "/api/segundo-cerebro/", "/_next/image?url=http://169.254.169.254/", "/_next/static//x.js",
                        "/_next/static/chunks/a.js%00.css", "/_next/static/chunks/..%2f..%2fx.js", "/_next/data/b/x.json"):
            r = c.get(caminho)
            ok(r.status_code in (404, 400), f"{caminho}: {r.status_code}")
            ok("inicio-core" not in r.get_data(as_text=True), f"{caminho}: não caiu numa rota do core")
        ok(not proc.rodando, "nada disso chegou ao Node")

    def t_rota_alheia_intocada(self):
        c, proc, *_ = self._matheus()
        anonimo = self._cliente(self._app(proc), None)
        for cliente in (c, anonimo):
            ok(cliente.get("/").get_data(as_text=True) == "inicio-core", "/ continua do core")
            ok(cliente.post("/api/chat").get_data(as_text=True) == "chat-core", "/api/chat continua do core")
            ok(cliente.get("/login").get_data(as_text=True) == "login-core", "/login continua do core")
            ok(cliente.get("/segundo-cerebroX").get_data(as_text=True) == "parecido-core", "nome parecido não é nosso")
            r = cliente.get("/")
            ok("Content-Security-Policy" not in r.headers, "rota alheia sem os cabeçalhos do gateway")
        ok(not proc.rodando, "rotas alheias não sobem o Node")

    def t_cabecalhos_limpos(self):
        c, proc, *_ = self._matheus()
        sujos = {"Cookie": "a=b", "Authorization": "Bearer do-cliente", "X-Csrf-Token": "t", "Origin": "https://mal.example",
                 "Referer": "https://mal.example/", "X-Forwarded-For": "1.2.3.4", "Cf-Connecting-Ip": "1.2.3.4",
                 "Next-Router-State-Tree": "x", "Rsc": "1", "X-Middleware-Subrequest": "1", "User-Agent": "navegador"}
        for caminho in ("/api/segundo-cerebro", "/segundo-cerebro"):
            cab = c.get(caminho, headers=sujos).get_json(force=True)["cabecalhos"]
            nomes = set(cab)
            ok(nomes <= {"host", "accept", "accept-encoding", "connection", "user-agent", "authorization"}, f"{caminho}: {nomes}")
            ok(cab["host"].startswith("127.0.0.1:") and cab["accept-encoding"] == "identity", f"{caminho}: host/encoding")
            ok(cab["user-agent"] == "segundo-cerebro-gateway", "User-Agent do cliente não vai")
            if caminho.startswith("/api/"):
                ok(cab["authorization"] == "valido", "na API vai o bearer interno (o do cliente é descartado)")
            else:
                ok("authorization" not in cab, "página não recebe bearer")

    def t_ambiente_minimo(self):
        os.environ["AWS_SECRET_ACCESS_KEY"] = "segredo-falso-de-teste"
        os.environ["A0_SEGREDO_TESTE"] = "x"
        try:
            c, proc, estado, dados = self._matheus()
            amb = c.get("/segundo-cerebro").get_json(force=True)["ambiente"]
        finally:
            os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
            os.environ.pop("A0_SEGREDO_TESTE", None)
        amb = {k: v for k, v in amb.items() if k not in ("LC_CTYPE",)}  # the interpreter of the fake server may add it
        ok(set(amb) == {"PATH", "HOME", "NODE_ENV", "HOSTNAME", "PORT", "NEXT_TELEMETRY_DISABLED",
                        "SECOND_BRAIN_TOKEN_SHA256", "SECOND_BRAIN_DATA_ROOT"}, f"ambiente: {sorted(amb)}")
        ok(amb["HOSTNAME"] == "127.0.0.1" and amb["NODE_ENV"] == "production", "só loopback, produção")
        ok(amb["SECOND_BRAIN_DATA_ROOT"] == str(dados) and amb["PATH"] == self.p.CAMINHO_PATH, "raiz de dados fixa")
        ok(len(amb["SECOND_BRAIN_TOKEN_SHA256"]) == 64 and amb["SECOND_BRAIN_TOKEN_SHA256"] != proc._token, "só o hash vai ao filho")
        ok(hashlib.sha256(proc._token.encode()).hexdigest() == amb["SECOND_BRAIN_TOKEN_SHA256"], "hash do bearer em memória")
        ok(self.p.Processo().raiz_dados == "/a0/usr", "em produção a raiz é /a0/usr")
        ok(self.p.so_loopback(int(amb["PORT"])), "o servidor escuta só em 127.0.0.1")

    def t_token_nao_vai_ao_navegador(self):
        c, proc, estado, dados = self._matheus()
        respostas = [c.get(x) for x in ("/segundo-cerebro", "/api/segundo-cerebro", "/_next/static/chunks/a.js", "/segundo-cerebro/")]
        token = proc._token
        ok(token and len(token) >= 32, "há um bearer interno")
        for r in respostas:
            ok(token not in r.get_data(as_text=True) and token not in str(r.headers), "bearer nunca na resposta")
        for f in estado.rglob("*"):
            if f.is_file():
                ok(token.encode() not in f.read_bytes(), f"bearer não gravado em {f.name}")
        ok(token.encode() not in json.dumps(proc.ambiente(proc._release, 1, "x")).encode(), "nem no ambiente do filho")

    def t_nao_grava_dados(self):
        c, proc, estado, dados = self._matheus()
        antes = {str(f): f.read_bytes() for f in dados.rglob("*") if f.is_file()}
        for x in ("/segundo-cerebro", "/api/segundo-cerebro", "/api/segundo-cerebro?user=fernanda"):
            c.get(x)
        depois = {str(f): f.read_bytes() for f in dados.rglob("*") if f.is_file()}
        ok(antes == depois, "a raiz de dados fica intacta")
        gravados = sorted(f.name for f in estado.iterdir() if f.is_file())
        ok(gravados == ["atual", "node.log", "node.pid"], f"só log e pid na pasta de estado: {gravados}")

    # ---------- process ----------
    def t_falha_processo_503(self):
        for modo, nome in (("morre", "morre"), ("mudo", "mudo")):
            proc, *_ = self._instalacao(modo)
            proc.prazo = 1.5
            c = self._cliente(self._app(proc), dict(self.MATHEUS))
            inicio = time.monotonic()
            r = c.get("/api/segundo-cerebro")
            ok(r.status_code == 503 and r.headers["Cache-Control"] == "private, no-store", f"{nome}: {r.status_code}")
            ok(time.monotonic() - inicio < 6, f"{nome}: falha dentro do prazo")
            inicio = time.monotonic()
            ok(c.get("/segundo-cerebro").status_code == 503 and time.monotonic() - inicio < 1, f"{nome}: espera antes de tentar de novo")
            ok(not proc.rodando, f"{nome}: nada fica rodando")
        proc, estado, _ = self._instalacao()
        (estado / "atual").write_text("desativado")
        c = self._cliente(self._app(proc), dict(self.MATHEUS))
        ok(c.get("/segundo-cerebro").status_code == 503, "sem versão instalada: 503")
        proc, estado, _ = self._instalacao("aberto")
        c = self._cliente(self._app(proc), dict(self.MATHEUS))
        ok(c.get("/api/segundo-cerebro").status_code == 503, "Node que responde sem bearer não fica saudável: 503")
        proc, estado, _ = self._instalacao("recusa")
        c = self._cliente(self._app(proc), dict(self.MATHEUS))
        ok(c.get("/api/segundo-cerebro").status_code == 502, "Node que recusa o bearer interno: 502")

    def t_bearer_recusado_e_resposta_grande_502(self):
        c, proc, *_ = self._matheus()
        ok(c.get("/api/segundo-cerebro").status_code == 200, "primeiro, saudável")
        proc._token = "outro"  # as if the server had another digest
        ok(c.get("/api/segundo-cerebro").status_code == 502, "bearer interno recusado: 502, não 401 ao navegador")
        c, proc, *_ = self._matheus("grande")
        ok(c.get("/segundo-cerebro").status_code == 502, "resposta acima do limite: 502")

    def t_morte_e_troca_de_release(self):
        c, proc, estado, _ = self._matheus()
        ok(c.get("/segundo-cerebro").status_code == 200, "sobe")
        pid = proc._proc.pid
        os.killpg(pid, 9)
        proc._proc.wait(5)
        ok(c.get("/segundo-cerebro").status_code == 200 and proc._proc.pid != pid, "morreu: sobe outro")
        novo = estado / "releases" / ("b" * 40)
        shutil.copytree(estado / "releases" / ("a" * 40), novo)
        (estado / "atual").write_text("b" * 40)
        ok(c.get("/segundo-cerebro").status_code == 200 and proc._release == novo, "troca de versão: reinicia na nova")
        proc.parar()
        ok(not proc.rodando, "parar encerra")

    def t_release_insegura(self):
        proc, estado, _ = self._instalacao()
        rel = estado / "releases" / ("a" * 40)
        ok(proc.release_atual() == rel, "release normal")
        for nome in ("../fora", "a" * 39, "A" * 40, "", "x" * 200):
            (estado / "atual").write_text(nome)
            ok(proc.release_atual() is None, f"nome recusado: {nome[:20]!r}")
        (estado / "atual").unlink()
        (estado / "alvo").write_text("a" * 40)
        (estado / "atual").symlink_to(estado / "alvo")
        ok(proc.release_atual() is None, "ponteiro link simbólico")
        (estado / "atual").unlink()
        (estado / "atual").write_text("c" * 40)
        (estado / "releases" / ("c" * 40)).symlink_to(rel)
        ok(proc.release_atual() is None, "release link simbólico")
        (estado / "atual").write_text("a" * 40)
        (rel / "server.js").rename(rel / "real.js")
        (rel / "server.js").symlink_to(rel / "real.js")
        ok(proc.release_atual() is None, "server.js link simbólico")

    def t_so_loopback(self):
        d = self._pasta()
        linha = "  0: {}:{:04X} 00000000:0000 0A 00000000:00000000 00:00000000 00000000 0 0 1 1 0 0 0 0 0\n"
        cab = "  sl  local_address rem_address   st\n"
        casos = (("0100007F", True), ("00000000", False), ("0101A8C0", False))
        for endereco, esperado in casos:
            (d / "tcp").write_text(cab + linha.format(endereco, 4321))
            (d / "tcp6").write_text(cab)
            ok(self.p.so_loopback(4321, d) is esperado, f"{endereco}: {not esperado}")
        (d / "tcp").write_text(cab + linha.format("0100007F", 4321))
        (d / "tcp6").write_text(cab + linha.format("00000000000000000000000000000000", 4321))
        ok(self.p.so_loopback(4321, d) is False, "também em :: (todas as interfaces IPv6): recusado")
        (d / "tcp6").write_text(cab)
        ok(self.p.so_loopback(9999, d) is False, "ninguém escutando: falso")
        (d / "tcp").unlink()
        ok(self.p.so_loopback(4321, d) is False, "sem /proc/net/tcp: falha fechada")

    # ---------- registration and lifecycle ----------
    def t_wrapper_idempotente(self):
        from flask import Flask

        class Runtime:
            def __init__(self, app):
                self.webapp = app

            @classmethod
            def create(cls):
                return cls(Flask("rt"))

        falso = types.SimpleNamespace(UiServerRuntime=Runtime)
        antigo = sys.modules.get(self.g.NOME_MODULO)
        try:
            ok(self.g.instalar_wrapper(falso) is True, "primeira vez: envolve")
            ok(self.g.instalar_wrapper(falso) is False, "segunda vez: nada muda")
            rt = Runtime.create()
            funcs = rt.webapp.before_request_funcs.get(None, [])
            ok(isinstance(rt, Runtime) and len(funcs) == 1 and funcs[0].__name__ == "segundo_cerebro_gateway", "gateway primeiro")
            ok(Runtime.create().webapp.before_request_funcs[None][0].__name__ == "segundo_cerebro_gateway", "cada app novo")

            class Quebrado:
                create = staticmethod(lambda: None)

            try:
                self.g.instalar_wrapper(types.SimpleNamespace(UiServerRuntime=Quebrado))
                ok(False, "create sem classmethod deve falhar alto")
            except RuntimeError:
                pass
        finally:
            if antigo is None:
                sys.modules.pop(self.g.NOME_MODULO, None)
            else:
                sys.modules[self.g.NOME_MODULO] = antigo

    def t_desligado_nao_serve(self):
        proc, *_ = self._instalacao()
        d = self._pasta()
        shutil.copytree(RAIZ, d / "plugin", ignore=shutil.ignore_patterns("__pycache__"))
        from flask import Flask

        app = Flask("desligado")
        app.secret_key = "chave-de-teste-nao-real"
        self.g.registrar(app, obter_hash=lambda: HASH, processo=proc, plugin_dir=d / "plugin")
        c = self._cliente(app, dict(self.MATHEUS))
        ok(c.get("/segundo-cerebro").status_code == 200, "ligado: serve")
        (d / "plugin" / ".toggle-0").write_text("")
        ok(c.get("/segundo-cerebro").status_code == 404, "desligado (.toggle-0): rota não existe mais")
        (d / "plugin" / ".toggle-0").unlink()
        shutil.move(d / "plugin", d / "plugin-revertido")
        ok(c.get("/segundo-cerebro").status_code == 404, "plugin tirado do lugar (rollback): rota não existe mais")

    def t_hooks_e_estrutura(self):
        ok(not (RAIZ / "execute.py").exists(), "sem execute.py")
        ok(self.g.validar_plugin(RAIZ) == [], f"plugin válido: {self.g.validar_plugin(RAIZ)}")
        h = _carregar("segundo_cerebro_hooks_teste", RAIZ / "hooks.py")
        ok(all(callable(getattr(h, n, None)) for n in ("install", "pre_update", "uninstall")), "hooks do ciclo de vida")
        est = self.g.estado()

        class Parado:
            parado = False

            def parar(self):
                Parado.parado = True

        antigo, est.processo = est.processo, Parado()
        try:
            ok(h.pre_update() is True and Parado.parado, "pre_update para o Node")
            Parado.parado = False
            ok(h.uninstall() is True and Parado.parado and est.desativado, "uninstall para e desliga")
        finally:
            est.processo, est.desativado = antigo, False
        ext = (RAIZ / "extensions/python/startup_migration/_15_segundo_cerebro_gateway.py").read_text()
        ok("instalar_wrapper" in ext and "validar_plugin" in ext, "a extensão de início registra pelo wrapper")
        fontes = "".join(p.read_text() for p in RAIZ.rglob("*.py") if p.parent.name != "tests")
        ok("os.environ.copy" not in fontes and "env=os.environ" not in fontes, "o filho nunca herda o ambiente")
        ok("0.0.0.0" not in (RAIZ / "helpers" / "processo.py").read_text(), "nenhum bind público")

    async def rodar(self, so=""):
        try:
            for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
                try:
                    getattr(self, nome)()
                    self.resultados.append({"teste": nome, "ok": True})
                except Exception as exc:
                    self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                            "onde": traceback.format_exc().splitlines()[-3:]})
                finally:
                    for p in self._procs:
                        p.parar()
                    self._procs.clear()
        finally:
            for d in self._tmp:
                shutil.rmtree(d, ignore_errors=True)
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])

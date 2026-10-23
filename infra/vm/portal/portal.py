"""O portal do agente (migração ao Hermes, fase 6): as páginas que hoje vivem dentro da interface do Agent Zero —
Segundo Cérebro, Painel, Tarefas e Cofre — num servidor próprio, com o login de sempre (usuarios.json: os mesmos
logins e senhas, só hash PBKDF2), para continuarem quando o A0 parar (o Hermes não tem portão de páginas).

Reaproveita o que já existe, sem reescrever:
- as páginas são os mesmos main.html dos plugins (painel, quadro, cofre), servidos numa casca com Alpine e um
  sendJsonData que fala com este servidor;
- as APIs fazem o que os ApiHandler do A0 fazem, pelos mesmos helpers (painel/vivos, quadro/fios, cofre);
  "Faz pra mim" das Tarefas abre um pedido no Hermes (/v1/runs, sessão própria da tarefa) em vez de uma conversa do A0;
- o Segundo Cérebro passa pelo mesmo portão (segundo_cerebro/helpers/gateway.py: decidir + encaminhar, só o dono) e
  pelo mesmo lançador do Next (processo.py), com o estado do Node numa pasta do portal (nunca o pid do A0).

Segurança: sessão em cookie assinado (HMAC, segredo só na VM), HttpOnly/SameSite=Lax; POST só com o cabeçalho
X-Portal (um site de fora não manda sem pré-voo); 5 senhas erradas do mesmo IP bloqueiam 15 min (o Bloqueio do A0).
PORTAL_SO_LEITURA=1 (até a virada): nada grava (cofre, tarefas); só mostra.
Executa: python3 portal.py  (PORTAL_PORTA, padrão 8650, só 127.0.0.1)."""
import asyncio
import base64
import hashlib
import hmac
import importlib.util
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from aiohttp import web

PLUGINS = Path(os.environ.get("PORTAL_PLUGINS", "/a0/usr/plugins"))
AQUI = Path(__file__).resolve().parent
SEGREDO = Path(os.environ.get("PORTAL_SEGREDO", "/portal/segredo"))
ESTADO_NEXT = Path(os.environ.get("PORTAL_ESTADO_NEXT", "/portal/segundo_cerebro"))
HERMES_URL = os.environ.get("HERMES_URL", "http://127.0.0.1:8642")
HERMES_CHAVE = Path(os.environ.get("HERMES_CHAVE", "/portal/hermes_api_key"))
SO_LEITURA = os.environ.get("PORTAL_SO_LEITURA") == "1"
VIDA = 400 * 86400  # como a sessão do A0
COOKIE = "portal_sessao"
PAGINAS = {"painel": ("painel", "Painel"), "tarefas": ("quadro", "Tarefas"), "cofre": ("cofre", "Cofre")}
ERRO_LEITURA = "Até a virada esta página só mostra: mude pelo agente de hoje."


def _modulo(nome: str, caminho: Path):
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        sys.modules[nome] = m
        spec.loader.exec_module(m)
        m._mtime = mtime
    return sys.modules[nome]


def usuarios():
    return _modulo("portal_usuarios", PLUGINS / "login_usuarios" / "helpers" / "usuarios.py")


def helper(plugin: str, arquivo: str):
    return _modulo(f"portal_{plugin}_{arquivo}", PLUGINS / plugin / "helpers" / f"{arquivo}.py")


# ------------------------------------------------------------------ sessão
def _segredo() -> bytes:
    try:
        return SEGREDO.read_bytes().strip()
    except OSError:
        return b""


def assinar(login: str, agora: float | None = None) -> str:
    corpo = base64.urlsafe_b64encode(json.dumps({"l": login, "t": int(agora or time.time())}).encode()).decode()
    sig = hmac.new(_segredo(), corpo.encode(), hashlib.sha256).hexdigest()
    return f"{corpo}.{sig}"


def login_do_cookie(valor: str, agora: float | None = None) -> str:
    """O login da sessão, ou "" (assinatura errada, vencida, sem segredo, ou o login saiu do usuarios.json)."""
    segredo = _segredo()
    if not segredo or not valor or "." not in valor:
        return ""
    corpo, sig = valor.rsplit(".", 1)
    if not hmac.compare_digest(hmac.new(segredo, corpo.encode(), hashlib.sha256).hexdigest(), sig):
        return ""
    try:
        d = json.loads(base64.urlsafe_b64decode(corpo.encode()))
    except ValueError:
        return ""
    login = str(d.get("l") or "")
    if (agora or time.time()) - int(d.get("t") or 0) > VIDA or login not in usuarios().carregar():
        return ""
    return login


@web.middleware
async def guarda(request: web.Request, handler):
    request["login"] = login_do_cookie(request.cookies.get(COOKIE, ""))
    if request.path in ("/entrar", "/saude"):
        return await handler(request)
    if request.method == "POST" and request.headers.get("X-Portal") != "1":
        return web.json_response({"erro": "pedido sem o cabeçalho do portal"}, status=403)
    if not request["login"]:
        if request.method == "GET" and not request.path.startswith(("/api/", "/plugins/", "/_next/")):
            raise web.HTTPFound(f"/entrar?volta={request.path}")
        return web.json_response({"erro": "entre de novo"}, status=401)
    resposta = await handler(request)
    resposta.headers.setdefault("Cache-Control", "private, no-store")
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resposta.headers.setdefault("Referrer-Policy", "same-origin")
    return resposta


ENTRAR = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Entrar</title><style>body{{font-family:system-ui;max-width:360px;margin:12vh auto;padding:0 16px}}input,button{{width:100%;
padding:10px;margin:6px 0;font-size:16px}}.e{{color:#b00}}</style></head><body><h2>Agente do Matheus</h2>
<form method="post" action="/entrar"><input type="hidden" name="volta" value="{volta}"><input name="login" placeholder="login"
autocomplete="username" required><input name="senha" type="password" placeholder="senha" autocomplete="current-password" required>
<button>Entrar</button></form><p class="e">{erro}</p></body></html>"""

INICIO = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agente</title><style>body{{font-family:system-ui;max-width:520px;margin:6vh auto;padding:0 16px}}a{{display:block;padding:14px;
margin:8px 0;border:1px solid #ccc;border-radius:10px;text-decoration:none;color:inherit}}</style></head><body>
<h2>Olá, {nome}</h2>{links}<p><a href="/sair">Sair</a></p></body></html>"""

CASCA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titulo}</title><style>body{{font-family:system-ui;margin:0;padding:12px 16px}}nav a{{margin-right:14px}}</style>
<script>globalThis.sendJsonData = async (url, dados) => {{
  const r = await fetch(url, {{method: "POST", headers: {{"Content-Type": "application/json", "X-Portal": "1"}},
                              body: JSON.stringify(dados || {{}}), credentials: "same-origin"}});
  if (r.status === 401) {{ location.href = "/entrar?volta=" + location.pathname; return {{}}; }}
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json(); }};</script>
<script defer src="https://cdnjs.cloudflare.com/ajax/libs/alpinejs/3.14.1/cdn.min.js"></script></head>
<body><nav><a href="/">Início</a>{nav}</nav>{corpo}</body></html>"""


async def entrar(request: web.Request) -> web.Response:
    volta = request.query.get("volta", "/")
    if request.method == "GET":
        return web.Response(text=ENTRAR.format(volta=_seguro(volta), erro=""), content_type="text/html")
    dados = await request.post()
    volta = _seguro(str(dados.get("volta") or "/"))
    ip = request.headers.get("CF-Connecting-IP") or request.remote or "?"
    bloq = request.app["bloqueio"]
    if bloq.bloqueado(ip):
        return web.Response(text=ENTRAR.format(volta=volta, erro="Muitas tentativas. Espere 15 minutos."),
                            content_type="text/html", status=429)
    login = str(dados.get("login") or "").strip().lower()
    u = await asyncio.to_thread(usuarios().verificar, login, str(dados.get("senha") or ""))
    if not u:
        bloq.falhou(ip)
        await asyncio.sleep(min(bloq.espera(), 5) if hasattr(bloq, "espera") else 1)
        return web.Response(text=ENTRAR.format(volta=volta, erro="Login ou senha errados."), content_type="text/html",
                            status=401)
    resposta = web.HTTPFound(volta)
    resposta.set_cookie(COOKIE, assinar(login), max_age=VIDA, httponly=True, samesite="Lax",
                        secure=request.headers.get("X-Forwarded-Proto") == "https" or request.secure)
    raise resposta


def _seguro(volta: str) -> str:
    return volta if volta.startswith("/") and not volta.startswith("//") and "\\" not in volta else "/"


async def sair(request: web.Request) -> web.Response:
    r = web.HTTPFound("/entrar")
    r.del_cookie(COOKIE)
    raise r


async def inicio(request: web.Request) -> web.Response:
    login = request["login"]
    links = "".join(f'<a href="/{rota}">{titulo}</a>' for rota, (_, titulo) in PAGINAS.items())
    if login == "matheus":
        links = '<a href="/segundo-cerebro">Segundo Cérebro</a>' + links
    nome = (usuarios().carregar().get(login) or {}).get("nome") or login.title()
    return web.Response(text=INICIO.format(nome=nome, links=links), content_type="text/html")


async def pagina(request: web.Request) -> web.Response:
    rota = request.match_info["rota"]
    plugin, titulo = PAGINAS[rota]
    corpo = (PLUGINS / plugin / "webui" / "main.html").read_text(encoding="utf-8")
    corpo = corpo.split("<body>", 1)[-1].rsplit("</body>", 1)[0]
    nav = "".join(f'<a href="/{r}">{t}</a>' for r, (_, t) in PAGINAS.items())
    return web.Response(text=CASCA.format(titulo=titulo, nav=nav, corpo=corpo), content_type="text/html")


# ------------------------------------------------------------------ as APIs (as mesmas dos ApiHandler do A0)
async def api_painel(request: web.Request) -> web.Response:
    login = request["login"]
    try:
        lista = helper("painel", "vivos").listar(login)
    except Exception:
        lista = []
    p = helper("painel", "painel")
    for d in lista:
        d["lido_as"] = p.hora(d.get("atualizado"))
        d.pop("receita", None)
    return web.json_response({"painel": p.ler(login), "vivos": lista})


def _hermes_tarefa(login: str, fio: dict, texto: str) -> str:
    sessao = f"tarefa-{login}-{fio['id']}"[:64]
    req = urllib.request.Request(HERMES_URL + "/v1/runs", data=json.dumps({"input": texto, "session_id": sessao}).encode(),
                                 headers={"Authorization": f"Bearer {HERMES_CHAVE.read_text().strip()}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        json.loads(r.read() or b"{}")
    return sessao


async def api_quadro(request: web.Request) -> web.Response:
    q, login = helper("quadro", "quadro"), request["login"]
    entrada = await request.json()
    acao, fid = str(entrada.get("acao") or "ler"), str(entrada.get("id") or "")
    msg = ""
    if acao in ("concluir", "reabrir", "fazer") and fid:
        if SO_LEITURA:
            return web.json_response({"ok": False, "erro": ERRO_LEITURA, "quadro": q.montar(login)})
        f = q.fios()
        fio = f.obter(login, fid)
        if not fio:
            return web.json_response({"ok": False, "erro": "essa tarefa não existe mais", "quadro": q.montar(login)})
        if acao == "fazer" and fio.get("estado") not in ("aberto", "adiado"):
            return web.json_response({"ok": False, "erro": "essa tarefa já não está em aberto", "quadro": q.montar(login)})
        if acao == "concluir":
            f.concluir(login, fid, f"{login}: concluiu no quadro de Tarefas")
            msg = "Concluída."
        elif acao == "reabrir":
            f.reabrir(login, fid)
            msg = "Reaberta."
        else:
            sessao = await asyncio.to_thread(_hermes_tarefa, login, fio, q.texto_fazer(fio))
            f.mesclar(login, [{"id": fid, "conversa": sessao}])
            msg = "Comecei um pedido só desta tarefa; aviso no celular quando terminar."
    return web.json_response({"ok": True, "mensagem": msg, "quadro": q.montar(login)})


async def api_cofre(request: web.Request) -> web.Response:
    c, login = helper("cofre", "cofre"), request["login"]
    entrada = await request.json()
    acao = str(entrada.get("acao") or "listar")
    if acao in ("salvar", "descrever", "apagar") and SO_LEITURA:
        return web.json_response({"ok": False, "erro": ERRO_LEITURA, "nomes": sorted(c.carregar(login))})
    try:
        if acao == "salvar":
            nome = str(entrada.get("nome") or "").strip().upper()
            c.salvar(login, nome, str(entrada.get("valor") or ""))
            if str(entrada.get("para") or "").strip():
                c.descrever(login, nome, str(entrada["para"]))
        elif acao == "descrever":
            c.descrever(login, str(entrada.get("nome") or "").strip().upper(), str(entrada.get("para") or ""))
        elif acao == "apagar":
            c.apagar(login, str(entrada.get("nome") or "").strip().upper())
    except ValueError as exc:
        return web.json_response({"ok": False, "erro": str(exc), "nomes": sorted(c.carregar(login))})
    return web.json_response({"ok": True, "nomes": sorted(c.carregar(login)), "descricoes": c.descricoes(login)})


# ------------------------------------------------------------------ Segundo Cérebro (o mesmo portão do A0)
HASH_SESSAO = "portal"  # a sessão do portal já foi conferida pela guarda; o portão confere o dono


def gateway():
    return _modulo("portal_sc_gateway", PLUGINS / "segundo_cerebro" / "helpers" / "gateway.py")


_NEXT: dict = {}


def processo_next():
    """O Node do Segundo Cérebro deste portal, com o estado (pid, log, release) numa pasta do portal: o do A0 continua
    dele (o lançador mata o pid órfão que acha na pasta de estado)."""
    if "p" not in _NEXT:
        proc = _modulo("portal_sc_processo", PLUGINS / "segundo_cerebro" / "helpers" / "processo.py")
        _NEXT["p"] = proc.Processo(raiz_estado=ESTADO_NEXT)
    return _NEXT["p"]


async def segundo_cerebro(request: web.Request) -> web.Response:
    g = gateway()
    login = request["login"]
    cab = {k.lower(): v for k, v in request.headers.items() if k.lower() not in ("cookie", "authorization", "x-portal")}
    sessao = {"authentication": HASH_SESSAO, "usuario": login, "user_id": login}
    d = g.decidir(request.method, request.path, cab, list(request.query.items()), sessao, HASH_SESSAO,
                  request.content_length or 0)
    if d.status != 200:
        status, cabecalhos, corpo = g.resposta_erro(d)
    else:
        status, cabecalhos, corpo = await asyncio.to_thread(g.encaminhar, d.tipo, request.method, request.path, cab,
                                                            processo_next())
    return web.Response(status=status, body=corpo, headers={k: v for k, v in cabecalhos.items()
                                                             if k.lower() not in ("content-length", "transfer-encoding")})


async def saude(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


def app() -> web.Application:
    a = web.Application(middlewares=[guarda], client_max_size=2 * 1024 * 1024)
    a["bloqueio"] = usuarios().Bloqueio()
    a.router.add_route("*", "/entrar", entrar)
    a.router.add_get("/sair", sair)
    a.router.add_get("/saude", saude)
    a.router.add_get("/", inicio)
    a.router.add_get("/{rota:painel|tarefas|cofre}", pagina)
    a.router.add_post("/plugins/painel/painel", api_painel)
    a.router.add_post("/plugins/quadro/quadro", api_quadro)
    a.router.add_post("/plugins/cofre/cofre", api_cofre)
    for caminho in ("/segundo-cerebro", "/segundo-cerebro/", "/api/segundo-cerebro", "/icon.svg", "/manifest.webmanifest",
                    "/_next/{resto:.*}", "/segundo-cerebro/{resto:.*}", "/api/segundo-cerebro/{resto:.*}"):
        a.router.add_route("*", caminho, segundo_cerebro)
    return a


if __name__ == "__main__":
    web.run_app(app(), host="127.0.0.1", port=int(os.environ.get("PORTAL_PORTA", "8650")), access_log=None)

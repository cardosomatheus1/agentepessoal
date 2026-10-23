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
PORTAL_SO_LEITURA=1 (até a virada): nada grava (cofre, tarefas); só mostra. Na virada, a página Navegador (o navegador do
Hermes, para resolver um login/captcha ou mostrar uma tarefa ao me_mostre; só o dono).
Executa: python3 portal.py  (PORTAL_PORTA, padrão 8650, só 127.0.0.1)."""
import asyncio
import base64
import hashlib
import hmac
import html
import importlib.util
import json
import os
import sys
import time
import urllib.parse
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
    sem_login_com_link = (request.path == "/navegador" and request.query.get("t")) or (
        request.path == "/api/navegador" and request.method == "POST" and request.headers.get("X-Portal") == "1")
    if sem_login_com_link and not request["login"]:
        # o link assinado do "Resolver aqui" (Telegram, sem login): a própria rota confere o token
        resposta = await handler(request)
        resposta.headers.setdefault("Cache-Control", "private, no-store")
        resposta.headers.setdefault("Referrer-Policy", "no-referrer")
        return resposta
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
        return web.Response(text=ENTRAR.format(volta=html.escape(_seguro(volta), quote=True), erro=""),
                            content_type="text/html")
    dados = await request.post()
    volta = _seguro(str(dados.get("volta") or "/"))
    volta_html = html.escape(volta, quote=True)  # nunca cru no HTML (revisão OpenCode 23/10: XSS refletido)
    ip = request.headers.get("CF-Connecting-IP") or request.remote or "?"
    bloq = request.app["bloqueio"]
    if bloq.bloqueado(ip):
        return web.Response(text=ENTRAR.format(volta=volta_html, erro="Muitas tentativas. Espere 15 minutos."),
                            content_type="text/html", status=429)
    login = str(dados.get("login") or "").strip().lower()
    u = await asyncio.to_thread(usuarios().verificar, login, str(dados.get("senha") or ""))
    if not u:
        bloq.falhou(ip)
        await asyncio.sleep(min(bloq.espera(), 5) if hasattr(bloq, "espera") else 1)
        return web.Response(text=ENTRAR.format(volta=volta_html, erro="Login ou senha errados."), content_type="text/html",
                            status=401)
    resposta = web.HTTPFound(volta)
    resposta.set_cookie(COOKIE, assinar(login), max_age=VIDA, httponly=True, samesite="Lax",
                        secure=request.headers.get("X-Forwarded-Proto") == "https" or request.secure)
    raise resposta


def _seguro(volta: str) -> str:
    """Só um caminho deste portal (nem outro site, nem texto que vire HTML ou script)."""
    import re

    return volta if re.fullmatch(r"/[A-Za-z0-9/_-]{0,80}", volta or "") and not volta.startswith("//") else "/"


async def sair(request: web.Request) -> web.Response:
    r = web.HTTPFound("/entrar")
    r.del_cookie(COOKIE)
    raise r


async def inicio(request: web.Request) -> web.Response:
    login = request["login"]
    links = "".join(f'<a href="/{rota}">{titulo}</a>' for rota, (_, titulo) in PAGINAS.items())
    if login == "matheus":
        links = '<a href="/segundo-cerebro">Segundo Cérebro</a>' + links
        if CDP:
            links += '<a href="/navegador">Navegador do agente</a>'
    
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


# ------------------------------------------------------------------ Navegador (virada, fase 8)
# O "Navegador" e o "🖥️ Resolver aqui" do A0 (navegador_visual: tela.html/tela.py) no Hermes: a tela do navegador dele
# (hermes-navegador, por CDP: PORTAL_CDP), onde um toque é um clique, segurar é "segure o botão" (Cloudflare, até 15 s),
# segurar e arrastar arrasta, arrastar rola; abas (lista, nova, trocar), endereço, digitar e teclas. Entra quem tem
# sessão do portal como dono, ou o link assinado que o agente manda no Telegram (ferramenta `resolver_aqui`: a mesma
# assinatura do A0, com o segredo da ponte, 30 min, só o dono); "✅ Terminei" avisa a conversa que pediu.
CDP = os.environ.get("PORTAL_CDP", "")
DONO_NAVEGADOR = "matheus"
CHAVE_PONTE = Path(os.environ.get("PORTAL_CHAVE_PONTE", "/a0/usr/whatsapp/.chave"))
PONTE_URL = os.environ.get("PORTAL_PONTE", "http://127.0.0.1:8789")  # a ponte do celular (o portal roda na rede do host)
PAGINA_NAVEGADOR = AQUI / "navegador.html"
TECLAS_NAV = {"Enter": (13, "\r"), "Backspace": (8, ""), "Tab": (9, "\t"), "Escape": (27, "")}
PRONTO = ("(Ele resolveu o que você pediu na tela do navegador, pelo botão \"Resolver aqui\" do Telegram. Leia a página de "
          "novo (browser_snapshot), confira se ficou certo e siga com a tarefa; se não ficou, diga o que falta.)")
TAMANHO = "(() => [innerWidth, innerHeight])()"
PRONTOS: set = set()  # os links cujo "✅ Terminei" já foi avisado


def tela_helper():
    return _modulo("portal_navegador_tela", PLUGINS / "navegador_visual" / "helpers" / "tela.py")


def pode_navegador(login: str) -> bool:
    """O navegador do agente é do dono; os logins de teste do operador (teste_*, sem celular) servem para conferir."""
    return login == DONO_NAVEGADOR or login.startswith("teste_")


def token_do_navegador(token: str) -> dict | None:
    """O link do "Resolver aqui": assinado com o segredo da ponte, ainda válido e do dono (nunca de um convidado)."""
    if not token:
        return None
    t = tela_helper()
    dados = t.conferir(token, t.segredo(CHAVE_PONTE))
    return dados if dados and pode_navegador(str(dados.get("usuario") or "")) else None


async def _cdp_abas() -> list:
    import aiohttp

    async with aiohttp.ClientSession() as s:
        async with s.get(f"{CDP}/json/list", timeout=aiohttp.ClientTimeout(total=10)) as r:
            return [a for a in await r.json(content_type=None) if a.get("type") == "page"]


async def _cdp_http(caminho: str, metodo: str = "GET") -> dict:
    import aiohttp

    async with aiohttp.ClientSession() as s:
        async with s.request(metodo, f"{CDP}{caminho}", timeout=aiohttp.ClientTimeout(total=10)) as r:
            try:
                return await r.json(content_type=None)
            except Exception:
                return {}


async def _cdp(aba: str, metodo: str, params: dict | None = None) -> dict:
    import aiohttp

    abas = await _cdp_abas()
    alvo = next((a for a in abas if a["id"] == aba), None) if aba else None
    if alvo is None:
        if not abas:
            raise web.HTTPNotFound(text="nenhuma aba aberta")
        alvo = abas[0]
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect(alvo["webSocketDebuggerUrl"], max_msg_size=50_000_000, timeout=10) as ws:
            await ws.send_json({"id": 1, "method": metodo, "params": params or {}})
            async for msg in ws:
                d = json.loads(msg.data)
                if d.get("id") == 1:
                    if d.get("error"):
                        raise web.HTTPBadGateway(text=str(d["error"])[:200])
                    return d.get("result") or {}
    return {}


def _autorizado(request: web.Request, token: str = "") -> dict | None:
    """{"login", "sessao"} de quem pode mexer no navegador do agente, ou HTTPForbidden."""
    if not CDP:
        raise web.HTTPForbidden(text="o navegador do agente só existe depois da virada")
    dados = token_do_navegador(token or request.query.get("t", ""))
    if dados:
        return {"login": dados["usuario"], "sessao": dados["contexto"], "token": token or request.query.get("t", "")}
    if request.get("login") == DONO_NAVEGADOR:
        return {"login": DONO_NAVEGADOR, "sessao": "", "token": ""}
    raise web.HTTPForbidden(text="o navegador do agente é só do Matheus")


async def navegador(request: web.Request) -> web.Response:
    token = request.query.get("t", "")
    if token and token_do_navegador(token) is None:
        return web.Response(text="<h3 style='font-family:sans-serif;padding:24px'>Este link expirou. Peça de novo ao "
                                 "agente.</h3>", status=403, content_type="text/html")
    _autorizado(request, token)
    pagina = PAGINA_NAVEGADOR.read_text(encoding="utf-8").replace("__TOKEN__", html.escape(token, quote=True))
    return web.Response(text=pagina, content_type="text/html")


def texto_pronto(login: str, sessao: str) -> str:
    """O aviso de "✅ Terminei": vai na conversa do celular da pessoa (tg-<login>); se o pedido nasceu em outra sessão
    (uma rotina), o agente sabe qual é para achar o contexto."""
    return PRONTO if sessao == f"tg-{login}" else PRONTO + f" (O pedido do botão veio da sessão {sessao}: veja o que era.)"


def _ponte_pronto(login: str, sessao: str) -> None:
    """Pela ponte do celular (POST /conversa, como os botões): ela abre o pedido na conversa da pessoa no Hermes, segue
    até o fim e manda a resposta ao celular (um /v1/runs direto daqui terminaria sem ninguém para entregar)."""
    req = urllib.request.Request(PONTE_URL + "/conversa",
                                 data=json.dumps({"usuario": login, "texto": texto_pronto(login, sessao)}).encode(),
                                 headers={"Content-Type": "application/json", "X-Chave": CHAVE_PONTE.read_text().strip()})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


PONTEIRO: dict = {}  # aba -> onde o ponteiro do mouse está (o próximo toque parte dali, como um mouse de verdade)


async def navegador_api(request: web.Request) -> web.Response:
    d = await request.json()
    quem = _autorizado(request, str(d.get("t") or ""))
    acao, aba = str(d.get("acao") or ""), str(d.get("aba") or "")
    if acao == "pronto":
        if not quem["sessao"]:
            return web.json_response({"erro": "sem conversa esperando (abra pelo botão do Telegram)"}, status=400)
        if quem["token"] in PRONTOS:  # um aviso por link: apertar de novo não abre outro pedido
            return web.json_response({"ok": True, "repetido": True})
        PRONTOS.add(quem["token"])
        await asyncio.to_thread(_ponte_pronto, quem["login"], quem["sessao"])
        return web.json_response({"ok": True})
    if acao == "abas":
        return web.json_response({"abas": [{"id": a["id"], "url": a.get("url", ""), "titulo": a.get("title", "")}
                                           for a in await _cdp_abas()]})
    if acao == "abrir" and d.get("nova"):
        url = str(d.get("url") or "about:blank")
        if not url.startswith(("https://", "about:blank")):
            return web.json_response({"erro": "só endereço https"}, status=400)
        nova = await _cdp_http(f"/json/new?{urllib.parse.quote(url, safe=':/?&=%')}", "PUT")
        return web.json_response({"ok": True, "aba": nova.get("id", "")})
    if acao == "ativar":
        await _cdp_http(f"/json/activate/{urllib.parse.quote(aba)}")
        return web.json_response({"ok": True})
    if acao == "quadro":
        r = await _cdp(aba, "Page.captureScreenshot", {"format": "jpeg", "quality": int(d.get("qualidade") or 60)})
        return web.json_response({"imagem": r.get("data", "")})
    if acao == "abrir":
        url = str(d.get("url") or "").strip()
        if not url.startswith("https://"):
            url = "https://" + url.split("://", 1)[-1]
        await _cdp(aba, "Page.navigate", {"url": url})
        return web.json_response({"ok": True})
    if acao == "voltar":
        await _cdp(aba, "Runtime.evaluate", {"expression": "history.back()"})
        return web.json_response({"ok": True})
    if acao == "recarregar":
        await _cdp(aba, "Page.reload", {})
        return web.json_response({"ok": True})
    if acao == "texto":
        await _cdp(aba, "Input.insertText", {"text": str(d.get("texto") or "")[:2000]})
        return web.json_response({"ok": True})
    if acao == "tecla":
        tecla = str(d.get("tecla") or "")
        if tecla not in TECLAS_NAV:
            return web.json_response({"erro": "tecla desconhecida"}, status=400)
        codigo, texto = TECLAS_NAV[tecla]
        base = {"key": tecla, "code": tecla, "windowsVirtualKeyCode": codigo}
        await _cdp(aba, "Input.dispatchKeyEvent", {**base, "type": "keyDown" if texto else "rawKeyDown",
                                                   **({"text": texto} if texto else {})})
        await _cdp(aba, "Input.dispatchKeyEvent", {**base, "type": "keyUp"})
        return web.json_response({"ok": True})
    if acao not in ("toque", "segurar", "arrastar", "rolar"):
        return web.json_response({"erro": "ação desconhecida"}, status=400)
    medida = await _cdp(aba, "Runtime.evaluate", {"expression": TAMANHO, "returnByValue": True})
    largura, altura = ((medida.get("result") or {}).get("value") or [0, 0])[:2]
    if not largura or not altura:
        return web.json_response({"erro": "não consegui medir a página"}, status=502)

    def ponto(fx, fy):
        return (max(0.0, min(1.0, float(fx or 0))) * largura, max(0.0, min(1.0, float(fy or 0))) * altura)

    async def mouse(tipo: str, x: float, y: float, botoes: int = 0):
        # force 0.5 com o botão apertado = a pressão de um mouse de verdade (pointerdown.pressure 0.5, como o xpra do A0
        # entregava); sem ele o CDP manda pressão 0, e o Cloudflare (Turnstile) recusa o toque ("Verification failed").
        await _cdp(aba, "Input.dispatchMouseEvent", {"type": tipo, "x": x, "y": y, "button": "left" if tipo != "mouseMoved" else
                                                     ("left" if botoes else "none"), "buttons": botoes, "clickCount": 1,
                                                     **({"force": 0.5} if botoes else {})})
        PONTEIRO[aba] = (x, y)

    async def chegar(x: float, y: float):
        """O ponteiro chega ao ponto vindo de onde estava (ou de perto), como um mouse de verdade: o quadro recebe
        movimento (movementX/Y) antes do clique, e não um clique "do nada"."""
        ox, oy = PONTEIRO.get(aba) or (max(0.0, x - 24), max(0.0, y + 18))
        if (ox, oy) != (x, y):
            await mouse("mouseMoved", (ox + x) / 2, (oy + y) / 2)
            await asyncio.sleep(0.03)
        await mouse("mouseMoved", x, y)
        await asyncio.sleep(0.05)

    if acao == "toque":
        # Como o toque chegava no A0 (xpra, um mouse de verdade no X): o ponteiro chega ao ponto, aperta (pressão 0,5)
        # e solta com o tempo de um dedo (Matheus, 23/10: "com Hermes não passa nenhum" Cloudflare).
        x, y = ponto(d.get("fx"), d.get("fy"))
        await chegar(x, y)
        await mouse("mousePressed", x, y, 1)
        await asyncio.sleep(0.08)
        await mouse("mouseReleased", x, y)
    elif acao == "segurar":  # "segure o botão" (Cloudflare): o mesmo tempo que a pessoa segurou, até 15 s
        x, y = ponto(d.get("fx"), d.get("fy"))
        await chegar(x, y)
        await mouse("mousePressed", x, y, 1)
        await asyncio.sleep(max(0.5, min(15.0, float(d.get("ms") or 0) / 1000)))
        await mouse("mouseReleased", x, y)
    elif acao == "arrastar":
        pontos = [ponto(*p[:2]) for p in (d.get("pontos") or [])][:200]
        if len(pontos) < 2:
            return web.json_response({"erro": "arraste curto"}, status=400)
        await chegar(*pontos[0])
        await mouse("mousePressed", *pontos[0], 1)
        for x, y in pontos[1:]:
            await mouse("mouseMoved", x, y, 1)
        await mouse("mouseReleased", *pontos[-1])
    else:
        await _cdp(aba, "Input.dispatchMouseEvent", {"type": "mouseWheel", "x": largura / 2, "y": altura / 2, "deltaX": 0,
                                                     "deltaY": float(d.get("dy") or 0) * altura})
    return web.json_response({"ok": True})


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
    a.router.add_get("/navegador", navegador)
    a.router.add_post("/api/navegador", navegador_api)
    for caminho in ("/segundo-cerebro", "/segundo-cerebro/", "/api/segundo-cerebro", "/icon.svg", "/manifest.webmanifest",
                    "/_next/{resto:.*}", "/segundo-cerebro/{resto:.*}", "/api/segundo-cerebro/{resto:.*}"):
        a.router.add_route("*", caminho, segundo_cerebro)
    return a


if __name__ == "__main__":
    web.run_app(app(), host="127.0.0.1", port=int(os.environ.get("PORTAL_PORTA", "8650")), access_log=None)

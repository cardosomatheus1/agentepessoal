"""Segundo Cérebro gateway: a Flask before_request on the Agent Zero web app that serves only

    /segundo-cerebro, /segundo-cerebro/        page            GET, HEAD
    /api/segundo-cerebro                       data            GET
    /_next/static/<safe asset path>            page assets     GET, HEAD
    /icon.svg and /manifest.webmanifest        public assets   GET, HEAD

from the loopback Next server (processo.py), and only to the existing Agent Zero session of Matheus:
session["authentication"] == helpers.login.get_credentials_hash() (non-empty), session["usuario"] == "matheus" and
session["user_id"] == "matheus" (set by login_usuarios). Nothing the caller sends selects an identity: identity
headers or query keys make the request fail (403); cookies, Authorization and every other client header are dropped.
The internal bearer is added only to the API request to Next and never reaches the browser.

Any other path under these prefixes is 404 without touching Next; every other route of Agent Zero is untouched.
Once registered (startup_migration), the hook reloads this file when it changes, so a deploy needs no restart.
"""

import hmac
import http.client
import importlib.util
import json
import re
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

DONO = "matheus"
PLUGIN_DIR = Path(__file__).resolve().parents[1]
PAGINAS = frozenset({"/segundo-cerebro", "/segundo-cerebro/"})
API = "/api/segundo-cerebro"
PUBLICOS = frozenset({"/icon.svg", "/manifest.webmanifest"})
PREFIXOS = ("/segundo-cerebro/", "/api/segundo-cerebro/", "/_next/")
# directories without dots; a file name with a known asset extension; nothing like "..", "%", "\" or "//" fits
ESTATICO = re.compile(r"^/_next/static/(?:[A-Za-z0-9_~-]+/){0,6}[A-Za-z0-9_~-]+(?:\.[A-Za-z0-9_~-]+){0,4}"
                      r"\.(?:js|css|woff2|woff|ttf|otf|png|svg|ico|webp|avif|jpg|jpeg|gif|txt)$")
METODOS = {"pagina": ("GET", "HEAD"), "estatico": ("GET", "HEAD"), "publico": ("GET", "HEAD"), "api": ("GET",)}
CABECALHO_IDENTIDADE = re.compile(
    r"^(?:x-(?:a0-|forwarded-|remote-|auth-request-|original-|authenticated-)?"
    r"(?:user|usuario|login|tenant|owner|dono|impersonat|identity|account|email|as-user)[a-z0-9_-]*|remote-user)$")
CONSULTA_IDENTIDADE = re.compile(
    r"^(?:user|users|usuario|user_id|userid|uid|login|tenant|owner|dono|as|impersonate|identity|quem|account|email"
    r"|session|sessao|token|authorization)$", re.I)
LIMITE_RESPOSTA = 8 * 1024 * 1024
TEMPO_UPSTREAM = 15
SEGURANCA = {
    "Cache-Control": "private, no-store",
    "Vary": "Cookie",
    "Content-Security-Policy": "frame-ancestors 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "same-origin",
}
LOGIN = "/login?next=/segundo-cerebro"


@dataclass
class Decisao:
    status: int  # 0: not ours (pass through); 200: forward; anything else: answer it here
    motivo: str
    tipo: str | None = None


def classificar(caminho: str) -> str | None:
    if caminho in PAGINAS:
        return "pagina"
    if caminho == API:
        return "api"
    if caminho in PUBLICOS:
        return "publico"
    if caminho.startswith("/_next/static/") and ESTATICO.match(caminho):
        return "estatico"
    if caminho.startswith(PREFIXOS):
        return "invalido"
    return None


def decidir(metodo: str, caminho: str, cabecalhos: dict, consulta: list, sessao, hash_global, corpo: int) -> Decisao:
    """Pure: what to do with one request. cabecalhos: lower-case names; consulta: [(key, value)]."""
    tipo = classificar(caminho)
    if tipo is None:
        return Decisao(0, "fora")
    if tipo == "invalido":
        return Decisao(404, "caminho não permitido", tipo)
    if not isinstance(hash_global, str) or not hash_global:
        return Decisao(401, "login do Agent Zero desligado", tipo)  # no global credentials: never open
    aut = sessao.get("authentication") if sessao is not None else None
    if not isinstance(aut, str) or not hmac.compare_digest(aut.encode(), hash_global.encode()):
        return Decisao(401, "sem sessão válida", tipo)
    if sessao.get("usuario") != DONO or sessao.get("user_id") != DONO:
        return Decisao(403, "só o Matheus", tipo)
    if any(CABECALHO_IDENTIDADE.match(k) for k in cabecalhos):
        return Decisao(403, "seleção de identidade não é permitida", tipo)
    if any(CONSULTA_IDENTIDADE.match(str(k)) for k, _ in consulta):
        return Decisao(403, "seleção de identidade não é permitida", tipo)
    if tipo == "api" and consulta:
        return Decisao(400, "parâmetros de consulta não são aceitos", tipo)
    if metodo not in METODOS[tipo]:
        return Decisao(405, "método não permitido", tipo)
    if corpo:
        return Decisao(413, "corpo não é aceito", tipo)
    return Decisao(200, "encaminhar", tipo)


def cabecalhos_upstream(tipo: str, cabecalhos: dict, porta: int, token: str) -> dict:
    """Built from scratch: nothing from the client but a sane Accept."""
    h = {"Host": f"127.0.0.1:{porta}", "Accept-Encoding": "identity", "Connection": "close",
         "User-Agent": "segundo-cerebro-gateway"}
    accept = cabecalhos.get("accept", "")
    if accept and len(accept) <= 512 and re.fullmatch(r"[\x20-\x7e]*", accept):
        h["Accept"] = accept
    if tipo == "api":
        h["Authorization"] = f"Bearer {token}"
    return h


def _location(valor: str | None) -> str | None:
    if not valor or not valor.startswith("/") or valor.startswith("//") or "\\" in valor:
        return None
    return valor if classificar(valor.split("?", 1)[0]) in ("pagina", "api", "estatico", "publico") else None


def encaminhar(tipo: str, metodo: str, caminho: str, cabecalhos: dict, processo) -> tuple[int, dict, bytes]:
    """Ask the loopback Next server. Never raises: problems become 503/502."""
    try:
        porta, token = processo.garantir()
    except Exception:
        return _json(503, "Segundo Cérebro indisponível agora. Tente de novo em instantes.")
    conexao = http.client.HTTPConnection("127.0.0.1", porta, timeout=TEMPO_UPSTREAM)
    try:
        conexao.request(metodo, quote(caminho, safe="/-._~"), headers=cabecalhos_upstream(tipo, cabecalhos, porta, token))
        r = conexao.getresponse()
        corpo = r.read(LIMITE_RESPOSTA + 1)
        status, tipo_conteudo, local = r.status, r.getheader("Content-Type"), r.getheader("Location")
    except (OSError, http.client.HTTPException):
        processo.falhou()
        return _json(503, "Segundo Cérebro indisponível agora. Tente de novo em instantes.")
    finally:
        conexao.close()
    if len(corpo) > LIMITE_RESPOSTA:
        return _json(502, "Resposta grande demais.")
    if tipo == "api" and status in (401, 403):  # the internal bearer was refused: our problem, not the user's
        return _json(502, "Configuração interna do Segundo Cérebro inválida.")
    h = {}
    if tipo_conteudo and re.fullmatch(r"[\x20-\x7e]{1,200}", tipo_conteudo):
        h["Content-Type"] = tipo_conteudo
    if 300 <= status < 400:
        destino = _location(local)
        if destino is None:
            return _json(502, "Redirecionamento inesperado.")
        h["Location"] = destino
    return status, h, corpo


def _json(status: int, mensagem: str) -> tuple[int, dict, bytes]:
    return status, {"Content-Type": "application/json; charset=utf-8"}, json.dumps({"erro": mensagem}).encode()


def _html(status: int, titulo: str, texto: str, link: str, rotulo: str) -> tuple[int, dict, bytes]:
    corpo = (f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>{titulo}</title>'
             f'<meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<body style="font-family:system-ui;background:#0d0d0d;color:#eee;display:grid;place-items:center;'
             f'min-height:100vh;margin:0"><main><h1>{titulo}</h1><p>{texto}</p><p><a style="color:#9cf" '
             f'href="{link}">{rotulo}</a></p></main></body></html>')
    return status, {"Content-Type": "text/html; charset=utf-8"}, corpo.encode()


def resposta_erro(d: Decisao) -> tuple[int, dict, bytes]:
    if d.tipo == "pagina" and d.status == 401:
        return _html(401, "Segundo Cérebro", "Entre com a sua conta para ver esta página.", LOGIN, "Entrar")
    if d.tipo == "pagina" and d.status == 403:
        return _html(403, "Segundo Cérebro", "Esta página é só do Matheus.", "/logout", "Sair e entrar com outra conta")
    status, h, corpo = _json(d.status, {401: "Não autorizado.", 403: "Proibido.", 404: "Não encontrado.",
                                        405: "Método não permitido.", 400: "Parâmetros não aceitos.",
                                        413: "Corpo não aceito."}.get(d.status, "Erro."))
    if d.status == 405 and d.tipo in METODOS:
        h["Allow"] = ", ".join(METODOS[d.tipo])
    return status, h, corpo


# ---------- Flask ----------

def tratar_flask(processo, obter_hash):
    """The before_request body: None lets Flask continue (route not ours)."""
    from flask import Response, request, session

    cab = {k.lower(): v for k, v in request.headers.items()}
    corpo = request.content_length or (1 if "transfer-encoding" in cab else 0)
    try:
        hash_global = obter_hash()
    except Exception:
        hash_global = None
    d = decidir(request.method, request.path, cab, list(request.args.items(multi=True)), session, hash_global, corpo)
    if d.status == 0:
        return None
    if d.status != 200:
        status, h, dados = resposta_erro(d)
    else:
        status, h, dados = encaminhar(d.tipo, request.method, request.path, cab, processo)
    resp = Response(b"" if request.method == "HEAD" else dados, status=status)
    for k, v in {**h, **SEGURANCA}.items():
        resp.headers[k] = v
    return resp


def _hash_do_framework():
    from helpers import login

    return login.get_credentials_hash()


# ---------- registration (state survives reloads of this file) ----------

ESTADO = "segundo_cerebro_estado"
NOME_MODULO = "segundo_cerebro_gateway"


def estado() -> types.ModuleType:
    m = sys.modules.get(ESTADO)
    if m is None:
        m = types.ModuleType(ESTADO)
        m.processo = None
        m.desativado = False
        sys.modules[ESTADO] = m
    return m


def _carregar(nome: str, arquivo: Path):
    m = sys.modules.get(nome)
    mtime = arquivo.stat().st_mtime
    if m is None or getattr(m, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, arquivo)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return m


def processo_padrao():
    """The one Node server of this Agent Zero process; replaced (and the old one stopped) when processo.py changes."""
    P = _carregar("segundo_cerebro_processo", PLUGIN_DIR / "helpers" / "processo.py").Processo
    est = estado()
    if not isinstance(est.processo, P):
        if est.processo is not None:
            est.processo.parar()
        est.processo = P()
    return est.processo


def ativo(plugin_dir: Path = PLUGIN_DIR) -> bool:
    return (not estado().desativado and (plugin_dir / "helpers" / "gateway.py").is_file()
            and not (plugin_dir / ".toggle-0").exists())


def parar_tudo() -> None:
    est = estado()
    if est.processo is not None:
        est.processo.parar()


def registrar(webapp, obter_hash=None, processo=None, plugin_dir: Path = PLUGIN_DIR) -> bool:
    """Put the gateway first in webapp's before_request list, once. obter_hash/processo: tests only."""
    if webapp.extensions.get("segundo_cerebro_gateway"):
        return False

    def segundo_cerebro_gateway():
        if not ativo(plugin_dir):  # rolled back / disabled / uninstalled: nothing here is served any more
            if classificar(_caminho_atual()) is not None:
                parar_tudo()
            return None
        if processo is not None:  # tests: this module, the given server
            return tratar_flask(processo, obter_hash or _hash_do_framework)
        atual = _carregar(NOME_MODULO, plugin_dir / "helpers" / "gateway.py")
        return atual.tratar_flask(atual.processo_padrao(), obter_hash or atual._hash_do_framework)

    webapp.before_request_funcs.setdefault(None, []).insert(0, segundo_cerebro_gateway)
    webapp.extensions["segundo_cerebro_gateway"] = segundo_cerebro_gateway
    return True


def _caminho_atual() -> str:
    from flask import request

    return request.path


def instalar_wrapper(ui_server=None) -> bool:
    """Wrap UiServerRuntime.create (idempotent) so the web app it builds gets the gateway. Core files untouched."""
    if ui_server is None:
        from helpers import ui_server
    cls = ui_server.UiServerRuntime
    original = cls.__dict__.get("create")
    if not isinstance(original, classmethod):
        raise RuntimeError("UiServerRuntime.create não é mais um classmethod: gateway não registrado")
    func = original.__func__
    if getattr(func, "_segundo_cerebro", False):
        return False
    arquivo = PLUGIN_DIR / "helpers" / "gateway.py"

    def create(klass, *args, **kwargs):
        runtime = func(klass, *args, **kwargs)
        try:
            _carregar(NOME_MODULO, arquivo).registrar(runtime.webapp)
        except Exception as exc:  # the rest of Agent Zero must still start; our routes then stay unserved (404)
            print(f"segundo_cerebro: gateway não registrado: {type(exc).__name__}: {exc}", flush=True)
        return runtime

    create._segundo_cerebro = True
    create.__wrapped__ = func
    cls.create = classmethod(create)
    estado().desativado = False
    return True


def validar_plugin(plugin_dir: Path = PLUGIN_DIR) -> list[str]:
    """Problems that make the plugin unsafe to enable (used by hooks.install and the deploy stage)."""
    problemas = []
    for rel in ("plugin.yaml", "hooks.py", "helpers/gateway.py", "helpers/processo.py",
                "extensions/python/startup_migration/_15_segundo_cerebro_gateway.py"):
        p = plugin_dir / rel
        if not p.is_file() or p.is_symlink():
            problemas.append(f"falta {rel}")
    if (plugin_dir / "execute.py").exists():
        problemas.append("execute.py não deve existir (o ciclo de vida fica em hooks.py)")
    for p in plugin_dir.rglob("*"):
        if p.is_symlink():
            problemas.append(f"link simbólico: {p.relative_to(plugin_dir)}")
    return problemas

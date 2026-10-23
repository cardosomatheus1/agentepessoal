"""Bridge between the Hermes and the tools of Agent Zero plugins (23/10 migration, docs/MIGRACAO_HERMES.md).

The tools of our plugins (/a0/usr/plugins/<plugin>/tools/<name>.py) are thin classes over pure helpers; from Agent Zero
they only need `helpers.tool.Tool`/`Response` and an agent whose `context` tells who is talking. This module provides
exactly that, so the same file runs under the Hermes with no change and no copy: the helpers, the data paths
(/a0/usr/...) and the rules (CLAUDE.md: changes only through the helpers' functions) stay the same.

- `instalar_modulos()` puts minimal `helpers`, `helpers.tool`, `helpers.extension` modules in sys.modules (the Hermes has
  no `helpers` package; nothing of Agent Zero is imported).
- `Conversa` is the context of one Hermes session: id, the person's login (`dono`/`usuario`), and the per-chat data the
  tools keep with get_data/set_data.
- `carregar(plugin, nome)` loads a tool class from its file; `esquema(...)` builds the JSON schema the model sees from
  the `execute` signature and the tool's own manual (prompts/agent.system.tool.<name>.md); `executar(...)` runs it."""
from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import threading
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLUGINS = Path("/a0/usr/plugins")
DADOS = Path("/opt/data/agentepessoal")
SESSOES = DADOS / "sessoes.json"   # session id -> login, written by the bridge (ponte) when it opens a session
PREFIXO_MIN = 4                    # "cron_*" ok; "*" or "c*" would hand every session to one person
DONO_PADRAO = "matheus"            # sessions nobody claimed (operator tests, cron of the owner) are the owner's
MANUAL_MAX = 6000                  # characters of the tool manual that go into the schema description


@dataclass
class Response:
    message: str
    break_loop: bool = False
    additional: dict[str, Any] | None = None


class Tool:
    """The constructor and attributes the Agent Zero tools rely on (helpers/tool.py of A0 v2.13)."""

    def __init__(self, agent, name: str, method: str | None, args: dict, message: str, loop_data=None, **kwargs):
        self.agent, self.name, self.method, self.args, self.loop_data, self.message = agent, name, method, args, loop_data, message
        self.progress = ""

    async def execute(self, **kwargs) -> Response:  # pragma: no cover - always overridden
        raise NotImplementedError

    async def set_progress(self, content: str | None):
        self.progress = content or ""

    def add_progress(self, content: str | None):
        self.progress += content or ""


async def _sem_extensoes(*args, **kwargs):
    return None


class NavegadorCDP:
    """O que as nossas ferramentas pedem ao navegador do A0 (plugins._browser.helpers.runtime: listar as abas e rodar um
    script NOSSO numa delas, ex.: a lista do Direct, sem passar pelo modelo), no navegador do Hermes, por CDP
    (BROWSER_CDP_URL, hermes/navegador.sh). Os scripts são os fixos do código das ferramentas, nunca texto do modelo."""

    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def _abas(self) -> list:
        import urllib.request

        with urllib.request.urlopen(f"{self.base}/json/list", timeout=10) as r:
            return [a for a in json.loads(r.read() or b"[]") if a.get("type") == "page"]

    async def call(self, metodo: str, *args, **kw):
        import asyncio
        import re

        if metodo == "list":
            abas = await asyncio.to_thread(self._abas)
            return {"browsers": [{"id": a["id"], "currentUrl": a.get("url", ""), "title": a.get("title", "")} for a in abas]}
        if metodo == "evaluate":
            aba_id, js = args[0], str(args[1])
            alvo = next((a for a in await asyncio.to_thread(self._abas) if a["id"] == aba_id), None)
            if alvo is None:
                raise LookupError("aba fechada")
            if re.match(r"^\s*(async\s*)?(\(\s*\)|function\s*\(\s*\))\s*(=>|\{)", js) and not re.search(r"\)\s*\(\s*\)\s*;?\s*$", js):
                js = f"({js})()"  # uma função: chamada, como o evaluate do Playwright faz
            import websockets

            async with websockets.connect(alvo["webSocketDebuggerUrl"], max_size=50_000_000, open_timeout=10) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
                    "expression": js, "returnByValue": True, "awaitPromise": True}}))
                while True:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                    if msg.get("id") == 1:
                        break
            res = msg.get("result") or {}
            if res.get("exceptionDetails"):
                raise RuntimeError(str(res["exceptionDetails"].get("text") or "erro no script")[:300])
            return {"result": (res.get("result") or {}).get("value")}
        if metodo == "navigate":  # (aba, url)
            await self._cdp(args[0], "Page.navigate", {"url": str(args[1])})
            return {"id": args[0]}
        if metodo == "open":  # (url) -> {"id": nova aba}
            import urllib.parse
            import urllib.request

            def abrir():
                req = urllib.request.Request(f"{self.base}/json/new?{urllib.parse.quote(str(args[0]), safe=':/?&=%')}",
                                             method="PUT")
                with urllib.request.urlopen(req, timeout=10) as r:
                    return json.loads(r.read() or b"{}")
            return {"id": (await asyncio.to_thread(abrir)).get("id")}
        if metodo == "keyboard":  # (aba, key=..., text=...): o teclado do Playwright que as ferramentas do A0 usam
            aba = args[0]
            if kw.get("text"):
                await self._cdp(aba, "Input.insertText", {"text": str(kw["text"])})
            if kw.get("key"):
                await self._tecla(aba, str(kw["key"]))
            return {}
        if metodo == "key_chord":  # (aba, ["Control", "a"])
            await self._tecla(args[0], str(args[1][-1]), [str(t) for t in args[1][:-1]])
            return {}
        if metodo == "screenshot":  # (aba ou None, quality=..) -> {"image": base64, "state": {url, title}}
            abas = await asyncio.to_thread(self._abas)
            alvo = next((a for a in abas if a["id"] == args[0]), None) if args and args[0] else (abas[0] if abas else None)
            if alvo is None:
                raise LookupError("nenhuma aba aberta")
            r = await self._cdp(alvo["id"], "Page.captureScreenshot",
                                {"format": "jpeg", "quality": int(kw.get("quality") or 60)})
            return {"image": r.get("data", ""), "state": {"url": alvo.get("url", ""), "title": alvo.get("title", "")}}
        raise ValueError(f"navegador: {metodo} não existe aqui")

    async def _cdp(self, aba_id: str, metodo: str, params: dict) -> dict:
        """Um comando CDP numa aba (só os fixos acima, pedidos pelo código das ferramentas)."""
        import asyncio

        import websockets

        alvo = next((a for a in await asyncio.to_thread(self._abas) if a["id"] == aba_id), None)
        if alvo is None:
            raise LookupError("aba fechada")
        async with websockets.connect(alvo["webSocketDebuggerUrl"], max_size=50_000_000, open_timeout=10) as ws:
            await ws.send(json.dumps({"id": 1, "method": metodo, "params": params}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if msg.get("id") == 1:
                    break
        if msg.get("error"):
            raise RuntimeError(str(msg["error"].get("message") or msg["error"])[:300])
        return msg.get("result") or {}

    TECLAS = {"Enter": (13, "\r"), "Backspace": (8, ""), "Tab": (9, "\t"), "Escape": (27, ""), "Delete": (46, "")}
    MODIFICADORES = {"Alt": 1, "Control": 2, "Meta": 4, "Shift": 8}

    async def _tecla(self, aba: str, tecla: str, mods: list | None = None) -> None:
        bits = sum(self.MODIFICADORES.get(m, 0) for m in (mods or []))
        codigo, texto = self.TECLAS.get(tecla, (ord(tecla.upper()[0]) if len(tecla) == 1 else 0, tecla if len(tecla) == 1 else ""))
        if bits & 2:
            texto = ""  # Ctrl+A etc.: comando, não texto
        base = {"key": tecla, "windowsVirtualKeyCode": codigo, "modifiers": bits,
                "code": f"Key{tecla.upper()}" if len(tecla) == 1 else tecla}
        await self._cdp(aba, "Input.dispatchKeyEvent", {**base, "type": "keyDown" if texto else "rawKeyDown",
                                                        **({"text": texto} if texto else {})})
        await self._cdp(aba, "Input.dispatchKeyEvent", {**base, "type": "keyUp"})


async def _navegador(context_id=None, create: bool = False):
    import os

    base = os.environ.get("BROWSER_CDP_URL", "")
    return NavegadorCDP(base) if base else None


def instalar_modulos() -> None:
    if "helpers.tool" in sys.modules and getattr(sys.modules["helpers.tool"], "_ponte_a0", False):
        return
    pacote = sys.modules.get("helpers") or types.ModuleType("helpers")
    pacote.__path__ = []  # a namespace for the stubs only
    tool = types.ModuleType("helpers.tool")
    tool.Tool, tool.Response, tool._ponte_a0 = Tool, Response, True
    extension = types.ModuleType("helpers.extension")
    extension.call_extensions_async = _sem_extensoes
    extension.Extension = type("Extension", (), {})
    # o celular importa chat_media/history no topo (no A0, para pôr a tela no histórico, em after_execution, que aqui
    # não roda: a tela vira um arquivo, ver executar)
    chat_media, history = types.ModuleType("helpers.chat_media"), types.ModuleType("helpers.history")
    history.RawMessage = type("RawMessage", (), {"__init__": lambda self, **k: self.__dict__.update(k)})
    sys.modules.update({"helpers": pacote, "helpers.tool": tool, "helpers.extension": extension,
                        "helpers.chat_media": chat_media, "helpers.history": history})
    pacote.tool, pacote.extension, pacote.chat_media, pacote.history = tool, extension, chat_media, history
    if "plugins._browser.helpers.runtime" not in sys.modules:  # o navegador do A0 -> o do Hermes, por CDP
        runtime = types.ModuleType("plugins._browser.helpers.runtime")
        runtime.get_runtime = _navegador
        try:  # o pacote `plugins` do PRÓPRIO Hermes (gateway importa plugins.memory etc.): só ganha o _browser
            import plugins  # noqa: F401
        except ImportError:
            sys.modules["plugins"] = types.ModuleType("plugins")
            sys.modules["plugins"].__path__ = []
        for nome in ("plugins._browser", "plugins._browser.helpers"):
            m = sys.modules.get(nome) or types.ModuleType(nome)
            m.__path__ = getattr(m, "__path__", [])
            sys.modules[nome] = m
        sys.modules["plugins._browser.helpers"].runtime = runtime
        sys.modules["plugins._browser"].helpers = sys.modules["plugins._browser.helpers"]
        sys.modules["plugins"]._browser = sys.modules["plugins._browser"]
        sys.modules["plugins._browser.helpers.runtime"] = runtime


_TRAVA = threading.Lock()
_CONVERSAS: dict[str, "Conversa"] = {}


def login_mapeado(sessao: str) -> str:
    """The login the bridge recorded for this session ("" when nobody did). A key ending in `*` covers every session
    that starts with it (e.g. the Hermes cron sessions of one person's routine)."""
    try:
        mapa = json.loads(SESSOES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        mapa = {}
    if not isinstance(mapa, dict):
        return ""
    login = mapa.get(sessao)
    if not login:
        prefixos = sorted((k for k in mapa if isinstance(k, str) and k.endswith("*") and len(k) > PREFIXO_MIN and sessao.startswith(k[:-1])),
                          key=len, reverse=True)
        login = mapa[prefixos[0]] if prefixos else ""
    return str(login or "").strip().lower()


def convidado_da_instancia() -> str:
    """O login do convidado quando este Hermes é o dele (hermes-<login>, subir.sh): tudo aqui é dele."""
    import os

    return str(os.environ.get("AGENTEPESSOAL_CONVIDADO") or "").strip().lower()


def login_da_sessao(sessao: str) -> str:
    return convidado_da_instancia() or login_mapeado(sessao) or DONO_PADRAO


class Conversa:
    """The Agent Zero `AgentContext` surface our tools use: id, name, get_data/set_data (login under dono/usuario)."""

    def __init__(self, sessao: str, login: str):
        self.id = sessao
        self.name = sessao
        self._dados = {"dono": login, "usuario": login, "usuario_nome": login.capitalize(), "hermes": True}

    def get_data(self, chave, recursive: bool = True):
        return self._dados.get(chave)

    def set_data(self, chave, valor, recursive: bool = True):
        self._dados[chave] = valor

    def get_output_data(self, chave, recursive: bool = True):
        return None

    def set_output_data(self, chave, valor, recursive: bool = True):
        return None


def conversa(sessao: str | None) -> Conversa:
    sessao = str(sessao or "hermes-operador")
    with _TRAVA:
        c = _CONVERSAS.get(sessao)
        if c is None:
            c = _CONVERSAS[sessao] = Conversa(sessao, login_da_sessao(sessao))
        return c


class _Historico:
    def output(self):
        return []

    def serialize(self):
        return "[]"


class Agente:
    """The Agent Zero `Agent` surface our tools touch: context, its data, an empty history, no intervention."""

    def __init__(self, ctx: Conversa):
        self.context, self.intervention, self.history = ctx, None, _Historico()
        self.number, self.agent_name, self.config = 0, "A0", types.SimpleNamespace()

    def get_data(self, chave):
        return self.context.get_data(chave)

    def set_data(self, chave, valor):
        self.context.set_data(chave, valor)

    def hist_add_message(self, *args, **kwargs):
        return None


_CLASSES: dict[str, tuple[float, type]] = {}


def carregar(plugin: str, nome: str):
    """The Tool subclass in /a0/usr/plugins/<plugin>/tools/<nome>.py (the same file Agent Zero runs), loaded again when
    the file changes (implantar.py of a plugin takes effect on the next call, as in Agent Zero; no Hermes restart)."""
    instalar_modulos()
    arquivo = PLUGINS / plugin / "tools" / f"{nome}.py"
    mtime = arquivo.stat().st_mtime
    guardada = _CLASSES.get(f"{plugin}/{nome}")
    if guardada and guardada[0] == mtime:
        return guardada[1]
    spec = importlib.util.spec_from_file_location(f"hermes_a0_{plugin}_{nome}", arquivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    for valor in vars(modulo).values():
        if inspect.isclass(valor) and issubclass(valor, Tool) and valor is not Tool:
            _CLASSES[f"{plugin}/{nome}"] = (mtime, valor)
            return valor
    raise LookupError(f"{arquivo}: nenhuma classe de ferramenta")


def _tipo(param: inspect.Parameter) -> dict:
    padrao = param.default
    anot = str(param.annotation)
    if isinstance(padrao, bool) or "bool" in anot:
        return {"type": "boolean"}
    if isinstance(padrao, int) or anot in ("int", "<class 'int'>"):
        return {"type": "integer"}
    if isinstance(padrao, float):
        return {"type": "number"}
    if isinstance(padrao, list) or "list" in anot:
        return {"type": "array", "items": {}}
    if isinstance(padrao, dict) or "dict" in anot:
        return {"type": "object"}
    if isinstance(padrao, str) or "str" in anot:
        return {"type": "string"}
    return {}  # any JSON value (None defaults: lists, dicts or strings, as the manual says)


def manual(plugin: str, nome: str) -> str:
    arquivo = PLUGINS / plugin / "prompts" / f"agent.system.tool.{nome}.md"
    try:
        texto = arquivo.read_text(encoding="utf-8").strip()
    except OSError:
        return f"Ferramenta {nome} do agente do Matheus."
    return texto if len(texto) <= MANUAL_MAX else texto[:MANUAL_MAX].rsplit("\n", 1)[0] + "\n…"


def esquema(plugin: str, nome: str, classe) -> dict:
    props, livre = {}, False
    for p in inspect.signature(classe.execute).parameters.values():
        if p.name == "self":
            continue
        if p.kind is inspect.Parameter.VAR_KEYWORD:
            livre = True
            continue
        props[p.name] = _tipo(p)
    return {"name": nome, "description": manual(plugin, nome),
            "parameters": {"type": "object", "properties": props, "additionalProperties": livre or not props}}


async def executar(classe, nome: str, args: dict, sessao: str | None) -> str:
    args = dict(args or {})
    agente = Agente(conversa(sessao))
    ferramenta = classe(agent=agente, name=nome, method=None, args=args, message="", loop_data=None)
    aceitos = inspect.signature(classe.execute).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in aceitos.values()):
        kwargs = args
    else:
        kwargs = {k: v for k, v in args.items() if k in aceitos}
    try:
        resposta = await ferramenta.execute(**kwargs)
    except Exception as exc:
        if somente_leitura(exc):
            return ERRO_SO_LEITURA
        raise
    texto = resposta.message if isinstance(resposta, Response) else str(resposta)
    imagem = getattr(ferramenta, "_imagem", None)  # a tela do celular: no A0 ia para o histórico; aqui, um arquivo
    if isinstance(imagem, (bytes, bytearray)) and imagem:
        texto += "\n" + guardar_imagem(bytes(imagem), nome)
    return texto


IMAGENS = DADOS / "telas"


def guardar_imagem(dados: bytes, nome: str) -> str:
    import time

    IMAGENS.mkdir(parents=True, exist_ok=True)
    for velha in sorted(IMAGENS.glob("*.jpg"))[:-40]:  # só as últimas 40
        velha.unlink(missing_ok=True)
    arquivo = IMAGENS / f"{nome}-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}.jpg"
    arquivo.write_bytes(dados)
    return f"[imagem da tela salva em {arquivo}: veja com vision_analyze se precisar]"


# Ensaio até a virada (docs/MIGRACAO_HERMES.md): os dados do A0 chegam aqui só para leitura (agentepessoal-hermes-dados).
# Uma ação que grava (ou pega trava) cai aqui com um erro claro, para o modelo não tentar outros caminhos à toa.
ERRO_SO_LEITURA = ("Ensaio do Hermes: os dados do agente estão só para leitura até a virada, e esta ação grava neles. "
                   "Ela continua sendo feita pelo agente de hoje; não tente de outro jeito. Diga ao operador o que ia fazer.")


def somente_leitura(exc: BaseException) -> bool:
    import errno
    import sqlite3

    if isinstance(exc, OSError) and (exc.errno == errno.EROFS or (
            exc.errno == errno.EACCES and str(exc.filename or "").startswith("/a0/usr/"))):
        return True  # EACCES: as pastas escondidas no ensaio (whatsapp, segredos: tmpfs vazio do root)
    texto = str(exc).lower()
    return isinstance(exc, sqlite3.OperationalError) and ("readonly" in texto or "read-only" in texto
                                                          or "unable to open database" in texto)

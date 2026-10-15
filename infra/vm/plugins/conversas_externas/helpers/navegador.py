"""The person's WhatsApp Web, driven by code (no model): one dedicated chat per person owns the tab, so the browser is
always that person's own profile (navegador_por_pessoa) and only one WhatsApp Web tab exists (WhatsApp allows one).
Never runs on a profile of someone else: the owner of the tab's chat is checked before every call."""

import asyncio
import json
import sys
import urllib.parse

WEB = "https://web.whatsapp.com/"
NOME_CONVERSA = "WhatsApp de {nome} (conversas com lojas)"


_TRAVAS: dict = {}  # one WhatsApp Web tab per person: the watcher and the tool never drive it at the same time


def trava(login: str) -> asyncio.Lock:
    return _TRAVAS.setdefault(login, asyncio.Lock())


class SemWhatsApp(Exception):
    """The person's WhatsApp is not connected (or the tab could not be used); the message says what to do."""


def _dono(ctx) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return (sep.dono_contexto(ctx) if sep else str(ctx.get_data("dono") or "")).lower()


def contexto(ex, login: str, nome: str):
    """The person's dedicated chat for the WhatsApp tab (created once, kept in the state file)."""
    from agent import AgentContext

    d = ex.carregar(login)
    ctx = AgentContext.get(d.get("contexto_whatsapp") or "") if d.get("contexto_whatsapp") else None
    if ctx is not None and _dono(ctx) == login:
        return ctx
    from helpers import projects
    from helpers.persist_chat import save_tmp_chat
    from initialize import initialize_agent

    ctx = AgentContext(config=initialize_agent(), name=NOME_CONVERSA.format(nome=nome))
    ctx.set_data("dono", login)
    ctx.set_data("usuario", login)
    conv = sys.modules.get("login_usuarios_convidados")
    if conv is not None and conv.convidado(login):
        try:
            projects.activate_project(ctx.id, conv.preparar(login, projects), mark_dirty=False)
        except Exception as exc:
            print(f"conversas_externas: projeto do convidado não ativado: {exc}", flush=True)
    save_tmp_chat(ctx)
    with ex.transacao(login) as dd:
        dd["contexto_whatsapp"] = ctx.id
    return ctx


async def _runtime(ex, login: str, nome: str):
    from plugins._browser.helpers import runtime as modulo

    ctx = contexto(ex, login, nome)
    if _dono(ctx) != login:
        raise SemWhatsApp("a aba do WhatsApp não é desta pessoa")
    perfis = sys.modules.get("navegador_por_pessoa_perfis")
    if perfis is not None and perfis.dono(ctx.id) != login:
        raise SemWhatsApp("o navegador desta conversa não é o perfil desta pessoa")
    return await modulo.get_runtime(ctx.id, create=True)


async def _aba(rt) -> int:
    abas = (await rt.call("list")).get("browsers") or []
    for a in abas:
        if "web.whatsapp.com" in str(a.get("currentUrl") or a.get("url") or ""):
            return a["id"]
    if abas:
        await rt.call("navigate", abas[0]["id"], WEB)
        return abas[0]["id"]
    return (await rt.call("open", WEB))["id"]


async def _js(rt, aba, script: str):
    res = await rt.call("evaluate", aba, script)
    valor = res.get("result", res.get("value")) if isinstance(res, dict) else res
    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except ValueError:
            return valor
    return valor


async def _esperar(rt, aba, ex, cond, segundos: float = 40.0) -> dict:
    est = {}
    for _ in range(int(segundos / 2)):
        est = await _js(rt, aba, ex.SCRIPT_ESTADO) or {}
        if isinstance(est, dict) and cond(est):
            return est
        await asyncio.sleep(2)
    return est if isinstance(est, dict) else {}


async def _estado(ex, login: str, nome: str) -> dict:
    rt = await _runtime(ex, login, nome)
    aba = await _aba(rt)
    return await _esperar(rt, aba, ex, lambda e: e.get("logado") or e.get("pede_numero") or e.get("qr") or e.get("codigo"), 30)


async def _conectar(ex, login: str, nome: str, tel: str) -> dict:
    """Start "link with phone number": returns {"codigo": "ABCD1234"} for the person to type on the phone
    (WhatsApp > Aparelhos conectados > Conectar aparelho > Conectar com número de telefone), or {"logado": True}."""
    numero = ex.telefone(tel)
    rt = await _runtime(ex, login, nome)
    aba = await _aba(rt)
    est = await _esperar(rt, aba, ex, lambda e: e.get("logado") or e.get("qr") or e.get("pede_numero"), 40)
    if est.get("logado"):
        return {"logado": True}
    if not est.get("pede_numero"):
        await _js(rt, aba, ex.SCRIPT_ENTRAR_COM_NUMERO)
        await asyncio.sleep(2)
    if await _js(rt, aba, ex.SCRIPT_CAMPO_TELEFONE) != "foco":
        raise SemWhatsApp(f"não achei o campo do número no WhatsApp Web (tela: {json.dumps(est)[:200]})")
    await rt.call("key_chord", aba, ["Control", "a"])
    await rt.call("keyboard", aba, key="Backspace")
    await rt.call("keyboard", aba, text="+" + numero)
    await _js(rt, aba, ex.SCRIPT_AVANCAR)
    est = await _esperar(rt, aba, ex, lambda e: e.get("codigo") or e.get("logado"), 30)
    if est.get("codigo"):
        return {"codigo": est["codigo"]}
    if est.get("logado"):
        return {"logado": True}
    raise SemWhatsApp(f"o WhatsApp Web não mostrou o código (tela: {json.dumps(est)[:200]})")


async def _abrir_conversa(rt, aba, ex, numero: str, texto: str = "") -> dict:
    url = f"{WEB}send?phone={numero}" + (f"&text={urllib.parse.quote(texto)}" if texto else "")
    await rt.call("navigate", aba, url)
    est = await _esperar(rt, aba, ex, lambda e: e.get("conversa_aberta") or e.get("invalido")
                         or (not e.get("logado") and (e.get("qr") or e.get("pede_numero"))), 45)
    if est.get("invalido"):
        raise SemWhatsApp(f"o número {numero} não tem WhatsApp (o WhatsApp Web recusou)")
    if not est.get("conversa_aberta"):
        if est.get("qr") or est.get("pede_numero"):
            raise SemWhatsApp("o WhatsApp da pessoa não está conectado: chame acao \"conectar\"")
        raise SemWhatsApp(f"a conversa não abriu no WhatsApp Web (tela: {json.dumps(est)[:200]})")
    return est


async def _enviar(ex, login: str, nome: str, numero: str, texto: str) -> list:
    """Send `texto` to `numero` from the person's WhatsApp; returns the messages on the screen after it went."""
    rt = await _runtime(ex, login, nome)
    aba = await _aba(rt)
    await _abrir_conversa(rt, aba, ex, numero, texto)
    r = ""
    for _ in range(5):
        r = await _js(rt, aba, ex.SCRIPT_ENVIAR)
        if r == "clicado":
            break
        if r == "foco":
            await rt.call("keyboard", aba, key="Enter")
            r = "clicado"
            break
        await asyncio.sleep(1.5)
    if r != "clicado":
        raise SemWhatsApp(f"não consegui enviar ({r})")
    inicio = " ".join(texto.split())[:40]
    for _ in range(8):
        await asyncio.sleep(1.5)
        lidas = (await _js(rt, aba, ex.SCRIPT_MENSAGENS) or {}).get("mensagens") or []
        if any(m["de"] == "eu" and inicio[:25] in " ".join(m["texto"].split()) for m in lidas[-5:]):
            return lidas
    raise SemWhatsApp("cliquei em enviar, mas a mensagem não apareceu na conversa: confira antes de mandar de novo")


async def _ler(ex, login: str, nome: str, numero: str) -> dict:
    """{"mensagens": [...]} of the conversation with `numero` (or {"mensagens": [], "texto_da_tela": ...})."""
    rt = await _runtime(ex, login, nome)
    aba = await _aba(rt)
    await _abrir_conversa(rt, aba, ex, numero)
    await asyncio.sleep(2)
    r = await _js(rt, aba, ex.SCRIPT_MENSAGENS)
    return r if isinstance(r, dict) else {"mensagens": []}


async def estado(ex, login: str, nome: str) -> dict:
    async with trava(login):
        return await _estado(ex, login, nome)


async def conectar(ex, login: str, nome: str, tel: str) -> dict:
    async with trava(login):
        return await _conectar(ex, login, nome, tel)


async def enviar(ex, login: str, nome: str, numero: str, texto: str) -> list:
    async with trava(login):
        return await _enviar(ex, login, nome, numero, texto)


async def ler(ex, login: str, nome: str, numero: str) -> dict:
    async with trava(login):
        return await _ler(ex, login, nome, numero)


def manter_acordado(ex, login: str) -> None:
    """Writing the WhatsApp chat's file is "use" for the VM's idle watchdog (watchdog.sh): while a business may answer
    soon, the VM stays up to see it."""
    from agent import AgentContext
    from helpers.persist_chat import save_tmp_chat

    ctx = AgentContext.get(ex.carregar(login).get("contexto_whatsapp") or "")
    if ctx is not None:
        save_tmp_chat(ctx)

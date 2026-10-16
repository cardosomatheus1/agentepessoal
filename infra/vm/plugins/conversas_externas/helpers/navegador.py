"""The person's WhatsApp Web, driven by code (no model): one dedicated chat per person owns the tab, so the browser is
always that person's own profile (navegador_por_pessoa) and only one WhatsApp Web tab exists (WhatsApp allows one).
Never runs on a profile of someone else: the owner of the tab's chat is checked before every call."""

import asyncio
import json
import re
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
    await asyncio.sleep(3)  # the login page settles a moment after it shows
    if est.get("logado"):
        return {"logado": True}
    if not est.get("pede_numero"):
        await _js(rt, aba, ex.SCRIPT_ENTRAR_COM_NUMERO)
        await _esperar(rt, aba, ex, lambda e: e.get("pede_numero"), 10)
    if await _js(rt, aba, ex.SCRIPT_CAMPO_TELEFONE) != "foco":
        raise SemWhatsApp(f"não achei o campo do número no WhatsApp Web (tela: {json.dumps(est)[:200]})")
    await rt.call("key_chord", aba, ["Control", "a"])
    for _ in range(4):  # the field starts with "+1 "; cleared, "+55…" switches the country by itself
        await rt.call("keyboard", aba, key="Backspace")
    await rt.call("keyboard", aba, text="+" + numero)
    await asyncio.sleep(1)
    valor = re.sub(r"\D", "", str(await _js(rt, aba, ex.SCRIPT_VALOR_TELEFONE) or ""))
    if valor != numero:
        raise SemWhatsApp(f"o número não entrou certo no WhatsApp Web (ficou {valor or 'vazio'}, esperado {numero})")
    if await _js(rt, aba, ex.SCRIPT_AVANCAR) != "clicado":
        raise SemWhatsApp("não achei o botão Avançar/Next no WhatsApp Web")
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


async def _na_lista(rt, aba, ex) -> None:
    """WhatsApp Web on its main screen (a send?phone= page or another chat may be open; the list is always there)."""
    est = await _js(rt, aba, ex.SCRIPT_ESTADO) or {}
    if not (isinstance(est, dict) and est.get("logado")):
        await rt.call("navigate", aba, WEB)
        est = await _esperar(rt, aba, ex, lambda e: e.get("logado") or e.get("qr") or e.get("pede_numero"), 45)
        if not est.get("logado"):
            raise SemWhatsApp("o WhatsApp da pessoa não está conectado: chame acao \"conectar\"")


async def _abrir_titulo(rt, aba, ex, titulo: str) -> None:
    await _na_lista(rt, aba, ex)
    if await _js(rt, aba, ex.script_abrir_titulo(titulo)) != "clicado":
        raise SemWhatsApp(f"não achei a conversa «{titulo}» na lista do WhatsApp Web")
    for _ in range(10):
        await asyncio.sleep(1)
        if await _js(rt, aba, ex.SCRIPT_TITULO_ABERTO) == titulo:
            return
    raise SemWhatsApp(f"a conversa «{titulo}» não abriu no WhatsApp Web")


async def _nao_lidas(ex, login: str, nome: str, maximo: int, pular: set) -> list:
    """[(titulo, mensagens)] of the chats with unread messages (opening one marks it read on the phone too, so a chat
    whose draft waits for the person, `pular`, stays closed and unread until then)."""
    rt = await _runtime(ex, login, nome)
    aba = await _aba(rt)
    await _na_lista(rt, aba, ex)
    chats = [c for c in ((await _js(rt, aba, ex.SCRIPT_NAO_LIDAS)) or {}).get("chats") or [] if c["titulo"] not in pular]
    out = []
    for c in chats[:maximo]:
        try:
            await _abrir_titulo(rt, aba, ex, c["titulo"])
            await asyncio.sleep(1.5)
            r = await _js(rt, aba, ex.SCRIPT_MENSAGENS)
            out.append((c["titulo"], (r or {}).get("mensagens") or [] if isinstance(r, dict) else []))
        except SemWhatsApp as exc:
            print(f"conversas_externas: {login}: {exc}", flush=True)
    return out


async def _responder(ex, login: str, nome: str, p: dict, texto: str) -> list:
    """Send the approved `texto` in the chat of request `p`; refuses when the person already answered it themselves."""
    rt = await _runtime(ex, login, nome)
    aba = await _aba(rt)
    if p.get("telefone"):
        await _abrir_conversa(rt, aba, ex, p["telefone"])
    else:
        await _abrir_titulo(rt, aba, ex, p["titulo"])
    await asyncio.sleep(1.5)
    antes = ((await _js(rt, aba, ex.SCRIPT_MENSAGENS)) or {}).get("mensagens") or []
    ids = [m["id"] for m in antes]
    ultima = (p.get("recebidas") or [{}])[-1].get("id")
    if ultima in ids and any(m["de"] == "eu" for m in antes[ids.index(ultima) + 1:]):
        raise SemWhatsApp("você já respondeu essa conversa pelo celular; não mandei a sugestão")
    if await _js(rt, aba, ex.SCRIPT_CAIXA) != "foco":
        raise SemWhatsApp("a caixa de mensagem não estava vazia ou não apareceu; não mandei")
    for i, linha in enumerate(texto.split("\n")):
        if i:
            await rt.call("key_chord", aba, ["Shift", "Enter"])
        if linha:
            await rt.call("keyboard", aba, text=linha)
    await asyncio.sleep(0.5)
    r = await _js(rt, aba, ex.SCRIPT_ENVIAR)
    if r == "foco":
        await rt.call("keyboard", aba, key="Enter")
    elif r != "clicado":
        raise SemWhatsApp(f"não consegui enviar ({r})")
    inicio = " ".join(texto.split())[:25]
    for _ in range(8):
        await asyncio.sleep(1.5)
        lidas = ((await _js(rt, aba, ex.SCRIPT_MENSAGENS)) or {}).get("mensagens") or []
        if any(m["de"] == "eu" and m["id"] not in ids and inicio in " ".join(m["texto"].split()) for m in lidas[-5:]):
            return lidas
    raise SemWhatsApp("cliquei em enviar, mas a mensagem não apareceu na conversa: confira antes de mandar de novo")


async def _ler_historico(rt, aba, ex, titulo: str) -> list:
    """Open one chat and scroll back until no older messages come (or APRENDER_ROLAGENS times)."""
    await _abrir_titulo(rt, aba, ex, titulo)
    await asyncio.sleep(1.5)
    antes = -1
    for _ in range(ex.APRENDER_ROLAGENS):
        n = await _js(rt, aba, ex.SCRIPT_ROLAR_CIMA)
        if not isinstance(n, int) or n == antes:
            break
        antes = n
        await asyncio.sleep(2)
    r = await _js(rt, aba, ex.SCRIPT_HISTORICO)
    return (r or {}).get("mensagens") or [] if isinstance(r, dict) else []


async def aprender(ex, login: str, nome: str, excluir: list | None = None, maximo: int | None = None) -> list:
    """Read the person's recent chats to learn how they answer: [(titulo, mensagens)]. Chats with unread messages are
    left alone (opening marks them read) and so are the ones the person excluded; the lock is taken per chat, so the
    watcher and the ✅ buttons are not held for the whole reading."""
    async with trava(login):
        rt = await _runtime(ex, login, nome)
        aba = await _aba(rt)
        await _na_lista(rt, aba, ex)
        chats = ((await _js(rt, aba, ex.SCRIPT_CONVERSAS)) or {}).get("chats") or []
    alvo = [c["titulo"] for c in chats if not c.get("nao_lidas") and not ex._excluido(c["titulo"], excluir or [])]
    out = []
    for titulo in alvo[:maximo or ex.APRENDER_CONVERSAS]:
        async with trava(login):
            try:
                out.append((titulo, await _ler_historico(rt, aba, ex, titulo)))
            except SemWhatsApp as exc:
                print(f"conversas_externas: {login}: aprender {titulo}: {exc}", flush=True)
    return out


async def nao_lidas(ex, login: str, nome: str, maximo: int = 3, pular: set | None = None) -> list:
    async with trava(login):
        return await _nao_lidas(ex, login, nome, maximo, pular or set())


async def responder(ex, login: str, nome: str, p: dict, texto: str) -> list:
    async with trava(login):
        return await _responder(ex, login, nome, p, texto)


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

"""Tests of the portal (infra/vm/portal/portal.py, 23/10 Hermes migration, phase 6): the Segundo Cérebro, Painel,
Tarefas and Cofre pages outside Agent Zero, with the same logins (PBKDF2 in usuarios.json). Login and signed session;
nothing without it; a POST needs the portal header (no cross-site request); the same page markup of the plugins; the
APIs answer for the logged-in person only; read-only until the cutover; the Segundo Cérebro only for its owner through
the same gate of the A0. Run from the repository root: python3 infra/vm/tests/test_portal.py"""
import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

RAIZ = Path(__file__).resolve().parents[3]
PLUGINS = RAIZ / "infra" / "vm" / "plugins"
falhas = []


def checa(cond, msg):
    if not cond:
        falhas.append(msg)


tmp = Path(tempfile.mkdtemp(prefix="portal-"))
os.environ.update(PORTAL_PLUGINS=str(PLUGINS), PORTAL_SEGREDO=str(tmp / "segredo"), PORTAL_SO_LEITURA="1",
                  PORTAL_ESTADO_NEXT=str(tmp / "next"))
(tmp / "segredo").write_text("s" * 64)
spec = importlib.util.spec_from_file_location("portal_teste", RAIZ / "infra" / "vm" / "portal" / "portal.py")
pt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pt)
us = pt.usuarios()
us.ARQUIVO = tmp / "usuarios.json"
sal = b"12345678"


def h(senha):
    return hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, 1000).hex()


us.ARQUIVO.write_text(json.dumps({"usuarios": {
    "matheus": {"nome": "Matheus", "salt": sal.hex(), "iter": 1000, "hash": h("certa")},
    "ilia": {"nome": "Ilia", "salt": sal.hex(), "iter": 1000, "hash": h("dele")}}}))
cofres = []
cofre = types.ModuleType("c")
cofre.carregar = lambda login: {"IG_SENHA": "x"} if login == "matheus" else {"OUTRA": "y"}
cofre.descricoes = lambda login: {}
cofre.salvar = lambda *a: cofres.append(a)
painel = types.ModuleType("p")
painel.ler = lambda login: {"de": login}
painel.hora = lambda t: "10:00"
vivos = types.ModuleType("v")
vivos.listar = lambda login: [{"id": "1", "receita": "segredo", "atualizado": 1}]
pt.helper = lambda plugin, arq: {("cofre", "cofre"): cofre, ("painel", "painel"): painel, ("painel", "vivos"): vivos}[(plugin, arq)]


async def main():
    async with TestClient(TestServer(pt.app())) as c:
        r = await c.get("/painel", allow_redirects=False)
        checa(r.status == 302 and r.headers["Location"].startswith("/entrar"), "sem sessão: vai para o login")
        r = await c.post("/plugins/cofre/cofre", json={}, headers={"X-Portal": "1"})
        checa(r.status == 401, "API sem sessão: 401")
        r = await c.get('/entrar?volta="><script>alert(1)</script>')
        checa("<script>alert" not in await r.text(), "o 'volta' nunca vira HTML/script (XSS)")
        r = await c.post("/entrar", data={"login": "x", "senha": "y", "volta": '/a"><script>alert(1)</script>'},
                         allow_redirects=False)
        checa("<script>alert" not in await r.text(), "nem na resposta de senha errada")
        r = await c.post("/entrar", data={"login": "matheus", "senha": "errada", "volta": "/painel"}, allow_redirects=False)
        checa(r.status == 401, "senha errada não entra")
        r = await c.post("/entrar", data={"login": "matheus", "senha": "certa", "volta": "//mal.com"}, allow_redirects=False)
        checa(r.status == 302 and r.headers["Location"] == "/" and pt.COOKIE in r.cookies, "entra; 'volta' de fora vira /")
        checa(r.cookies[pt.COOKIE]["httponly"], "cookie HttpOnly")
        r = await c.get("/painel")
        texto = await r.text()
        checa(r.status == 200 and "sendJsonData('/plugins/painel/painel'" in texto and "x-data" in texto and "X-Portal" in texto,
              "a página é a do plugin, numa casca que fala com o portal")
        r = await c.post("/plugins/painel/painel", json={})
        checa(r.status == 403, "POST sem o cabeçalho do portal (outro site) é recusado")
        r = await c.post("/plugins/painel/painel", json={}, headers={"X-Portal": "1"})
        d = await r.json()
        checa(d["painel"] == {"de": "matheus"} and "receita" not in d["vivos"][0], f"painel do dono, sem a receita: {d}")
        r = await c.post("/plugins/cofre/cofre", json={"acao": "salvar", "nome": "X", "valor": "y"}, headers={"X-Portal": "1"})
        d = await r.json()
        checa(not d["ok"] and "só mostra" in d["erro"] and not cofres and d["nomes"] == ["IG_SENHA"],
              f"até a virada nada grava; só os nomes, nunca valores: {d}")
        r = await c.get("/segundo-cerebro/../../etc/passwd")
        checa(r.status in (404, 400), "caminho torto no Segundo Cérebro não passa")
        c.session.cookie_jar.clear()
        r = await c.get("/painel", allow_redirects=False, headers={"Cookie": f"{pt.COOKIE}=lixo.assinatura"})
        checa(r.status == 302, "cookie falsificado não vale")
        valido = pt.assinar("matheus")
        checa(pt.login_do_cookie(valido[:-1] + ("0" if valido[-1] != "0" else "1")) == "", "assinatura mexida não vale")
        r = await c.post("/entrar", data={"login": "ilia", "senha": "dele"}, allow_redirects=False)
        r = await c.post("/plugins/cofre/cofre", json={}, headers={"X-Portal": "1"})
        checa((await r.json())["nomes"] == ["OUTRA"], "cada um vê só o seu cofre")
        r = await c.get("/api/segundo-cerebro")
        checa(r.status == 403, f"o Segundo Cérebro é só do Matheus ({r.status})")
        r = await c.get("/")
        checa("Segundo Cérebro" not in await r.text(), "convidado nem vê o link")
        pt.CDP = "http://127.0.0.1:9"  # virada: o navegador do Hermes, só do dono
        r = await c.get("/navegador")
        checa(r.status == 403, f"o navegador do agente não é do convidado ({r.status})")
        r = await c.post("/api/navegador", json={"acao": "abas"}, headers={"X-Portal": "1"})
        checa(r.status == 403, "nem pela API")
        c.session.cookie_jar.clear()
        r = await c.post("/entrar", data={"login": "matheus", "senha": "certa"}, allow_redirects=False)
        r = await c.get("/")
        checa("/navegador" in await r.text(), "o dono vê o link do navegador depois da virada")
        r = await c.get("/navegador")
        texto = await r.text()
        checa(r.status == 200 and "pointer-events: none" in texto and '"segurar"' in texto and 'const TOKEN = ""' in texto,
              "a página do navegador (a do tela.html do A0: segurar, imagem sem ponteiro), sem token pela sessão")
        r = await c.post("/api/navegador", json={"acao": "abas"})
        checa(r.status == 403, "POST do navegador sem o cabeçalho do portal (outro site) é recusado")
        r = await c.post("/api/navegador", json={"acao": "rodar_js"}, headers={"X-Portal": "1"})
        checa(r.status in (400, 500, 502), "ação desconhecida não roda nada")
        await resolver_aqui(c)
        pt.CDP = ""
        r = await c.get("/navegador")
        checa(r.status == 403, "antes da virada (sem CDP) não há navegador no portal")
    checa(pt.login_do_cookie(pt.assinar("matheus", agora=1)) == "", "sessão vencida não vale")
    checa(pt.login_do_cookie(pt.assinar("fantasma")) == "", "login que saiu do usuarios.json não vale")


async def resolver_aqui(c):
    """O link assinado do "🖥️ Resolver aqui" (resolver_hermes.py): sem login, só o dono, vence, um "Terminei" por link."""
    tela = pt.tela_helper()
    pt.CHAVE_PONTE = tmp / "chave"
    pt.CHAVE_PONTE.write_text("k" * 40)
    chamadas, prontos, esperas = [], [], []

    async def cdp(aba, metodo, params=None):
        chamadas.append((aba, metodo, params or {}))
        if metodo == "Runtime.evaluate" and "innerWidth" in (params or {}).get("expression", ""):
            return {"result": {"value": [1000, 800]}}
        if metodo == "Page.captureScreenshot":
            return {"data": "QUJD"}
        return {}

    async def abas():
        return [{"id": "A1", "url": "https://ifood.com.br/login", "title": "iFood"}, {"id": "B2", "url": "https://x.com"}]

    async def cdp_http(caminho, metodo="GET"):
        chamadas.append(("http", caminho, metodo))
        return {"id": "NOVA"}

    async def dormir(s):
        esperas.append(s)

    pt._cdp, pt._cdp_abas, pt._cdp_http = cdp, abas, cdp_http
    pt._ponte_pronto = lambda login, sessao: prontos.append((login, sessao))
    pt.asyncio = types.SimpleNamespace(sleep=dormir, to_thread=asyncio.to_thread)
    c.session.cookie_jar.clear()
    bom = tela.assinar("tg-matheus", "matheus", "k" * 40)
    r = await c.get("/navegador", params={"t": bom, "aba": "A1"})
    texto = await r.text()
    checa(r.status == 200 and bom in texto and "no-store" in r.headers.get("Cache-Control", ""),
          f"o link do Telegram abre sem login ({r.status})")
    for nome, ruim in (("vencido", tela.assinar("tg-matheus", "matheus", "k" * 40, agora=1)),
                       ("de convidado", tela.assinar("tg-ilia", "ilia", "k" * 40)),
                       ("assinado com outro segredo", tela.assinar("tg-matheus", "matheus", "z" * 40)),
                       ("mexido", bom[:-2] + "xx")):
        r = await c.get("/navegador", params={"t": ruim})
        checa(r.status == 403, f"link {nome} não abre ({r.status})")
        r = await c.post("/api/navegador", json={"t": ruim, "acao": "abas"}, headers={"X-Portal": "1"})
        checa(r.status == 403, f"link {nome} não mexe pela API ({r.status})")
    r = await c.post("/api/navegador", json={"acao": "abas"}, headers={"X-Portal": "1"})
    checa(r.status == 403, f"sem link e sem login: nada ({r.status})")
    r = await c.post("/api/navegador", json={"t": bom, "acao": "abas"})
    checa(r.status in (401, 403), f"sem o cabeçalho do portal não passa nem com link ({r.status})")

    async def api(acao, **extra):
        r = await c.post("/api/navegador", json={"t": bom, "aba": "A1", "acao": acao, **extra}, headers={"X-Portal": "1"})
        return r.status, await r.json()

    st, d = await api("abas")
    checa(st == 200 and [a["id"] for a in d["abas"]] == ["A1", "B2"] and d["abas"][0]["titulo"] == "iFood", f"abas: {d}")
    st, d = await api("quadro")
    checa(d.get("imagem") == "QUJD", f"quadro: {d}")
    chamadas.clear()
    await api("toque", fx=0.5, fy=0.25)
    cliques = [p for a, m, p in chamadas if m == "Input.dispatchMouseEvent"]
    checa([p["type"] for p in cliques] == ["mouseMoved", "mousePressed", "mouseReleased"]
          and all(p["x"] == 500 and p["y"] == 200 for p in cliques) and cliques[0]["buttons"] == 0,
          f"toque = o ponteiro chega ao ponto e então clica, como o xpra do A0 (o Turnstile recusava clique sem movimento): {cliques}")
    checa(esperas[-2:] == [0.05, 0.08], f"toque com o tempo de um dedo entre chegar, apertar e soltar: {esperas}")
    chamadas.clear()
    await api("segurar", fx=0.1, fy=0.1, ms=60000)
    tipos = [p["type"] for a, m, p in chamadas if m == "Input.dispatchMouseEvent"]
    checa(tipos == ["mouseMoved", "mousePressed", "mouseReleased"] and esperas[-1] == 15.0,
          f"segurar aperta, espera (até 15 s) e solta: {tipos} {esperas}")
    await api("segurar", fx=0.1, fy=0.1, ms=4200)
    checa(esperas[-1] == 4.2, f"segura o tempo que ele segurou: {esperas}")
    chamadas.clear()
    await api("arrastar", pontos=[[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]])
    tipos = [p["type"] for a, m, p in chamadas if m == "Input.dispatchMouseEvent"]
    checa(tipos == ["mouseMoved", "mousePressed", "mouseMoved", "mouseMoved", "mouseReleased"], f"arrastar: {tipos}")
    chamadas.clear()
    await api("rolar", dy=0.5)
    checa(any(m == "Input.dispatchMouseEvent" and p["type"] == "mouseWheel" and p["deltaY"] == 400 for a, m, p in chamadas),
          f"rolar: {chamadas}")
    chamadas.clear()
    st, d = await api("abrir", url="https://exemplo.com", nova=True)
    checa(d.get("aba") == "NOVA" and chamadas[0][0] == "http" and chamadas[0][2] == "PUT", f"abrir nova aba: {d} {chamadas}")
    st, d = await api("abrir", url="file:///etc/passwd", nova=True)
    checa(st == 400, "nova aba só com https")
    chamadas.clear()
    await api("ativar", aba="B2")
    checa(chamadas and "/json/activate/B2" in chamadas[0][1], f"trocar de aba: {chamadas}")
    chamadas.clear()
    await api("abrir", url="javascript:alert(1)")
    checa(chamadas and chamadas[0][2]["url"].startswith("https://"), f"endereço vira https: {chamadas}")
    chamadas.clear()
    await api("texto", texto="oi")
    await api("tecla", tecla="Enter")
    checa([m for a, m, p in chamadas] == ["Input.insertText", "Input.dispatchKeyEvent", "Input.dispatchKeyEvent"],
          f"digitar e tecla: {chamadas}")
    st, d = await api("tecla", tecla="F12")
    checa(st == 400, "tecla fora da lista não vai")
    st, d = await api("pronto")
    st2, d2 = await api("pronto")
    checa(prontos == [("matheus", "tg-matheus")] and d2.get("repetido"), f"Terminei avisa a conversa uma vez: {prontos}")
    checa(pt.texto_pronto("matheus", "tg-matheus") == pt.PRONTO and "cron_x" in pt.texto_pronto("matheus", "cron_x"),
          "o aviso diz de qual sessão veio quando não é a do celular")
    teste = tela.assinar("tg-teste_hermes", "teste_hermes", "k" * 40)
    r = await c.get("/navegador", params={"t": teste})
    checa(r.status == 200, "o login de teste do operador abre (para conferir sem o celular do Matheus)")
    pt.asyncio = asyncio
    await c.post("/entrar", data={"login": "matheus", "senha": "certa"}, allow_redirects=False)


asyncio.run(main())
if falhas:
    raise SystemExit("test_portal: " + "; ".join(falhas))
print("test_portal: ok")

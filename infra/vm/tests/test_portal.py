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
    tipos = [p["type"] for p in cliques]
    checa(tipos == ["mouseMoved", "mouseMoved", "mousePressed", "mouseReleased"]
          and (cliques[0]["x"], cliques[0]["y"]) != (500, 200) and all(p["x"] == 500 and p["y"] == 200 for p in cliques[1:])
          and cliques[0]["buttons"] == 0 and "force" not in cliques[1],
          f"toque = o ponteiro chega ao ponto vindo de perto e então clica, como o xpra do A0: {cliques}")
    checa(cliques[2]["force"] == 0.5 and cliques[2]["buttons"] == 1 and "force" not in cliques[3],
          f"aperta com a pressão de um mouse de verdade (0,5; com 0 o Turnstile recusava o toque): {cliques}")
    checa(esperas[-3:] == [0.03, 0.05, 0.08], f"toque com o tempo de um dedo entre chegar, apertar e soltar: {esperas}")
    chamadas.clear()
    await api("toque", fx=0.5, fy=0.25)
    cliques = [p for a, m, p in chamadas if m == "Input.dispatchMouseEvent"]
    checa([p["type"] for p in cliques] == ["mouseMoved", "mousePressed", "mouseReleased"],
          f"o ponteiro já está ali: não anda de novo: {cliques}")
    chamadas.clear()
    await api("toque", fx=0.1, fy=0.1)
    cliques = [p for a, m, p in chamadas if m == "Input.dispatchMouseEvent"]
    checa((cliques[0]["x"], cliques[0]["y"]) == ((500 + 100) / 2, (200 + 80) / 2), f"parte de onde o ponteiro estava: {cliques}")
    chamadas.clear()
    await api("segurar", fx=0.1, fy=0.1, ms=60000)
    cliques = [p for a, m, p in chamadas if m == "Input.dispatchMouseEvent"]
    tipos = [p["type"] for p in cliques]
    checa(tipos == ["mouseMoved", "mousePressed", "mouseReleased"] and esperas[-1] == 15.0 and cliques[1]["force"] == 0.5,
          f"segurar aperta (pressão 0,5), espera (até 15 s) e solta: {tipos} {esperas}")
    await api("segurar", fx=0.1, fy=0.1, ms=4200)
    checa(esperas[-1] == 4.2, f"segura o tempo que ele segurou: {esperas}")
    chamadas.clear()
    await api("arrastar", pontos=[[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]])
    cliques = [p for a, m, p in chamadas if m == "Input.dispatchMouseEvent"]
    tipos = [p["type"] for p in cliques]
    checa(tipos == ["mouseMoved", "mousePressed", "mouseMoved", "mouseMoved", "mouseReleased"]
          and all(p.get("force") == 0.5 for p in cliques[1:4]), f"arrastar (com pressão enquanto apertado): {cliques}")
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
    # A tela do X (cdp_encaminhar.py /tela/*, como o xpra do A0): com ela no ar, quadro e mouse vão por ela, nunca CDP
    telas = []

    async def tela_x(caminho, dados):
        telas.append((caminho, dados))
        return {"imagem": "WFla", "largura": 1280, "altura": 813} if caminho == "quadro" else {"ok": True}

    antigo_tela, pt._tela = pt._tela, tela_x
    chamadas.clear()
    st, d = await api("quadro")
    checa(d.get("imagem") == "WFla" and telas[-1] == ("quadro", {"aba": "A1", "qualidade": 60})
          and not any(m == "Page.captureScreenshot" for a, m, p in chamadas), f"quadro pela tela do X: {d} {telas}")
    await api("toque", fx=0.5, fy=0.25)
    await api("segurar", fx=0.1, fy=0.2, ms=3000)
    await api("arrastar", pontos=[[0.1, 0.1], [0.2, 0.2]])
    await api("rolar", dy=0.5)
    checa([t[1]["acao"] for t in telas[1:]] == ["toque", "segurar", "arrastar", "rolar"] and telas[1][1]["fx"] == 0.5
          and telas[2][1]["ms"] == 3000 and telas[3][1]["pontos"] == [[0.1, 0.1], [0.2, 0.2]] and telas[4][1]["dy"] == 0.5
          and not any(m == "Input.dispatchMouseEvent" for a, m, p in chamadas),
          f"toque, segurar, arrastar e rolar como mouse de verdade do X (nenhum clique sintético do CDP): {telas} {chamadas}")
    r = await c.post("/api/navegador", json={"t": bom, "acao": "toque", "fx": 0.5, "fy": 0.5}, headers={"X-Portal": "1"})
    checa(telas[-1][1]["aba"] == "A1", f"sem aba: a da frente, também pela tela do X: {telas[-1]}")

    async def tela_fora(caminho, dados):
        return None

    pt._tela = tela_fora
    chamadas.clear()
    await api("toque", fx=0.5, fy=0.25)
    checa([p["type"] for a, m, p in chamadas if m == "Input.dispatchMouseEvent"][-2:] == ["mousePressed", "mouseReleased"],
          f"sem a tela do X (navegador antigo): o caminho do CDP: {chamadas}")
    pt._tela = antigo_tela
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

# cdp_encaminhar.py /tela/*: onde fica a página na tela do X e os comandos do xdotool de cada gesto (sem X)
spec = importlib.util.spec_from_file_location("teste_encaminhar", RAIZ / "infra" / "vm" / "hermes" / "cdp_encaminhar.py")
enc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enc)
checa(enc.area_da_pagina([0, 0, 1280, 900, 1280, 813]) == (0, 87, 1280, 813)
      and enc.area_da_pagina([22, 30, 1280, 900, 1272, 809]) == (26, 117, 1272, 809), "área da página na tela do X")
g = enc.gestos({"acao": "toque", "fx": 0.5, "fy": 0.5}, (0, 87, 1001, 801))
checa(g[0] == ["mousemove", "488", "496"] and g[2] == ["mousemove", "500", "487"] and ["mousedown", "1"] in g
      and g[-1] == ["mouseup", "1"] and g[g.index(["mousedown", "1"]) + 1] == ["sleep", "0.08"],
      f"toque: o ponteiro chega por perto, aperta e solta com o tempo de um dedo: {g}")
g = enc.gestos({"acao": "segurar", "fx": 0, "fy": 0, "ms": 60000}, (0, 87, 1001, 801))
checa(["sleep", "15.0"] in g and g[2] == ["mousemove", "0", "87"], f"segurar até 15 s no ponto: {g}")
g = enc.gestos({"acao": "arrastar", "pontos": [[0, 0], [1, 1]]}, (0, 0, 101, 101))
checa(g[0] == ["mousemove", "0", "0"] and ["mousemove", "100", "100"] in g and g[-1] == ["mouseup", "1"], f"arrastar: {g}")
g = enc.gestos({"acao": "rolar", "dy": -0.5}, (0, 0, 100, 800))
checa(g[1][-1] == "4" and g[1][2] == "4", f"rolar para cima: 4 cliques da roda: {g}")
try:
    enc.gestos({"acao": "apagar"}, (0, 0, 1, 1))
    checa(False, "ação desconhecida não vira comando")
except ValueError:
    pass
checa(not enc.TELA, "a tela do X só com TELA_X=1 (o repasse do adb segue só repasse)")
nav_sh = (RAIZ / "infra" / "vm" / "hermes" / "navegador.sh").read_text()
lanca = nav_sh.split("docker run", 1)[1]
checa("Xvfb :99" in lanca and "--headless" not in lanca and "TELA_X=1" in lanca and "DISPLAY=:99" in lanca
      and " xvfb xdotool " in (RAIZ / "infra" / "vm" / "hermes" / "imagem" / "Dockerfile").read_text(),
      "o navegador roda com tela num Xvfb e o repasse atende a tela do X, como no A0")
if falhas:
    raise SystemExit("test_portal: " + "; ".join(falhas))
print("test_portal: ok")

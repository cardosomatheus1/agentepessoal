"""Tests of the "🖥️ Resolver aqui" tool in Hermes (infra/vm/hermes/plugins/agentepessoal/resolver_hermes.py, the A0
navegador_visual): only the owner (and the operator's test logins), never a guest; the print of the chosen tab and a
Telegram web-app button with a signed 30-min link the portal accepts; no public address or bridge secret, no button.
Run from the repository root: python3 infra/vm/tests/test_resolver_hermes.py"""
import asyncio
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
P = RAIZ / "infra" / "vm" / "hermes" / "plugins" / "agentepessoal"
falhas = []


def checa(cond, msg):
    if not cond:
        falhas.append(msg)


def carregar(nome, caminho):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    m = importlib.util.module_from_spec(spec)
    sys.modules[nome] = m
    spec.loader.exec_module(m)
    return m


tela = carregar("teste_tela", RAIZ / "infra" / "vm" / "plugins" / "navegador_visual" / "helpers" / "tela.py")
r = carregar("teste_resolver", P / "resolver_hermes.py")
tmp = Path(tempfile.mkdtemp())
r.PRINTS = tmp / "prints"
SEGREDO = "k" * 40
tela_fake = types.SimpleNamespace(assinar=tela.assinar, segredo=lambda: SEGREDO)

pa = types.ModuleType("agentepessoal_ponte_a0")
pa.instancia = ""
pa.convidado_da_instancia = lambda: pa.instancia
pa.login_da_sessao = lambda s: pa.instancia or {"tg-matheus": "matheus", "tg-ilia": "ilia",
                                                "tg-teste_hermes": "teste_hermes"}.get(s, "matheus")
sys.modules["agentepessoal_ponte_a0"] = pa


class Navegador:
    def __init__(self):
        self.fotos = []

    async def call(self, metodo, *args, **kw):
        if metodo == "list":
            return {"browsers": [{"id": "A1", "currentUrl": "https://www.ifood.com.br/entrar"},
                                 {"id": "B2", "currentUrl": "https://portal.99food.com/login"}]}
        if metodo == "screenshot":
            self.fotos.append(args[0])
            return {"image": "QUJD"}
        raise AssertionError(metodo)


class Ponte:
    def __init__(self, erro=""):
        self.envios, self.erro = [], erro

    def enviar(self, *a):
        self.envios.append(a)
        return self.erro


REGISTRO = tmp / "browser_own_tabs.json"  # o do Hermes (patch abas_por_sessao): dono -> a aba dele
REGISTRO.write_text(json.dumps({"tg-matheus": {"target_id": "A1", "used": 1}, "tg-teste_hermes": {"target_id": "A1", "used": 1}}))


def rodar(args, sessao, ponte=None, base="https://agente.exemplo.com", nav=None, registro=REGISTRO):
    return asyncio.run(r.executar(args, sessao, navegador=nav or Navegador(), ponte=ponte or Ponte(), tela=tela_fake,
                                  base_url=base, registro=registro, quadro=lambda aba: ""))


# quem pode
checa(r.pode("matheus", "") and r.pode("teste_hermes", ""), "o dono e o login de teste podem")
checa(not r.pode("ilia", "") and not r.pode("matheus", "ilia") and not r.pode("ilia", "ilia"), "convidado nunca")

# a aba
abas = [{"id": "A1", "currentUrl": "https://a.com"}, {"id": "B2", "currentUrl": "https://b.com/x"}]
checa(r.escolher_aba(abas, "") is None and r.escolher_aba(abas, "", ["B2"])["id"] == "B2" and r.escolher_aba(abas, "B2")["id"] == "B2"
      and r.escolher_aba(abas, "b.com")["id"] == "B2" and r.escolher_aba(abas, "zzz") is None, "escolher a aba")

# o link: assinatura que o portal confere (tela.conferir), com sessão e login
url = r.link("https://agente.exemplo.com/", "tg-matheus", "matheus", "A1", SEGREDO, tela_fake)
token = url.split("t=", 1)[1].split("&", 1)[0]
dados = tela.conferir(token, SEGREDO)
checa(url.startswith("https://agente.exemplo.com/navegador?t=") and url.endswith("&aba=A1")
      and dados and dados["contexto"] == "tg-matheus" and dados["usuario"] == "matheus", f"link assinado: {url} {dados}")
checa(1700 < dados["expira"] - __import__("time").time() <= 1800, "vale 30 min")
checa(r.link("http://agente", "tg-matheus", "matheus", "A1", SEGREDO, tela_fake) == "", "sem https, sem link")
checa(r.link("https://a", "tg-matheus", "matheus", "A1", "", tela_fake) == "", "sem o segredo da ponte, sem link")
checa(r.link("https://a", "s.com.ponto", "matheus", "A1", SEGREDO, tela_fake) == "", "sessão com ponto quebraria o token")

# executar: o dono recebe print + botão
p = Ponte()
nav = Navegador()
texto = rodar({"pedido": "Entre na sua conta do 99Food", "aba": "99food"}, "tg-matheus", p, nav=nav)
checa(nav.fotos == ["B2"], f"print da aba pedida: {nav.fotos}")
checa(len(p.envios) == 1, f"uma mensagem: {p.envios}")
login, msg, arquivo, legenda, botoes, tipo, sempre, rotina, app = p.envios[0]
checa(login == "matheus" and "99Food" in msg and tipo == "urgente" and sempre, f"mensagem ao dono: {p.envios[0]}")
checa(Path(arquivo).read_bytes() == b"ABC" and str(arquivo).startswith(str(r.PRINTS)), "o print vai como arquivo")
checa(app["titulo"].endswith("Resolver aqui") and "&aba=B2" in app["url"]
      and tela.conferir(app["url"].split("t=", 1)[1].split("&")[0], SEGREDO)["contexto"] == "tg-matheus",
      f"o botão abre a aba nesta conversa: {app}")
checa("Terminei" in texto and "browser_snapshot" in texto and "Não tente resolver" in texto,
      f"o agente espera e confere depois: {texto}")

# login de teste: vai para a caixa de testes (a ponte cuida), assinado com o login dele
p = Ponte()
rodar({"pedido": "teste"}, "tg-teste_hermes", p)
checa(p.envios and p.envios[0][0] == "teste_hermes"
      and tela.conferir(p.envios[0][8]["url"].split("t=", 1)[1].split("&")[0], SEGREDO)["usuario"] == "teste_hermes",
      "login de teste recebe o botão dele")

# convidado: nunca (nem na conversa dele no Hermes do Matheus, nem no Hermes dele)
for sessao, instancia in (("tg-ilia", ""), ("tg-ilia", "ilia")):
    pa.instancia = instancia
    p = Ponte()
    texto = rodar({"pedido": "x"}, sessao, p)
    checa(texto.startswith("NÃO FEITO") and not p.envios, f"convidado não recebe ({instancia or 'na do Matheus'}): {texto}")
pa.instancia = ""

# sem endereço público, aba inexistente, pedido vazio, ponte fora
p = Ponte()
checa(rodar({"pedido": "x"}, "tg-matheus", p, base="").startswith("NÃO FEITO") and not p.envios, "sem endereço, nada vai")
checa("não achei essa aba" in rodar({"pedido": "x", "aba": "zzz"}, "tg-matheus"), "aba que não existe")
checa(rodar({"pedido": "  "}, "tg-matheus").startswith("NÃO FEITO"), "pedido vazio")
checa("não chegou" in rodar({"pedido": "x"}, "tg-matheus", Ponte("ponte fora")), "falha da ponte é dita")

# registrado no plugin, como ferramenta assíncrona
registros = []
r.registrar(types.SimpleNamespace(register_tool=lambda **k: registros.append(k)))
checa(registros and registros[0]["name"] == "resolver_aqui" and registros[0]["is_async"]
      and registros[0]["schema"]["parameters"]["required"] == ["pedido"], f"registro: {registros}")
checa('resolver.registrar(ctx)' in (P / "__init__.py").read_text(), "o plugin registra o resolver_aqui")
acesso = (P / "acesso_hermes.py").read_text()
checa('"resolver_aqui"' not in acesso, "o resolver_aqui não está entre o que o convidado pode")

# 23/10 (Matheus): o Hermes disse que a página do botão (no Telegram, com o nome do bot) "parece golpe", negou que
# webmail-seguro.com.br fosse da Locaweb e mexeu no próprio código no ar.
H = RAIZ / "infra" / "vm" / "hermes"
alma = (H / "SOUL.md").read_text()
skill = (H / "skills" / "login-sites-navegador" / "SKILL.md").read_text()
desc = r.ESQUEMA["description"]
checa("Luffy" in alma and "golpe" in alma and "Luffy" in desc and "golpe" in desc and "Luffy" in skill,
      "a persona, a ferramenta e a skill dizem que a página do botão (Luffy, no Telegram) é dele e não é golpe")
checa("webmail-seguro.com.br" in skill and "Locaweb" in skill and "raizconnect.com.br" in skill,
      "a skill de login sabe que webmail-seguro.com.br é o webmail da Locaweb (e-mail da raizconnect.com.br)")
checa("ressemear: resolver-aqui-3" in skill, "a skill pede ressemeadura (a cópia no Hermes recebe o texto novo)")
checa("Nunca mude o seu próprio código" in alma and "se reinicie" in alma and "operador" in alma,
      "regra dura: nunca mexer no próprio código/containers nem se reiniciar; quem muda é o operador")

# Sem `aba`: a aba DESTA conversa (cada conversa/rotina tem a sua), nunca a primeira da lista (a de outra conversa).
reg2 = tmp / "abas2.json"
reg2.write_text(json.dumps({"tg-ilia": {"target_id": "A1", "used": 9}, "tgp1-matheus": {"target_id": "A1", "used": 9},
                            "tg-matheus": {"target_id": "SUMIU", "used": 5}, "tg-matheus#s2": {"target_id": "B2", "used": 3},
                            "cron:job7": {"target_id": "B2", "used": 1}}))
checa(r.aba_da_conversa("tg-matheus", reg2) == ["SUMIU", "B2"] and r.aba_da_conversa("cron:job7:run3", reg2) == ["B2"]
      and r.aba_da_conversa("tgp2-matheus", reg2) == [] and r.aba_da_conversa("x", tmp / "nao-existe.json") == [],
      "as abas da conversa (a própria e a segunda dela; a rotina pela do job; nunca a de outra conversa)")
nav = Navegador()
rodar({"pedido": "Entre no 99Food"}, "tg-matheus", Ponte(), nav=nav, registro=reg2)
checa(nav.fotos == ["B2"], f"sem aba: a desta conversa que ainda está aberta, não a primeira da lista: {nav.fotos}")
nav, p = Navegador(), Ponte()
texto = rodar({"pedido": "x"}, "tgp2-matheus", p, nav=nav, registro=reg2)
checa(texto.startswith("NÃO FEITO") and "browser_navigate" in texto and not p.envios and not nav.fotos,
      f"conversa sem aba própria: não manda a aba de outra conversa: {texto}")

# O print vem da tela do X (com tela, o print por CDP de página com Cloudflare trava); sem ela, o do CDP
nav, p = Navegador(), Ponte()
asyncio.run(r.executar({"pedido": "x"}, "tg-matheus", navegador=nav, ponte=p, tela=tela_fake, base_url="https://agente.exemplo.com",
                       registro=REGISTRO, quadro=lambda aba: "WFla" if aba == "A1" else ""))
checa(nav.fotos == [] and p.envios and Path(p.envios[0][2]).read_bytes() == b"XYZ", f"print pela tela do X: {nav.fotos} {p.envios[:1]}")
checa(r.quadro_x("A1", "") == "" and r.quadro_x("A1", "http://127.0.0.1:9") == "", "sem a tela do X: vazio (vale o CDP)")

# O código do navegador da oficial com os patches (o que o Hermes tinha feito no ar, agora revisado e no git):
img = H / "imagem"
df = (img / "Dockerfile").read_text()
patches = sorted((img / "patches").glob("*.patch"))
cf = (img / "patches" / "cloudflare.patch").read_text()
checa({p.name for p in patches} == {"cloudflare.patch", "abas_por_sessao.patch"} and "git apply -p1" in df
      and "|| exit 1" in df and "! grep -q '\"Runtime.enable\"'" in df, f"patches aplicados no build, que para se falham: {patches}")
checa('-        await self._cdp("Runtime.enable", session_id=session_id, timeout=timeout)' in cf
      and "challenges\\.cloudflare\\.com" in cf and "__hermesDialogBridgeInstalled\", {value: true, enumerable: false}" in cf,
      "Turnstile: sem Runtime ligado em cada frame e sem trocar alert/confirm/prompt no frame do desafio")
subir = (H / "subir.sh").read_text()
checa("cat Dockerfile patches/*.patch | sha256sum" in subir, "o rótulo da imagem muda quando um patch muda")

if falhas:
    raise SystemExit("test_resolver_hermes: " + "; ".join(falhas))
print("test_resolver_hermes: ok")

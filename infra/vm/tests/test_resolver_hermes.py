"""Tests of the "🖥️ Resolver aqui" tool in Hermes (infra/vm/hermes/plugins/agentepessoal/resolver_hermes.py, the A0
navegador_visual): only the owner (and the operator's test logins), never a guest; the print of the chosen tab and a
Telegram web-app button with a signed 30-min link the portal accepts; no public address or bridge secret, no button.
Run from the repository root: python3 infra/vm/tests/test_resolver_hermes.py"""
import asyncio
import importlib.util
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


def rodar(args, sessao, ponte=None, base="https://agente.exemplo.com", nav=None):
    return asyncio.run(r.executar(args, sessao, navegador=nav or Navegador(), ponte=ponte or Ponte(), tela=tela_fake,
                                  base_url=base))


# quem pode
checa(r.pode("matheus", "") and r.pode("teste_hermes", ""), "o dono e o login de teste podem")
checa(not r.pode("ilia", "") and not r.pode("matheus", "ilia") and not r.pode("ilia", "ilia"), "convidado nunca")

# a aba
abas = [{"id": "A1", "currentUrl": "https://a.com"}, {"id": "B2", "currentUrl": "https://b.com/x"}]
checa(r.escolher_aba(abas, "")["id"] == "A1" and r.escolher_aba(abas, "B2")["id"] == "B2"
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

if falhas:
    raise SystemExit("test_resolver_hermes: " + "; ".join(falhas))
print("test_resolver_hermes: ok")

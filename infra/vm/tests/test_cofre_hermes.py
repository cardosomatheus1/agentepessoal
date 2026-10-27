"""Tests of the vault inside the Hermes (infra/vm/hermes/plugins/agentepessoal/cofre_hermes.py, 23/10 migration):
an acting tool gets the owner's value and the result comes back masked with the notice; any other tool gets only the
name; a missing name is an error naming the ones there are; nothing from the vault reaches the model (request and tool
result); the names (never the values) go into the first message and again only when the list changes. Run from the
repository root: python3 infra/vm/tests/test_cofre_hermes.py"""
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


tmp = Path(tempfile.mkdtemp())
ponte = types.ModuleType("agentepessoal_ponte_a0")
mapa = {"s-ilia": "teste_ilia", "s1": "teste_matheus", "s9": "teste_matheus"}
ponte.login_mapeado = lambda s: mapa.get(s, "")
sys.modules["agentepessoal_ponte_a0"] = ponte
cf = carregar("teste_cofre_hermes", P / "cofre_hermes.py")
cf.PLUGINS = RAIZ / "infra" / "vm" / "plugins"
helper = cf.cofre()
helper.PASTA = tmp / "segredos"
helper.salvar("teste_matheus", "IG_SENHA", "senhaForte123")
helper.salvar("teste_ilia", "OUTRA", "valorDaIlia9")
livro = []
lc = cf._livro_cofre()
lc.registrar_usos = lambda registro, login, ferramenta, nomes, ultimos, ctx_id="", agora=None: livro.append(
    (login, ferramenta, list(nomes)))

visto = {}


def rodar(ferramenta, args, sessao="s1", devolve=None):
    def proximo(a):
        visto["args"] = a
        return devolve if devolve is not None else f"ok {json.dumps(a)}"
    return cf.executar(tool_name=ferramenta, args=args, next_call=proximo, session_id=sessao)


r = rodar("browser_type", {"ref": "@e3", "text": "§§secret(IG_SENHA)"}, devolve="digitado senhaForte123 no campo")
checa(visto["args"]["text"] == "senhaForte123", "ferramenta que age recebe o valor real")
checa("senhaForte123" not in r and "§§secret(IG_SENHA)" in r, "o resultado volta mascarado")
checa("✅ Cofre: o valor real de IG_SENHA (13 caracteres)" in r, "o aviso diz que o valor entrou")
checa(livro == [("teste_matheus", "browser_type", ["IG_SENHA"])], "o uso entra no livro, só o nome")

r = rodar("whatsapp_enviar", {"texto": "a senha é §§secret(IG_SENHA)"})
checa(visto["args"]["texto"] == "a senha é IG_SENHA", "ferramenta de texto recebe só o nome, nunca o valor")
checa(len(livro) == 1, "texto para gente não conta como uso")

visto.clear()
r = rodar("terminal", {"command": "login §§secret(NAO_TEM)"})
checa("NAO_TEM não está no cofre" in r and "IG_SENHA" in r, "nome que falta: erro com os nomes que há")
checa("args" not in visto, "com nome faltando, a ferramenta não roda")

visto.clear()
rodar("terminal", {"command": "login §§secret(OUTRA)"})
checa("args" not in visto, "o cofre de outra pessoa não vale nesta conversa")
visto.clear()
r = rodar("browser_type", {"text": "§§secret(IG_SENHA)"}, sessao="sub-tarefa-sem-dono")
checa("args" not in visto and "não está ligada a uma pessoa" in r,
      "sessão sem dono não recebe senha de ninguém (nem do Matheus)")
checa(cf.contexto_nomes(session_id="sub-tarefa-sem-dono", is_first_turn=True) is None, "nem a lista de nomes")

helper.salvar("teste_matheus", "ASPAS", 'ab"c\\dé\nfg')
r = rodar("terminal", {"command": "x"}, devolve=json.dumps({"output": 'senha: ab"c\\dé\nfg'}))
checa("ab" not in r.replace("§§secret(ASPAS)", ""), f"valor escapado no JSON volta mascarado: {r}")
r = rodar("terminal", {"command": "x"}, devolve=json.dumps({"output": 'ab"c\\dé\nfg'}, ensure_ascii=False))
checa("§§secret(ASPAS)" in r, "também com acento sem escape")
interno = json.dumps({"ASPAS": 'ab"c\\dé\nfg'})
r = rodar("read_file", {"path": "segredos/x.json"}, devolve=json.dumps({"content": interno}))
checa("§§secret(ASPAS)" in r and "dé" not in r and "d\\u00e9" not in r, f"JSON dentro de JSON (2 níveis) volta mascarado: {r}")
helper.salvar("teste_ilia", "IG_SENHA", "senhaDaIlia55")
r = rodar("browser_type", {"text": "§§secret(IG_SENHA)"}, devolve="eco senhaForte123 e senhaDaIlia55")
checa("senhaForte123" not in r and "senhaDaIlia55" not in r, f"mesmo nome em dois cofres: os dois mascarados: {r}")
r = rodar("read_file", {"path": "x"}, sessao="sub-tarefa-sem-dono", devolve="vi senhaForte123 e valorDaIlia9")
checa("senhaForte123" not in r and "valorDaIlia9" not in r, "a máscara vale em qualquer sessão, com todos os cofres")
r = rodar("terminal", {"command": "login §§secret(OUTRA)"}, sessao="s-ilia")
checa(visto["args"]["command"] == "login valorDaIlia9", "cada conversa usa o cofre do seu dono")

r = rodar("read_file", {"path": "x"}, devolve="conteúdo com senhaForte123 dentro")
checa(r == "conteúdo com §§secret(IG_SENHA) dentro", "qualquer resultado com valor do cofre volta mascarado")
checa(cf.resultado_mascarado(tool_name="t", result="vi senhaForte123", session_id="s1") == "vi §§secret(IG_SENHA)",
      "segunda trava: transform_tool_result mascara")
checa(cf.resultado_mascarado(tool_name="t", result="nada", session_id="s1") is None, "sem valor, não mexe")

pedido = {"model": "m", "system": [{"text": "x"}], "messages": [
    {"role": "user", "content": [{"type": "text", "text": "minha senha é senhaForte123"}]}]}
novo = cf.pedido_mascarado(request=pedido, session_id="s1")
checa(novo and "senhaForte123" not in json.dumps(novo["request"]) and "§§secret(IG_SENHA)" in json.dumps(novo["request"], ensure_ascii=False),
      "senha colada na conversa não chega ao modelo")
checa("senhaForte123" in json.dumps(pedido), "o pedido original não é alterado no lugar")
checa(cf.pedido_mascarado(request={"messages": [{"role": "user", "content": "oi"}]}, session_id="s1") is None,
      "sem valor, o pedido segue igual")

c1 = cf.contexto_nomes(session_id="s9", is_first_turn=True)
checa(c1 and "IG_SENHA" in c1["context"] and "senhaForte123" not in c1["context"], "nomes no início, nunca valores")
checa(cf.contexto_nomes(session_id="s9", is_first_turn=False) is None, "lista igual: não repete a cada mensagem")
helper.salvar("teste_matheus", "NOVA", "outroValor77")
c2 = cf.contexto_nomes(session_id="s9", is_first_turn=False)
checa(c2 and "NOVA" in c2["context"], "lista mudou: avisa de novo")

# 27/10: dica junto do erro de ref do navegador, no mesmo gancho, depois da máscara
dicas = carregar("teste_dicas_hermes", P / "dicas_hermes.py")
dicas.registrar(cf); dicas.registrar(cf)
checa(cf.DEPOIS.count(dicas.dica) == 1, "a dica entra uma vez só")
r = cf.resultado_mascarado(tool_name="browser_click", result='{"error": "Unknown ref: e42"} senhaForte123', session_id="s1")
checa(r and "browser_snapshot` agora" in r and "e42" in r and "senhaForte123" not in r, f"ref que sumiu: dica e máscara ({r})")
checa(cf.resultado_mascarado(tool_name="browser_click", result=r, session_id="s1") is None, "a dica não se repete")
checa(cf.resultado_mascarado(tool_name="terminal", result="Unknown ref: e1", session_id="s1") is None, "só no navegador")
cf.DEPOIS.append(lambda n, t: 1 / 0)
checa("§§secret(IG_SENHA)" in (cf.resultado_mascarado(tool_name="x", result="v senhaForte123", session_id="s1") or ""),
      "uma dica com erro não derruba a máscara")
cf.DEPOIS.pop()

if falhas:
    print("test_cofre_hermes: FALHOU\n- " + "\n- ".join(falhas))
    sys.exit(1)
print("test_cofre_hermes: ok")

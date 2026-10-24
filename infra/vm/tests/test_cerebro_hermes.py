"""Tests of cerebro_hermes (infra/vm/hermes/plugins/agentepessoal), 24/10 (Matheus: "Me diz pra que serve segundo
cérebro então? Ou não tá preenchendo ele ou não tá buscando informações"): every turn of a phone conversation goes to
the Segundo Cérebro's queue and the anotação automática records it (the A0's monologue_end capture, which the migration
left behind); every turn carries what of the Pasta the conversation does not have yet (rules, open Assuntos with where
they stopped, his to-dos, notes linked to his message, the long task's Assunto), again after a summary; each finished
step of a long task moves its Assunto by itself; a teste_* login uses only its own decisions and to-dos; the profile
and decisions come back after a summary. Real helpers on a temporary Pasta, a fake model.
Run from the repository root: python3 infra/vm/tests/test_cerebro_hermes.py"""
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
P = RAIZ / "infra" / "vm" / "hermes" / "plugins" / "agentepessoal"
PLUGINS = RAIZ / "infra" / "vm" / "plugins"
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


tmp = Path(tempfile.mkdtemp(prefix="cerebro-hermes-"))
ponte = types.ModuleType("agentepessoal_ponte_a0")
MAPA = {"tg-teste_hermes": "teste_hermes", "tg-teste_hermes-20261024130000": "teste_hermes", "tg-ilia": "ilia"}
ponte.login_da_sessao = lambda s: MAPA.get(s, "matheus")
ponte.convidado_da_instancia = lambda: ""
ponte.SESSOES = tmp / "sessoes.json"
sys.modules["agentepessoal_ponte_a0"] = ponte

# the real helpers on a temporary Pasta (as plugins/cerebro/tests/suite.py does)
for k in [k for k in sys.modules if k.startswith(("cerebro_", "memoria_pessoal_", "fios_soltos_helper"))]:
    sys.modules.pop(k, None)
mods = carregar("cerebro_modulos", PLUGINS / "cerebro" / "helpers" / "modulos.py")
pa = mods.m("pasta")
pa.RAIZ = tmp / "pasta"
pa.estrutura()
(pa.RAIZ / pa.MARCA_MIGRADO).write_text("{}")
mods.m("decisoes").PASTA = tmp / "decisoes"
mods.m("fios").PASTA = tmp / "fios"
assuntos = mods.m("assuntos")
trabalho = mods.m("trabalho")

cb = carregar("agentepessoal_cerebro", P / "cerebro_hermes.py")
cb.PLUGINS = PLUGINS
cb.ENTRADA = tmp / "entrada"

# ---- 1. which sessions are someone's phone conversation
checa(cb.login_da_conversa("tg-matheus") == "matheus", "tg-matheus é a conversa do Matheus")
checa(cb.login_da_conversa("tg-teste_hermes-20261024130000") == "teste_hermes", "/nova do login de teste")
checa(cb.login_da_conversa("tgp2-matheus") == "matheus", "conversa paralela")
for s in ("api-123", "cron_abc_20261024_100000", "", "tg-outro"):
    checa(cb.login_da_conversa(s) == "", f"{s!r} não é conversa de ninguém (sem dono cai no Matheus: nunca anotar)")

# ---- 2. write: each turn goes to the queue
cb.anotar(session_id="tg-matheus", user_message="Decidi que nos testes da Raiz a conta é sempre matheus@raizconnect.com.br",
          assistant_response="Combinado, sigo com essa conta.")
arqs = sorted(cb.ENTRADA.glob("*.json"))
checa(len(arqs) == 1, f"um arquivo na fila por turno ({arqs})")
d = json.loads(arqs[0].read_text())
checa(d["login"] == "matheus" and d["dele"] == ["Decidi que nos testes da Raiz a conta é sempre matheus@raizconnect.com.br"]
      and d["relato"] == "Combinado, sigo com essa conta." and d["origem"] == "conversa tg-matheus", f"conteúdo: {d}")
arqs[0].unlink()
vigia = "[Aviso automático do vigia de tarefas: a tarefa longa 1023-2315-7a8d parou no meio]"
cb.anotar(session_id="tg-matheus", user_message=vigia, assistant_response="Passo 16 feito: Pessoas cadastradas. " * 8)
d = json.loads(next(cb.ENTRADA.glob("*.json")).read_text())
checa(d["dele"] == [] and d["relato"].startswith(vigia), "aviso do vigia não é palavra dele: vai como relato")
next(cb.ENTRADA.glob("*.json")).unlink()
cb.anotar(session_id="tg-matheus", user_message="(Operador) Fatos conferidos: a conta do teste é a de 23/10",
          assistant_response="ok")
d = json.loads(next(cb.ENTRADA.glob("*.json")).read_text())
checa(d["dele"] == [] and "Fatos conferidos" in d["relato"], "mensagem do operador vai como relato")
next(cb.ENTRADA.glob("*.json")).unlink()
cb.anotar(session_id="tg-matheus", user_message="", assistant_response="ok")
cb.anotar(session_id="api-1", user_message="Decidi X Y Z de vez", assistant_response="ok")
cb.anotar(session_id="tg-ilia", user_message="Decidi X Y Z de vez", assistant_response="ok")
cb.anotar(session_id="cron_abc_20261024_100000", user_message="rotina", assistant_response="x" * 500)
checa(not list(cb.ENTRADA.glob("*.json")), "nada: turno vazio, teste da API, convidado no principal, rotina")
ponte.convidado_da_instancia = lambda: "ilia"
cb.anotar(session_id="tg-matheus", user_message="Decidi X Y Z de vez", assistant_response="ok")
checa(not list(cb.ENTRADA.glob("*.json")), "no Hermes de um convidado a fila não é usada (o relógio de lá não lê)")
ponte.convidado_da_instancia = lambda: ""
cb.ENTRADA = Path("/proc/nao-da")
checa(cb.anotar(session_id="tg-matheus", user_message="Decidi isso", assistant_response="ok") is None,
      "fila fora do ar não derruba a conversa")
cb.ENTRADA = tmp / "entrada"

# ---- 3. the queue is read by the anotação automática (cerebro/helpers/trabalho.py), owner and test login
frente = assuntos.registrar("Teste de cliente novo na Raiz conta TESTE Luffy", onde_parou="cadastro feito", area="raiz")
cb.anotar(session_id="tg-matheus", user_message="Vc cadastrou no matheus@raizconnect.com.br, não no agente@",
          assistant_response="Corrigi: a conta do teste é matheus@raizconnect.com.br, criada em 23/10 17:58.")
cb.anotar(session_id="tg-teste_hermes",
          user_message="Decidi: nos testes da Raiz a conta de teste é sempre qa.luffy@raizconnect.com.br",
          assistant_response="Anotado.")


def modelo(pedido):
    if "qa.luffy" in pedido:
        checa("Teste de cliente novo" not in pedido, "o login de teste não vê os Assuntos do Matheus")
        return json.dumps({"decisoes": [{"tema": "raiz.conta-teste", "decisao": "Conta de teste da Raiz: qa.luffy@raizconnect.com.br",
                                         "tipo": "decisao", "area": "raiz",
                                         "citacao": "nos testes da Raiz a conta de teste é sempre qa.luffy@raizconnect.com.br"}],
                           "assuntos": [{"id": frente["id"], "onde_parou": "x", "citacao": "nos testes da Raiz a conta de teste"}]})
    checa("Teste de cliente novo" in pedido, "o Matheus: os Assuntos abertos vão ao modelo")
    return json.dumps({"assuntos": [{"id": frente["id"], "onde_parou": "conta do teste: matheus@raizconnect.com.br (23/10 17:58)",
                                     "citacao": "a conta do teste é matheus@raizconnect.com.br"}]})


avisos = []
r = trabalho.processar(mods, cb.ENTRADA, chamar=modelo, avisar=lambda login, linha: avisos.append((login, linha)))
checa(len(r) == 2 and all("erro" not in x for x in r), f"os dois turnos anotados: {r}")
checa(assuntos.achar(assuntos.todos(), frente["id"])["onde_parou"].startswith("conta do teste: matheus@"),
      "o relato do agente move o onde parou do assunto")
dec_teste = mods.m("decisoes").ativas("teste_hermes")
checa(len(dec_teste) == 1 and "qa.luffy" in dec_teste[0]["valor"] and dec_teste[0]["origem"] == "conversa tg-teste_hermes",
      f"a decisão do login de teste fica com ele: {dec_teste}")
checa(not any("qa.luffy" in str(a.get("onde_parou")) for a in assuntos.todos()), "e nunca nos Assuntos do Matheus")
checa({a[0] for a in avisos} == {"matheus", "teste_hermes"} and all(a[1].startswith("📌 Anotei") for a in avisos),
      f"cada um recebe o seu 📌 Anotei: {avisos}")

# ---- 4. read: what the conversation does not have yet
mods.m("fios").mesclar("matheus", [{"titulo": "Mandar o certificado A1 da Raiz", "dono": "você", "area": "raiz"}])
outra = assuntos.registrar("Cloudflare no navegador do Hermes", onde_parou="resolvido em 24/10: o webmail abre", area="agente")
c1 = cb.contexto(session_id="tg-matheus", user_message="E a conta do teste da Raiz, qual é?", conversation_history=[])
texto1 = (c1 or {}).get("context", "")
checa(cb.MARCA in texto1 and "Assuntos em andamento" in texto1 and "matheus@raizconnect.com.br" in texto1
      and "resolvido em 24/10" in texto1 and "certificado A1" in texto1, f"1º turno: regras, assuntos, pendências: {texto1[:900]}")
hist = [{"role": "user", "content": "E a conta do teste da Raiz, qual é?", "api_content": "E a conta…\n\n" + texto1},
        {"role": "assistant", "content": "É a matheus@raizconnect.com.br."}]
c2 = cb.contexto(session_id="tg-matheus", user_message="ok, segue", conversation_history=hist)
checa(c2 is None, f"nada novo: nada se repete ({c2})")
assuntos.atualizar(outra["id"], onde_parou="voltou a falhar às 15h: Cloudflare pede captcha de novo")
c3 = (cb.contexto(session_id="tg-matheus", user_message="ok, segue", conversation_history=hist) or {}).get("context", "")
checa("voltou a falhar às 15h" in c3 and cb.MARCA not in c3 and "Teste de cliente novo" not in c3,
      f"só o assunto que mudou desde a última vez: {c3}")
resumo = [{"role": "user", "content": "[Resumo da conversa até aqui: testes da Raiz…]"}]
c4 = (cb.contexto(session_id="tg-matheus", user_message="continua", conversation_history=resumo) or {}).get("context", "")
checa(cb.MARCA in c4 and "Teste de cliente novo" in c4, "depois de um resumo da conversa, tudo volta")
mods.m("decisoes").registrar("matheus", "raiz.preco-setup", "Setup da Raiz custa R$ 497", citacao="setup de 497",
                             area="raiz")
c5 = (cb.contexto(session_id="tg-matheus", user_message="quanto é o setup da Raiz mesmo?", conversation_history=hist)
      or {}).get("context", "")
checa("R$ 497" in c5 or "preco-setup" in c5, f"a nota ligada ao que ele escreveu vem junto, sem ele pedir: {c5}")
checa(cb.contexto(session_id="api-9", user_message="quanto é o setup?", conversation_history=[]) is None,
      "sessão que não é conversa de ninguém: nada")

# test login: its own decisions, never the owner's Pasta
c6 = (cb.contexto(session_id="tg-teste_hermes-20261024130000", user_message="Qual conta de teste eu uso nos testes da Raiz?",
                  conversation_history=[]) or {}).get("context", "")
checa("qa.luffy@raizconnect.com.br" in c6 and cb.MARCA in c6, f"sessão NOVA do teste: a decisão anotada volta sozinha: {c6}")
checa("Teste de cliente novo" not in c6 and "certificado A1" not in c6 and "R$ 497" not in c6,
      "o login de teste nunca vê o que é do Matheus")

# ---- 5. long tasks: each finished step moves its Assunto by itself
t = carregar("agentepessoal_tarefas", P / "tarefas_hermes.py")
t.RAIZ = tmp / "tarefas"
t.VIVAS = tmp / "vivas"
t.enviar = lambda *a, **k: ""
t.andamento = lambda *a, **k: ""
plano = t.criar("matheus", "Teste E2E da Raiz como cliente novo", "testa tudo", ["Cadastro", "Estoque", "Relatório"],
                "tg-matheus", agora=1_800_000_000.0)
ligado = plano.get("assunto")
checa(ligado and assuntos.achar(assuntos.todos(), ligado), f"tarefa nova abre (ou reaproveita) o assunto dela: {plano}")
t.mudar_passo("matheus", plano["id"], 1, "fazendo")
t.mudar_passo("matheus", plano["id"], 1, "feito", resultado="Conta criada: matheus@raizconnect.com.br (empresa TESTE Luffy)")
a = assuntos.achar(assuntos.todos(), ligado)
checa("1/3 passos feitos" in a["onde_parou"] and "matheus@raizconnect.com.br" in a["onde_parou"]
      and "Próximo: passo 2" in a["onde_parou"], f"passo feito: o onde parou muda sozinho: {a['onde_parou']}")
t.mudar_passo("matheus", plano["id"], 2, "esperando_matheus", pergunta="Qual CNPJ uso no cadastro fiscal?")
a = assuntos.achar(assuntos.todos(), ligado)
checa("esperando ele" in a["onde_parou"] and "CNPJ" in a["onde_parou"], f"esperando ele também: {a['onde_parou']}")
checa(sum("matheus@raizconnect" in h.get("nota", "") for h in a["historico"]) >= 1, "o passo anterior fica no histórico")
c7 = (cb.contexto(session_id="tg-matheus", user_message="como está o teste?", conversation_history=hist) or {}).get("context", "")
checa(f"Tarefa longa {plano['id']}" in c7 and "Conta criada: matheus@raizconnect.com.br" in c7,
      f"o que a tarefa já sabe vai com a mensagem (a conta usada não se perde): {c7}")
t.mudar_passo("matheus", plano["id"], 2, "falhou", erro="sem CNPJ")
t.mudar_passo("matheus", plano["id"], 3, "feito", resultado="Relatório pronto")
t.concluir("matheus", plano["id"], "Cadastro e relatório feitos; fiscal sem CNPJ.", enviar_fn=lambda *a, **k: "")
checa(assuntos.achar(assuntos.todos(), ligado)["onde_parou"].startswith(f"Tarefa {plano['id']} entregue"),
      "tarefa entregue: o assunto diz")
existente = assuntos.registrar("Integração 99Food", onde_parou="esperando a 99", area="raiz")
p2 = t.criar("matheus", "Homologar a 99Food", "faz", ["a", "b"], "tg-matheus", assunto=existente["id"])
checa(p2["assunto"] == existente["id"], "tarefa_iniciar com `assunto`: liga ao que já existe")
p3 = t.criar("teste_hermes", "Teste do login de teste", "faz", ["a", "b"], "tg-teste_hermes")
checa(not p3.get("assunto") and not any(x["titulo"] == "Teste do login de teste" for x in assuntos.todos()),
      "login de teste: nada nos Assuntos do Matheus")
t.mudar_passo("teste_hermes", p3["id"], 1, "feito", resultado="ok")  # sem assunto: segue normal
velho = t.criar("matheus", "Tarefa antiga sem assunto", "faz", ["a", "b"], "tg-matheus")
sys.modules.pop("agentepessoal_cerebro")
semc = t.criar("matheus", "Sem o plugin do cérebro", "faz", ["a", "b"], "tg-matheus")
checa(not semc.get("assunto"), "sem o cerebro_hermes a tarefa abre igual")
sys.modules["agentepessoal_cerebro"] = cb
try:
    t.ligar_assunto("matheus", velho["id"], "zzzzzz", por="operador: teste")
    checa(False, "assunto que não existe não liga")
except ValueError:
    pass
checa(t.ligar_assunto("matheus", velho["id"], existente["id"], por="operador: teste") == existente["id"]
      and json.loads((t.pasta("matheus", velho["id"]) / "plano.json").read_text())["assunto"] == existente["id"],
      "o operador liga uma tarefa aberta a um assunto (pelo helper, com o motivo no diário)")
checa("assunto" in t.ESQUEMAS["tarefa_iniciar"]["parameters"]["properties"], "tarefa_iniciar aceita o assunto")

# ---- 6. profile and decisions come back after a summary (contexto_hermes)
cx = carregar("teste_contexto_hermes2", P / "contexto_hermes.py")
cx.PLUGINS = PLUGINS
dec = types.ModuleType("memoria_pessoal_decisoes")
dec.texto_para_prompt = lambda login: "- #1 **pagamento** (não pode): nunca pagar"
dec._mtime = (PLUGINS / "memoria_pessoal" / "helpers" / "decisoes.py").stat().st_mtime
fic = types.ModuleType("memoria_pessoal_ficha")
fic.texto_para_prompt = lambda login: ("- mora em Salvador", True)
fic._mtime = (PLUGINS / "memoria_pessoal" / "helpers" / "ficha.py").stat().st_mtime
sys.modules.update({"memoria_pessoal_decisoes": dec, "memoria_pessoal_ficha": fic})
r1 = cx.contexto(session_id="tg-matheus", is_first_turn=True)["context"]
checa(cx.contexto(session_id="tg-matheus", is_first_turn=False,
                  conversation_history=[{"role": "user", "api_content": "oi\n\n" + r1}]) is None, "ainda na conversa: não repete")
r2 = cx.contexto(session_id="tg-matheus", is_first_turn=False, conversation_history=resumo)
checa(r2 and "nunca pagar" in r2["context"], "o resumo levou embora: volta no turno seguinte")

if falhas:
    print("FALHAS:")
    for f in falhas:
        print(" -", f)
    sys.exit(1)
print("ok: test_cerebro_hermes")

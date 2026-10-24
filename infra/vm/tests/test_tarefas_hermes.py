"""Tests of tarefas_hermes (infra/vm/hermes/plugins/agentepessoal): long tasks with the plan on disk (Matheus 23/10,
"Pode fazer e testar"). A long request becomes /a0/usr/tarefas/<login>/<id>/plano.json + resultado.md; steps change only
through the TRANSICOES table (done is final), each finished step appends its result, an external action is recorded
before ("vou fazer X") and proven after, and on a resume it must be checked before being redone; a step that needs
Matheus asks him once and the independent steps go on; the watcher resumes an unfinished task whose session runs
nothing (restart, crash, usage limit, timeout, stopped run) in that session, with backoff and a cap, then tells him once;
the end delivers one message with the whole file; each person only sees their own tasks; /parar pauses them.
Run from the repository root: python3 infra/vm/tests/test_tarefas_hermes.py"""
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import threading
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
P = RAIZ / "infra" / "vm" / "hermes" / "plugins" / "agentepessoal"
falhas = []


def checa(cond, msg):
    if not cond:
        falhas.append(msg)


spec = importlib.util.spec_from_file_location("teste_tarefas", P / "tarefas_hermes.py")
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
tmp = Path(tempfile.mkdtemp(prefix="tarefas-"))
t.RAIZ = tmp / "tarefas"
t.VIVAS = tmp / "vivas"
ponte = types.ModuleType("agentepessoal_ponte_a0")
ponte.login_da_sessao = lambda s: "ilia" if s.endswith("ilia") else ("teste_hermes" if "teste_hermes" in s else "matheus")
ponte.SESSOES = tmp / "sessoes.json"
sys.modules["agentepessoal_ponte_a0"] = ponte
enviados = []


def enviar(login, texto, arquivo="", legenda=""):
    enviados.append({"login": login, "texto": texto, "arquivo": arquivo, "legenda": legenda})
    return ""


t.enviar = enviar
checa(t.passo_do_relogio(raiz=tmp, conversa_fn=lambda *a: 1 / 0) == [], "logo depois de carregar (Hermes subindo): o vigia espera")
t._CARREGADO = 0
AGORA = 1_800_000_000.0

# ---- criar: pasta da pessoa, pedido como veio, passos em ordem (cada um depende do anterior, salvo [] = independente)
pedido = "Testa o Raiz Connect como cliente novo, todos os módulos, e me manda o relatório"
plano = t.criar("matheus", "Teste E2E Raiz", pedido, ["Cadastro", "Estoque", {"titulo": "Fiscal", "depende_de": []},
                                                       "Relatório"], "tg-matheus", agora=AGORA)
tid = plano["id"]
p = t.pasta("matheus", tid)
salvo = json.loads((p / "plano.json").read_text())
checa(salvo["pedido"] == pedido and salvo["login"] == "matheus" and salvo["estado"] == "aberta"
      and [x["estado"] for x in salvo["passos"]] == ["falta"] * 4, "plano em disco com o pedido como veio")
checa([x["depende_de"] for x in salvo["passos"]] == [[], [1], [], [3]], f"dependências: {[x['depende_de'] for x in salvo['passos']]}")
checa(salvo["sessao_alvo"] == "tg-matheus" and salvo["origem"] == "conversa", "conversa: retoma na própria sessão")
checa(pedido in (p / "resultado.md").read_text(), "resultado.md começa com o pedido")
for ruim in (["só um"], []):
    try:
        t.criar("matheus", "x", "y", ruim, "tg-matheus")
        checa(False, f"tarefa com {len(ruim)} passo não é longa")
    except ValueError:
        pass
for tid_ruim in ("../../segredos", "1023-1530-zzzz", ""):
    try:
        t.pasta("matheus", tid_ruim)
        checa(False, f"id torto aceito: {tid_ruim!r}")
    except ValueError:
        pass
try:
    t.pasta("../matheus", tid)
    checa(False, "login torto aceito")
except ValueError:
    pass

# rotina: retoma na conversa principal da pessoa (a do mapa da ponte)
rot = t.criar("matheus", "Rotina grande", "pedido da rotina", ["a", "b"], "cron_ab12cd34ef56_20261023_081700",
              agora=AGORA, mapa={"atual:tg-matheus": "tg-matheus-20261023101010"})
checa(rot["origem"] == "rotina" and rot["sessao_alvo"] == "tg-matheus-20261023101010", f"rotina: {rot['sessao_alvo']}")
checa(t.sessao_alvo("matheus", "api-qualquer", {}) == "tg-matheus" and t.sessao_alvo("ilia", "tgp2-ilia") == "tgp2-ilia",
      "sessão sem dono vai à principal; paralela fica na dela")

# ---- passos: só pela tabela; feito é final; o resultado entra no arquivo
r = t.mudar_passo("matheus", tid, 1, "fazendo", sessao="tg-matheus", agora=AGORA + 10)
checa("Anotado" in r, f"fazendo: {r}")
r = t.mudar_passo("matheus", tid, 1, "feito", resultado="Conta criada, onboarding ok.", agora=AGORA + 20)
checa("Próximo: passo 2" in r, f"feito aponta o próximo: {r}")
r = t.mudar_passo("matheus", tid, 1, "fazendo", agora=AGORA + 30)
checa(r.startswith("NÃO FEITO") and "não se refaz" in r, f"passo feito não volta: {r}")
r = t.mudar_passo("matheus", tid, 9, "feito", agora=AGORA + 30)
checa(r.startswith("NÃO FEITO") and "passo 9" in r, f"passo inexistente: {r}")
r = t.mudar_passo("matheus", tid, 2, "pronto", agora=AGORA + 30)
checa(r.startswith("NÃO FEITO"), "estado fora da lista")
res = (p / "resultado.md").read_text()
checa("## Passo 1 — Cadastro" in res and "Conta criada, onboarding ok." in res, "o resultado do passo 1 está no arquivo")

# ---- ação de fora: marcada antes, provada depois; na retomada, conferida antes de refazer
r = t.mudar_passo("matheus", tid, 2, "fazendo", acao="vou criar o produto Teste no estoque", agora=AGORA + 40)
r = t.mudar_passo("matheus", tid, 2, "feito", resultado="produto criado", agora=AGORA + 50)
checa(r.startswith("NÃO FEITO") and "prova" in r, f"ação de fora sem prova não fecha: {r}")
st = t.status("matheus", tid)
checa("NÃO confirmada" in st and "vou criar o produto Teste" in st, "o status avisa a ação marcada e não confirmada")
r = t.mudar_passo("matheus", tid, 2, "fazendo", acao="vou criar o produto Teste no estoque", agora=AGORA + 60)
checa(r.startswith("NÃO FEITO") and "confira" in r, f"retomada: não refaz sem conferir: {r}")
r = t.mudar_passo("matheus", tid, 2, "fazendo", acao="vou criar o produto Teste no estoque",
                  conferido="abri a lista de produtos: não existe", agora=AGORA + 70)
checa("Anotado" in r, f"conferido: segue ({r})")
r = t.mudar_passo("matheus", tid, 2, "feito", resultado="produto criado", prova="id 4412, lido de volta na lista",
                  agora=AGORA + 80)
checa("Anotado" in r, f"com prova fecha: {r}")
salvo = json.loads((p / "plano.json").read_text())
ac = salvo["passos"][1]["acao"]
checa(ac["estado"] == "feita" and "4412" in ac["prova"] and salvo["passos"][1]["tentativas"] == 2,
      f"ação feita com prova; 2 tentativas ({ac}, {salvo['passos'][1]['tentativas']})")
checa("Prova: id 4412" in (p / "resultado.md").read_text(), "a prova vai para o arquivo")

# ---- precisa do Matheus: pergunta uma vez; o que não depende segue
enviados.clear()
r = t.mudar_passo("matheus", tid, 3, "esperando_matheus", pergunta="Qual CNPJ uso no teste fiscal?", agora=AGORA + 90)
checa(len(enviados) == 1 and "CNPJ" in enviados[0]["texto"] and "Mandei a pergunta" in r, f"pergunta ao celular: {r}")
t.mudar_passo("matheus", tid, 3, "esperando_matheus", pergunta="Qual CNPJ uso no teste fiscal?", agora=AGORA + 95)
checa(len(enviados) == 1, "a mesma pergunta não vai de novo")
salvo = json.loads((p / "plano.json").read_text())
checa(t.situacao(salvo) == "esperando", f"o passo 4 depende do 3: só falta o Matheus ({t.situacao(salvo)})")
indep = t.criar("matheus", "Pesquisa", "p", ["A", {"titulo": "B", "depende_de": []}], "tg-matheus", agora=AGORA)
t.mudar_passo("matheus", indep["id"], 1, "esperando_matheus", pergunta="qual cidade?", agora=AGORA + 1)
checa(t.situacao(t.ler(t.pasta("matheus", indep["id"]))) == "pronta", "passo independente segue enquanto espera")
ctx = t.lembrete("tg-matheus")
checa(ctx and "CNPJ" in ctx["context"] and tid in ctx["context"], "a conversa sabe da pergunta aberta (lembrete)")
checa(t.lembrete("cron_ab12cd34ef56_20261023_081700") is None, "rotina não recebe o lembrete")

# ---- isolamento: cada pessoa só as dela
checa("Nenhuma tarefa" in t.status("ilia") and tid not in t.status("ilia"), "a convidada não vê as do Matheus")
r = t.mudar_passo("ilia", tid, 3, "falta")
checa(r.startswith("NÃO FEITO"), "nem muda")
checa(t.lembrete("tg-ilia") is None, "nem no lembrete")
checa(tid in t.status("matheus"), "o Matheus vê as dele")

# ---- concluir: só com tudo resolvido; uma mensagem com o arquivo
r = t.concluir("matheus", tid, "Tudo certo menos o fiscal.")
checa(r.startswith("NÃO FEITO") and "3 (esperando_matheus)" in r, f"não conclui com passo aberto: {r}")
t.mudar_passo("matheus", tid, 3, "feito", resultado="NF-e de teste emitida", agora=AGORA + 100)
t.mudar_passo("matheus", tid, 4, "fazendo", agora=AGORA + 110)
t.mudar_passo("matheus", tid, 4, "feito", resultado="relatório: 3 problemas", agora=AGORA + 120)
enviados.clear()
r = t.concluir("matheus", tid, "3 problemas: X, Y, Z.", sessao="tg-matheus", agora=AGORA + 130)
checa("Responda só: ok" in r and len(enviados) == 1, f"entregue: {r}")
e = enviados[0]
checa(e["login"] == "matheus" and e["arquivo"].endswith(f"-{tid}.md") and "3 problemas" in e["legenda"],
      f"uma mensagem: resumo na legenda e o arquivo ({e})")
final = Path(e["arquivo"]).read_text()
checa(final.index("## Resumo") < final.index("## Passo 1") < final.index("## Passo 4") and pedido in final,
      "o arquivo: pedido, resumo e todos os passos em ordem")
checa(t._nome_arquivo({"titulo": "Relatório: açaí & CMV", "id": tid}) == f"relatorio-acai-cmv-{tid}.md", "nome do arquivo sem acento")
checa(t.concluir("matheus", tid, "de novo").startswith("Já estava concluída") and len(enviados) == 1, "não entrega duas vezes")

ordem = t.criar("matheus", "Ordem", "p", [{"titulo": "A", "depende_de": []}, {"titulo": "B", "depende_de": []}], "tg-matheus")
t.mudar_passo("matheus", ordem["id"], 2, "feito", resultado="rB")
t.mudar_passo("matheus", ordem["id"], 1, "feito", resultado="rA")
t.concluir("matheus", ordem["id"], "ok")
txt = (t.pasta("matheus", ordem["id"]) / "resultado.md").read_text()
checa(txt.index("## Passo 1") < txt.index("## Passo 2") and "rA" in txt and "rB" in txt, "arquivo final na ordem dos passos")
# entrega que falhou: o vigia entrega depois (sem modelo)
falhar = ["ponte fora"]
ent = t.criar("matheus", "Entrega", "p", ["a", "b"], "tg-matheus", agora=AGORA)
for n in (1, 2):
    t.mudar_passo("matheus", ent["id"], n, "feito", resultado=f"r{n}", agora=AGORA)
r = t.concluir("matheus", ent["id"], "ok", agora=AGORA + 1, enviar_fn=lambda *a: falhar[0])
checa("falhou" in r, f"entrega falhou: {r}")
feito = t.passo_do_relogio(agora=AGORA + 400, conversa_fn=lambda *a: {"ok": True}, enviar_fn=lambda *a: "",
                           inicio_fn=lambda pid: "x")
checa((ent["id"], "entregue") in feito, f"o vigia entregou depois ({feito})")

# ---- sessões vivas
v = tmp / "vivas_t"
checa(t.viva("tg-x", v, AGORA) == (False, "nada rodando"), "sem batimento: nada rodando")
t.marcar("tg-x", v, AGORA, turno_desde=AGORA, fim=None, ferramenta=None)
eu = t._EU["inicio"]
checa(t.viva("tg-x", v, AGORA + 60, lambda pid: eu)[0], "turno em andamento no mesmo processo: rodando")
checa(t.viva("tg-x", v, AGORA + 60, lambda pid: "outro")[1] == "o agente reiniciou no meio", "container reiniciado")
checa(not t.viva("tg-x", v, AGORA + t.SEM_SINAL + 5, lambda pid: eu)[0], "sem sinal há 20 min: parado")
t.marcar("tg-x", v, AGORA, ferramenta="terminal")
checa(t.viva("tg-x", v, AGORA + 3600, lambda pid: eu)[0], "ferramenta longa (ou o ok pelo celular): segue rodando")
t.marcar("tg-x", v, AGORA + 10, fim=AGORA + 10, ferramenta=None)
checa(t.viva("tg-x", v, AGORA + 11, lambda pid: eu)[1] == "o pedido terminou sem fechar a tarefa", "turno terminou")
checa(t._inicio_processo(os.getpid()) == eu and eu, "o início do processo vem do /proc")
t.VIVAS = tmp / "vivas_g"
t.gancho_inicio(session_id="tg-y")
d = json.loads((t.VIVAS / "tg-y.json").read_text())
checa(d["fim"] is None and d["pid"] == os.getpid(), "gancho do início do turno")
t.gancho_ferramenta(tool_name="browser_click", session_id="tg-y")
checa(json.loads((t.VIVAS / "tg-y.json").read_text())["ferramenta"] == "browser_click", "gancho da ferramenta")
t.gancho_fim(session_id="tg-y")
checa(json.loads((t.VIVAS / "tg-y.json").read_text())["fim"], "gancho do fim do turno")

# ---- o vigia: retoma na sessão dela, com espera crescente e teto; avisa uma vez
t.RAIZ = tmp / "vigia"
t.VIVAS = tmp / "vivas_v"
conversas = []


def conversa(login, texto, sessao):
    conversas.append((login, texto, sessao))
    return {"ok": True}


vivo = {"inicio": "velho"}
ini = lambda pid: vivo["inicio"]  # noqa: E731
w = t.criar("teste_hermes", "Pesquisa longa", "5 passos", ["p1", "p2", "p3", "p4", "p5"], "tg-teste_hermes", agora=AGORA)
wid = w["id"]
t.mudar_passo("teste_hermes", wid, 1, "fazendo", sessao="tg-teste_hermes", agora=AGORA)
t.mudar_passo("teste_hermes", wid, 1, "feito", resultado="r1", agora=AGORA + 60)
t.mudar_passo("teste_hermes", wid, 2, "fazendo", agora=AGORA + 70)
t.marcar("tg-teste_hermes", agora=AGORA + 80, turno_desde=AGORA, fim=None, ferramenta=None)
vivo["inicio"] = t._EU["inicio"]
checa(t.passo_do_relogio(agora=AGORA + 400, conversa_fn=conversa, inicio_fn=ini) == [] and not conversas,
      "rodando na sessão: o vigia espera")
vivo["inicio"] = "reiniciou"  # o container reiniciou: o processo do batimento não existe mais
checa(t.passo_do_relogio(agora=AGORA + 100, conversa_fn=conversa, inicio_fn=ini) == [] and not conversas,
      "logo depois de parar: espera um pouco (o Hermes subindo)")
feito = t.passo_do_relogio(agora=AGORA + 200, conversa_fn=conversa, inicio_fn=ini)
checa(len(conversas) == 1 and conversas[0][0] == "teste_hermes" and conversas[0][2] == "tg-teste_hermes"
      and f"retome a tarefa {wid}" in conversas[0][1].lower() and "reiniciou" in conversas[0][1],
      f"retomada na sessão dela, dizendo por quê ({feito}, {conversas})")
checa(t.passo_do_relogio(agora=AGORA + 260, conversa_fn=conversa, inicio_fn=ini) == [] and len(conversas) == 1,
      "não retoma de novo em seguida")
# a retomada andou (passo 2 feito): o fôlego volta
t.mudar_passo("teste_hermes", wid, 2, "feito", resultado="r2", agora=AGORA + 300)
checa(t.ler(t.pasta("teste_hermes", wid))["sem_progresso"] == 0, "passo feito zera as retomadas sem progresso")
# sem progresso: espera crescente e, no teto, um aviso só
agora = AGORA + 300
enviados.clear()
for _ in range(40):
    agora += 600
    t.passo_do_relogio(agora=agora, conversa_fn=conversa, inicio_fn=ini)
salvo = t.ler(t.pasta("teste_hermes", wid))
checa(salvo["sem_progresso"] == t.MAX_RETOMADAS and salvo["travada_em"], f"teto de retomadas ({salvo['sem_progresso']})")
checa(len(conversas) == 1 + t.MAX_RETOMADAS, f"retomadas: {len(conversas)}")
intervalos = [b["em"] - a["em"] for a, b in zip(salvo["retomadas"][1:], salvo["retomadas"][2:])]
checa(intervalos == sorted(intervalos) and intervalos[-1] >= t.BACKOFF[-2], f"espera crescente: {intervalos}")
checa(len(enviados) == 1 and "não consegui retomar" in enviados[0]["texto"] and enviados[0]["login"] == "teste_hermes",
      f"avisa uma vez ({enviados})")
t.passo_do_relogio(agora=agora + 9000, conversa_fn=conversa, inicio_fn=ini)
checa(len(enviados) == 1 and len(conversas) == 1 + t.MAX_RETOMADAS, "travada: nada mais até ele pedir")
r = t.mudar_passo("teste_hermes", wid, 3, "fazendo", agora=agora + 9100)  # ele disse "continua"
checa(not t.ler(t.pasta("teste_hermes", wid))["travada_em"], "mexeu na tarefa: destrava")

# esperando só o Matheus, pausada pelo /parar: o vigia não retoma
pau = t.criar("teste_hermes", "Pausada", "p", ["a", "b"], "tg-teste_hermes", agora=AGORA)
titulos = t.pausar("teste_hermes")
checa("Pausada" in titulos and t.pausar("teste_hermes") == [], f"o /parar pausa as abertas, uma vez ({titulos})")
esp = t.criar("teste_hermes", "Espera", "p", ["a", "b"], "tg-teste_hermes", agora=AGORA)
t.mudar_passo("teste_hermes", esp["id"], 1, "esperando_matheus", pergunta="qual?", agora=AGORA)
n = len(conversas)
feito = t.passo_do_relogio(agora=agora + 20000, conversa_fn=conversa, inicio_fn=ini)
checa(all(x[0] not in (esp["id"], pau["id"]) for x in feito) and len(conversas) == n,
      f"esperando o Matheus ou pausada: não retoma ({feito})")
checa("pausada" in t.status("teste_hermes", pau["id"]), "o status diz que está pausada")
t.mudar_passo("teste_hermes", pau["id"], 1, "fazendo", agora=agora + 20001)
checa(not (t.pasta("teste_hermes", pau["id"]) / "pausada").exists(), "voltou a andar: sai da pausa")
# tudo resolvido mas sem entrega: o vigia pede só o resumo
fim = t.criar("teste_hermes", "Sem entrega", "p", ["a", "b"], "tg-teste_hermes", agora=AGORA)
for n_ in (1, 2):
    t.mudar_passo("teste_hermes", fim["id"], n_, "feito", resultado="x", agora=AGORA)
conversas.clear()
t.passo_do_relogio(agora=agora + 30000, conversa_fn=conversa, inicio_fn=ini)
checa(any(fim["id"] in c[1] and "tarefa_concluir" in c[1] and "estão resolvidos" in c[1] for c in conversas),
      "falta só entregar: o vigia pede o resumo")
# uma pasta trocada de dono nunca faz o vigia agir por outra pessoa
torto = t.RAIZ / "ilia" / wid
torto.mkdir(parents=True)
(torto / "plano.json").write_text((t.pasta("teste_hermes", wid) / "plano.json").read_text())
conversas.clear()
t.passo_do_relogio(agora=agora + 90000, conversa_fn=conversa, inicio_fn=ini)
checa(all(c[0] != "ilia" for c in conversas), "plano de um login na pasta de outro: ignorado")

# ---- escrita concorrente: nada se perde
t.RAIZ = tmp / "conc"
c = t.criar("matheus", "Paralelo", "p", [{"titulo": f"p{i}", "depende_de": []} for i in range(1, 9)], "tg-matheus")
ths = [threading.Thread(target=t.mudar_passo, args=("matheus", c["id"], i, "feito"), kwargs={"resultado": f"r{i}"})
       for i in range(1, 9)]
[x.start() for x in ths]
[x.join() for x in ths]
salvo = t.ler(t.pasta("matheus", c["id"]))
res = (t.pasta("matheus", c["id"]) / "resultado.md").read_text()
checa(all(x["estado"] == "feito" for x in salvo["passos"]) and all(f"r{i}\n" in res for i in range(1, 9)),
      "8 passos ao mesmo tempo: todos no plano e no arquivo")
checa(not list(t.pasta("matheus", c["id"]).glob("*.tmp")), "sem temporário largado")

# ---- as ferramentas (o que o modelo chama)
t.RAIZ = tmp / "ferr"
r = asyncio.run(t.executar("tarefa_iniciar", {"titulo": "T", "pedido": "faz tudo", "passos": "- um\n- dois\n- três"},
                           "tg-matheus"))
checa("aberta com 3 passos" in r, f"iniciar com a lista em texto: {r}")
tid2 = r.split("Tarefa ", 1)[1].split(" ", 1)[0]
r = asyncio.run(t.executar("tarefa_passo", {"id": tid2, "passo": 1, "estado": "feito", "resultado": "ok1"}, "tg-matheus"))
checa("Próximo: passo 2" in r, f"passo pela ferramenta: {r}")
r = asyncio.run(t.executar("tarefa_status", {"id": tid2}, "tg-matheus"))
checa("faz tudo" in r and "ok1" in r and "Próximo passo: 2" in r, f"status pela ferramenta: {r[:200]}")
r = asyncio.run(t.executar("tarefa_status", {"id": tid2}, "tg-ilia"))
checa("Não achei" in r, "a convidada não lê pela ferramenta")
r = asyncio.run(t.executar("tarefa_passo", {"id": "../x", "passo": 1, "estado": "feito"}, "tg-matheus"))
checa(r.startswith("NÃO FEITO"), "id torto pela ferramenta")
registrados = {"tools": [], "hooks": []}
ctxm = types.SimpleNamespace(register_tool=lambda **k: registrados["tools"].append(k["name"]),
                             register_hook=lambda nome, f: registrados["hooks"].append(nome))
t.registrar(ctxm)
checa(registrados["tools"] == ["tarefa_iniciar", "tarefa_passo", "tarefa_status", "tarefa_concluir"]
      and {"pre_llm_call", "on_session_end", "pre_tool_call", "post_tool_call", "pre_api_request"} <= set(registrados["hooks"]),
      f"registro: {registrados}")
for nome, esq in t.ESQUEMAS.items():
    checa(esq["name"] == nome and esq["parameters"]["type"] == "object" and len(esq["description"]) < 2000,
          f"esquema de {nome}")

# ---- ligações no plugin: relógio, convidados, SOUL, skill
init = (P / "__init__.py").read_text()
checa('_sub("agentepessoal_tarefas", "tarefas_hermes.py")' in init and "tarefas.registrar(ctx)" in init, "o plugin registra")
rel = (P / "relogio_hermes.py").read_text()
checa('sys.modules.get("agentepessoal_tarefas")' in rel and "tarefas.passo_do_relogio" in rel, "o vigia roda no relógio")
ace = (P / "acesso_hermes.py").read_text()
checa('"tarefa_iniciar", "tarefa_passo", "tarefa_status", "tarefa_concluir"' in ace, "convidado usa as dele")
alma = (RAIZ / "infra" / "vm" / "hermes" / "SOUL.md").read_text()
checa("tarefa_iniciar" in alma and "tarefa-longa" in alma, "a persona manda usar")
sk = (RAIZ / "infra" / "vm" / "hermes" / "skills" / "tarefa-longa" / "SKILL.md").read_text()
checa("Raiz Connect" in sk and "esperando_matheus" in sk and "prova" in sk and "conferido" in sk, "a skill cobre o caso")
raiz_skill = (RAIZ / "infra" / "vm" / "hermes" / "skills" / "teste-fluxo-produto-raizconnect" / "SKILL.md").read_text()
checa("tarefa_iniciar" in raiz_skill and "\nressemear: " in raiz_skill, "o teste E2E da Raiz usa tarefa longa (ressemeada)")

if falhas:
    raise SystemExit("test_tarefas_hermes: " + "; ".join(falhas))
print("test_tarefas_hermes: ok")

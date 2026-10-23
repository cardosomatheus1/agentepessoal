"""Tests of the routines in the Hermes (23/10 migration, phase 5): every scheduled task of the A0 has its Hermes
version (same schedule, same request with only the tools changed, nothing essential lost, created paused); a cron
round gets the scheduled-task block and the corrections Matheus approved, and its final answer goes to the owner's
phone with the A0 rules (SEM NOVIDADE quiet, PRECISA DE VOCÊ urgent, the A0 id for the morning summary), the gate is
confirmed and the self-assessment runs; the first turn of any session carries the person's profile and decisions;
`reuniao` schedules its briefing and follow-up as Hermes one-shot jobs. Run from the repository root:
python3 infra/vm/tests/test_rotinas_hermes.py"""
import asyncio
import importlib.util
import json
import re
import sys
import tempfile
import time
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
P = RAIZ / "infra" / "vm" / "hermes" / "plugins" / "agentepessoal"
PLUGINS = RAIZ / "infra" / "vm" / "plugins"
H = RAIZ / "infra" / "vm" / "hermes"
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


# --- 1. the sources: 23 routines, A0 schedule, nothing of the A0 tools, essentials kept
fontes = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((H / "rotinas").glob("*.json"))}
checa(len(fontes) == 23, f"as 23 tarefas agendadas do A0 têm a versão do Hermes ({len(fontes)})")
ANTIGAS = re.compile(r"`browser`|vision_load|code_execution|search_engine|ferramentas_extras|call_subordinate|notify_user|"
                     r"document_query|`response`|`scheduler`|scheduler/tasks\.json|salvar_rotina|me_mostre|tarefa_limite|"
                     r"criar_gatilho|browser_id|`pesquisar`|`canal`|painel_vivo|skills_tool|memory_save|memory_load")
for uuid, r in fontes.items():
    checa(r["a0"] == uuid and r["nome"] and r["fuso"] == "America/Bahia", f"{uuid}: id, nome e fuso do A0")
    checa(re.fullmatch(r"\S+ \S+ \S+ \S+ \S+", r["agenda"]), f"{uuid}: horário em cron de 5 campos ({r['agenda']})")
    checa(not ANTIGAS.search(r["pedido"]), f"{uuid} ainda cita ferramenta do A0: {ANTIGAS.findall(r['pedido'])[:3]}")
    checa("sonnet" in r["modelo"], f"{uuid}: rotina no Sonnet (decisão 4 do Matheus: Haiku no dia a dia, Sonnet nas rotinas)")
desligadas = {u for u, r in fontes.items() if not r["ligada_no_a0"]}
checa(desligadas == {"H8kWmYP1", "qAvKcIyw", "2FQESGed", "8COQyGTD", "gOqdMBE3", "PZoyGwEh"},
      f"as desligadas no A0 seguem marcadas como desligadas ({sorted(desligadas)})")
ess = carregar("teste_essenciais", RAIZ / "infra" / "vm" / "tests" / "test_rotinas_essenciais.py")
for uuid, itens in ess.ESSENCIAIS.items():
    if uuid in fontes:
        for item in itens:
            checa(item in fontes[uuid]["pedido"], f"{uuid}: a versão do Hermes perdeu «{item}»")
for chave, uuid in (("prospeccao:buscar", "laMIuaPt"), ("prospeccao:executar", "F9Ku9frw")):
    for item in ess.ESSENCIAIS[chave]:
        if "skill `prospeccao-instagram`" == item:
            item = "prospeccao-instagram"
        checa(item in fontes[uuid]["pedido"], f"{uuid} ({chave}): a versão do Hermes perdeu «{item}»")
ap = (H / "rotinas_aplicar.py").read_text()
checa("paused=True" in ap and "jobs.update_job(job_id, campos)" in ap and '"enabled"' not in ap.split("campos =")[1].split("}")[0],
      "rotina nova nasce pausada; atualizar não liga nem desliga")
sh = (H / "subir.sh").read_text()
checa("HERMES_SEM_ROTINAS" in sh and "rotinas_aplicar.py" in sh, "a implantação aplica as rotinas (o git é a fonte)")

# --- 2. a cron round: block, corrections, delivery, gate, self-assessment
tmp = Path(tempfile.mkdtemp())
ponte = carregar("agentepessoal_ponte_a0", P / "ponte_a0.py")
ponte.PLUGINS = PLUGINS
ponte.SESSOES = tmp / "sessoes.json"
ponte.SESSOES.write_text('{"s-ilia": "ilia"}')
rh = carregar("teste_rotinas_hermes", P / "rotinas_hermes.py")
rh.PLUGINS = PLUGINS
rh.MAPA = tmp / "rotinas.json"
rh.CHECKPOINTS = tmp / "rotinas"
rh.JOBS = tmp / "jobs.json"
rh.MAPA.write_text(json.dumps({"abc123": {"a0": "HL76nfIg", "nome": "🔎 Radar e fios soltos"}}))
enviados, confirmados, avaliados = [], [], []
falso = types.ModuleType("whatsapp_ponte")
real = carregar("ponte_real_teste", PLUGINS / "whatsapp" / "helpers" / "ponte.py")
falso.SILENCIO, falso.urgente, falso.pede_tela = real.SILENCIO, real.urgente, real.pede_tela
falso.enviar = lambda *a, **k: enviados.append((a, k)) or ""
falso._mtime = (PLUGINS / "whatsapp" / "helpers" / "ponte.py").stat().st_mtime
sys.modules["whatsapp_ponte"] = falso
rot = types.ModuleType("rotinas_helper")
rot.correcoes_agendada = lambda u: ["Não repita o fio do PayGo"] if u == "HL76nfIg" else []
rot._mtime = (PLUGINS / "rotinas" / "helpers" / "rotinas.py").stat().st_mtime
sys.modules["rotinas_helper"] = rot
port = types.ModuleType("rotinas_portao")
port.confirmar = lambda u: confirmados.append(u) or True
port._mtime = (PLUGINS / "rotinas" / "helpers" / "portao.py").stat().st_mtime
sys.modules["rotinas_portao"] = port
auto = types.ModuleType("rotinas_autoavaliacao")
auto.autoavaliar = lambda u, n, t, pedido="": avaliados.append((u, n, t)) or {"motivo": "avaliada"}
auto._mtime = (PLUGINS / "rotinas" / "helpers" / "autoavaliacao.py").stat().st_mtime
sys.modules["rotinas_autoavaliacao"] = auto

sess = "cron_abc123_20261023_084000"
c = rh.contexto(session_id=sess, is_first_turn=True)["context"]
checa("LER → ENTENDER → AGIR" in c and "SEM NOVIDADE" in c and "PRECISA DE VOCÊ:" in c and "🔎 Radar e fios soltos" in c
      and str(rh.CHECKPOINTS / "HL76nfIg" / "contexto.md") in c and "whatsapp_enviar" in c, "bloco de tarefa agendada do A0")
checa("Não repita o fio do PayGo" in c, "as correções aprovadas pelo Matheus entram na rodada")
checa(rh.contexto(session_id="api-123", is_first_turn=True) is None and rh.contexto(session_id=sess) is None,
      "só no 1º turno de uma rodada do cron")
rh.entregar(session_id=sess, assistant_response="Achei 2 e-mails novos do PayGo.", user_message="pedido")
time.sleep(0.2)
(a, k) = enviados[-1]
checa(a[0] == "matheus" and a[1].startswith("*🔎 Radar e fios soltos*\n\nAchei 2") and a[5] == "progresso"
      and a[7] == "🔎 Radar e fios soltos" and k.get("reenviar"),
      f"resultado ao celular do dono, com o nome da rotina (o 📰 junta os avisos da noite, como no A0): {enviados[-1]}")
checa(confirmados == ["HL76nfIg"] and avaliados and avaliados[-1][0] == "HL76nfIg", "portão confirmado e autoavaliação")
rh.entregar(session_id=sess, assistant_response="de novo")
checa(len(enviados) == 1, "a mesma rodada nunca vira 2 mensagens")
rh.entregar(session_id="cron_abc123_20261023_114000", assistant_response="SEM NOVIDADE: nada mudou")
checa(len(enviados) == 1, "SEM NOVIDADE fica quieto")
rh.entregar(session_id="cron_abc123_20261023_144000", assistant_response="PRECISA DE VOCÊ: o login do Gmail caiu")
checa(enviados[-1][0][5] == "urgente", "PRECISA DE VOCÊ vai como urgente")
rh.entregar(session_id="api-999", assistant_response="conversa normal")
checa(len(enviados) == 2, "conversa que não é do cron não passa por aqui")
rh.JOBS.write_text(json.dumps({"jobs": [{"id": "zzz", "name": "📅 Briefing: X"}]}))
checa(rh.rotina("zzz") == {"a0": "", "nome": "📅 Briefing: X"}, "rotina sem mapa (briefing): nome do cron do Hermes")

# --- 3. profile and decisions on the first turn
cx = carregar("teste_contexto_hermes", P / "contexto_hermes.py")
cx.PLUGINS = PLUGINS
dec = types.ModuleType("memoria_pessoal_decisoes")
dec.texto_para_prompt = lambda login: f"- #1 **pagamento** (não pode): nunca pagar ({login})"
dec._mtime = (PLUGINS / "memoria_pessoal" / "helpers" / "decisoes.py").stat().st_mtime
fic = types.ModuleType("memoria_pessoal_ficha")
fic.texto_para_prompt = lambda login: (f"- mora em Salvador ({login})", True)
fic._mtime = (PLUGINS / "memoria_pessoal" / "helpers" / "ficha.py").stat().st_mtime
sys.modules.update({"memoria_pessoal_decisoes": dec, "memoria_pessoal_ficha": fic})
r = cx.contexto(session_id="api-1", is_first_turn=True)["context"]
checa("Decisões em vigor" in r and "nunca pagar (matheus)" in r and "Salvador (matheus)" in r, f"ficha e decisões do dono: {r}")
checa("(ilia)" in cx.contexto(session_id="s-ilia", is_first_turn=True)["context"] and "(matheus)" not in
      cx.contexto(session_id="s-ilia", is_first_turn=True)["context"], "convidado vê só as dele")
checa(cx.contexto(session_id="api-1", is_first_turn=False) is None, "só no 1º turno")

# --- 4. reuniao over the Hermes cron
rn = carregar("teste_reuniao_hermes", P / "reuniao_hermes.py")
rn.PLUGINS = PLUGINS
a = rn.aux()
a.PASTA = tmp / "auxiliar"
criados, removidos = [], []


class CronFalso:
    def create_job(self, **kw):
        criados.append(kw)
        return {"id": f"j{len(criados)}"}

    def remove_job(self, job_id):
        removidos.append(job_id)
        return True


cf = CronFalso()
inicio = (a.agora() + a.dt.timedelta(hours=3)).isoformat()
fim = (a.agora() + a.dt.timedelta(hours=4)).isoformat()
msg = rn.agendar("teste_hermes", "ev1", "Alinhamento NEXOS", inicio, fim, "João", "Meet", cron=cf)
checa("briefing às" in msg and "pergunta do pós" in msg and len(criados) == 2, f"briefing e pós agendados no cron do Hermes: {msg}")
checa(criados[0]["name"].startswith("📅 Briefing:") and criados[0]["repeat"] == 1 and criados[1]["name"].startswith("📝 Pós-reunião:")
      and "Alinhamento NEXOS" in criados[0]["prompt"] and criados[0]["deliver"] == "local", f"uma vez só, com o pedido do A0: {criados}")
reg = a.carregar("teste_hermes")["reunioes"][0]
checa(reg["tarefa_briefing"] == "hermes:j1" and reg["tarefa_pos"] == "hermes:j2", "o registro guarda os ids do Hermes")
checa("já estava agendada" in rn.agendar("teste_hermes", "ev1", "Alinhamento NEXOS", inicio, fim, cron=cf), "mesma hora: nada muda")
novo_ini = (a.agora() + a.dt.timedelta(hours=5)).isoformat()
rn.agendar("teste_hermes", "ev1", "Alinhamento NEXOS", novo_ini, "", cron=cf)
checa(removidos == ["j1", "j2"] and len(criados) == 4, "horário mudou: os antigos saem, os novos entram")
checa("cancelada" in rn.cancelar("teste_hermes", "ev1", cron=cf) and removidos[-2:] == ["j3", "j4"]
      and not a.carregar("teste_hermes")["reunioes"], "cancelar tira os agendamentos e o registro")
# a gravação falha (ex.: só leitura): nenhum agendamento fica órfão no cron
salvar_real = a.salvar
a.salvar = lambda *x, **k: (_ for _ in ()).throw(OSError(30, "Read-only file system"))
antes = len(criados)
try:
    rn.agendar("teste_hermes", "ev2", "Outra", inicio, fim, cron=cf)
except OSError:
    pass
a.salvar = salvar_real
checa(len(criados) == antes + 2 and removidos[-2:] == [f"j{antes + 1}", f"j{antes + 2}"],
      "gravação falhou: os agendamentos criados saem (nada órfão rodando o modelo)")
import os
os.environ["AGENTEPESSOAL_ENSAIO"] = "1"
n = len(criados)
r_ensaio = asyncio.run(rn.executar({"acao": "agendar", "evento_id": "ev3", "titulo": "X", "inicio": inicio}, session_id="s"))
checa("Ensaio" in r_ensaio and len(criados) == n, f"no ensaio nada é agendado: {r_ensaio}")
os.environ.pop("AGENTEPESSOAL_ENSAIO")
esq = rn.esquema()
checa(esq["name"] == "reuniao" and {"acao", "evento_id", "titulo", "inicio"} <= set(esq["parameters"]["properties"]),
      "mesmo nome e parâmetros da ferramenta do A0")

rr = (H / "rotina_rodar.py").read_text()
checa("run_job(dict(job))" in rr and "trigger_job" not in rr.split('"""', 2)[2] and "rotina_rodar.py" in sh,
      "rodar à mão sem ligar a rotina (o run do cron liga a pausada)")
# --- 5. the gate script
pt = (H / "scripts" / "portao.py").read_text()
checa('"wakeAgent": False' in pt and "hermes-mcp:8765" in pt and "P.preparar" in pt, "portão: contrato wakeAgent do cron do Hermes")
checa('printf' in sh and 'portao_$u.py' in sh, "um embrulho do portão por rotina que tem portão")

if falhas:
    raise SystemExit("test_rotinas_hermes: " + "; ".join(falhas))
print("test_rotinas_hermes: ok")

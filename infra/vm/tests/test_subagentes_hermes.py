"""Tests of subagentes_hermes (infra/vm/hermes/plugins/agentepessoal): the Hermes always runs delegate_task in the
background and, through the API server (the phone bridge), only keeps the result for the NEXT turn (23/10, live: "as
soon as they finish I'll send it" and nothing came). A dispatch in a person's session is followed and, when the batch
ends, the bridge gets a request in THAT session (the new turn reads the kept result); routines and already-read
results are left alone.
Run from the repository root: python3 infra/vm/tests/test_subagentes_hermes.py"""
import importlib.util
import json
import sys
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
P = RAIZ / "infra" / "vm" / "hermes" / "plugins" / "agentepessoal"
falhas = []


def checa(cond, msg):
    if not cond:
        falhas.append(msg)


spec = importlib.util.spec_from_file_location("teste_subagentes", P / "subagentes_hermes.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
ponte = types.ModuleType("agentepessoal_ponte_a0")
ponte.login_da_sessao = lambda sessao: "ilia" if sessao.endswith("ilia") else "matheus"
sys.modules["agentepessoal_ponte_a0"] = ponte

# the hook: only a dispatched delegate_task of a person's session starts a follower
iniciadas = []
s.threading = types.SimpleNamespace(Thread=lambda target, args, daemon, name: types.SimpleNamespace(
    start=lambda: iniciadas.append(args)), Lock=s.threading.Lock)
despachado = json.dumps({"status": "dispatched", "mode": "background", "count": 2, "delegation_id": "deleg_abc"})
s.depois(tool_name="delegate_task", args={}, result=despachado, session_id="tgp1-matheus")
checa(iniciadas == [("deleg_abc", "matheus", "tgp1-matheus")], f"disparo seguido na sessão em que foi feito ({iniciadas})")
s.depois(tool_name="delegate_task", args={}, result=despachado, session_id="tgp1-matheus")
checa(len(iniciadas) == 1, "o mesmo lote não é seguido duas vezes")
s.depois(tool_name="delegate_task", args={}, result=json.dumps({"status": "dispatched", "delegation_id": "d2"}),
         session_id="cron_ab12cd34ef56_20261023_081700")
s.depois(tool_name="delegate_task", args={}, result=json.dumps({"results": []}), session_id="tg-matheus")
s.depois(tool_name="terminal", args={}, result=despachado, session_id="tg-matheus")
s.depois(tool_name="delegate_task", args={}, result="não é json", session_id="tg-matheus")
checa(len(iniciadas) == 1, "rotina, resultado na hora, outra ferramenta ou texto torto: nada")
s.depois(tool_name="delegate_task", args={}, result=json.dumps({"status": "dispatched", "delegation_id": "d3"}),
         session_id="tg-ilia")
checa(iniciadas[-1] == ("d3", "ilia", "tg-ilia"), "convidado: o aviso volta para ele")

# the follower: waits, then wakes that session once
relogio = [0.0]
estados = [{"state": "running"}, {"state": "running"}, {"state": "completed", "completed_at": 10, "delivery_state": "pending"}]
avisos = []
r = s.seguir("deleg_abc", "matheus", "tgp1-matheus", dormir=lambda t: relogio.__setitem__(0, relogio[0] + t),
             agora=lambda: relogio[0], estado_fn=lambda d: estados.pop(0), avisar_fn=lambda *a: avisos.append(a))
checa(r == "avisado" and len(avisos) == 1 and avisos[0][:2] == ("matheus", "tgp1-matheus") and "deleg_abc" in avisos[0][2],
      f"quando o lote termina, a sessão dele é acordada ({r}, {avisos})")
avisos.clear()
r = s.seguir("d", "matheus", "tg-matheus", dormir=lambda t: None, agora=lambda: 0,
             estado_fn=lambda d: {"state": "completed", "completed_at": 1, "delivery_state": "delivered"},
             avisar_fn=lambda *a: avisos.append(a))
checa(r == "já entregue" and not avisos, "ele escreveu antes e o turno já leu o resultado: não acorda de novo")
r = s.seguir("d", "matheus", "tg-matheus", dormir=lambda t: None, agora=lambda: 0, estado_fn=lambda d: None,
             avisar_fn=lambda *a: avisos.append(a))
checa(r == "sumiu" and not avisos, "registro sumido: nada")
relogio = [0.0]
r = s.seguir("d", "matheus", "tg-matheus", dormir=lambda t: relogio.__setitem__(0, relogio[0] + 600),
             agora=lambda: relogio[0], estado_fn=lambda d: {"state": "running"}, avisar_fn=lambda *a: avisos.append(a))
checa(r == "tempo esgotado" and not avisos, "lote que não termina em 3 h: desiste sem avisar")
checa(s.terminou({"state": "error"}) and not s.terminou({"state": "running"}) and not s.terminou(None),
      "terminou: erro conta, rodando não")

if falhas:
    raise SystemExit("test_subagentes_hermes: " + "; ".join(falhas))
print("test_subagentes_hermes: ok")

"""Desde a virada ao Hermes (23/10) as ferramentas do operador que falam com o A0 param com aviso (o A0 parado não
pode ser religado por engano) e dizem o equivalente no Hermes; com A0_LEGADO=1 (depois de voltar ao A0) seguem.
Rode da raiz: python3 infra/operador/tests/test_legado_a0.py"""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]  # infra/
falhas = []
LEGADAS = ("aprovar_pendente.py", "retomar_chat.py", "resetar_chat.py", "apagar_chat.py", "tarefa_atualizar.py",
           "tarefas_auxiliar.py", "resumo_novo.py", "rodar_testes.py", "rodar_testes_pro.py", "preset_sonnet.py",
           "mover_perfis_navegador.py")
amb = {k: v for k, v in os.environ.items() if k != "A0_LEGADO"}
for nome in LEGADAS:
    r = subprocess.run([sys.executable, str(RAIZ / "operador" / nome), "x"], capture_output=True, text=True, env=amb, timeout=60)
    if r.returncode != 3 or "LEGADO" not in r.stderr or "No lugar:" not in r.stderr:
        falhas.append(f"{nome}: devia parar com aviso de legado (rc={r.returncode}) {r.stderr[-200:]}")
r = subprocess.run([sys.executable, str(RAIZ / "operador" / "rotinas.py"), "aplicar", "x"], capture_output=True, text=True,
                   env=amb, timeout=60)
if r.returncode != 3 or "infra/vm/hermes/rotinas" not in r.stderr:
    falhas.append(f"rotinas.py aplicar: devia parar (as rotinas vivem no Hermes): {r.returncode} {r.stderr[-200:]}")
gancho = (RAIZ.parent / ".claude" / "hooks" / "cerebro_inicio.py").read_text()
if "docker exec agent-zero" in gancho or "/opt/agentepessoal/a0py /a0/usr/tmp_cerebro_inicio.py" not in gancho:
    falhas.append("o gancho de início lê o Segundo Cérebro pelo a0py (Hermes), não pelo A0 parado")
for f in falhas:
    print("FALHA", f)
print("legado_a0:", "ok" if not falhas else f"{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)

"""Rehearsal of the weekly content routine with a simulated date (11/11, Matheus: "Bom simular ele fazer só e você
checar a qualidade"). Only the operator turns it on, through the plugin's own ligar_ensaio()/desligar_ensaio(); it
turns itself off (at most 240 min). While it is on, the PLANNING (which week `propor_semana` fills, the briefing, the
agenda the routine reads) sees the simulated date; the redo loop, the Crítico, the videos and the publishing keep the
real clock, and what the Crítico approves is scheduled for real. Usage, from the repository root:
    python3 infra/operador/ensaio_conteudo.py ligar 2026-11-18T07:47 180 "<motivo>"
    python3 infra/operador/ensaio_conteudo.py ver
    python3 infra/operador/ensaio_conteudo.py desligar "<motivo>"
Then run the routine once: docker exec hermes python3 /opt/data/agentepessoal/rotina_rodar.py 4qfNuwRX
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def script(args: list) -> str:
    acao = args[0] if args else "ver"
    if acao == "ligar":
        motivo = args[3] if len(args) > 3 else "ensaio da rotina da semana"
        chamada = f"s.ligar_ensaio({json.dumps(args[1])}, {int(args[2]) if len(args) > 2 else 120}, {json.dumps(motivo)})"
    elif acao == "desligar":
        motivo = args[1] if len(args) > 1 else "fim do ensaio"
        chamada = f"s.desligar_ensaio({json.dumps(motivo)})"
    elif acao == "ver":
        motivo, chamada = "ver o ensaio", "{'ligado': bool(s.ensaio()), 'ensaio': s.ensaio()}"
    else:
        raise SystemExit("uso: ensaio_conteudo.py ligar <AAAA-MM-DDTHH:MM> [minutos] [motivo] | ver | desligar [motivo]")
    return f"""
import importlib.util as iu, json
x = iu.spec_from_file_location('s', '/a0/usr/plugins/conteudo/helpers/semana.py'); s = iu.module_from_spec(x); x.loader.exec_module(s)
s.c().AUTOR['quem'] = {json.dumps('operador: ' + motivo)}
print(json.dumps({chamada}, ensure_ascii=False, default=str))
"""


if __name__ == "__main__":
    b64 = base64.b64encode(script(sys.argv[1:]).encode()).decode()
    cmd = f"echo {b64} | base64 -d > /opt/a0/usr/tmp_ensaio.py && /opt/agentepessoal/a0py /a0/usr/tmp_ensaio.py; rm -f /opt/a0/usr/tmp_ensaio.py"
    sys.exit(subprocess.call([sys.executable, str(RAIZ / "infra" / "operador" / "vmcmd.py"), cmd]))

"""Cancels one pending @raiz.connect post on the VM through the plugin's own cancelar() (operator only; a published
post is never touched), so its day is free for agendar_conteudo.py. Usage, from the repository root:
    python3 infra/operador/cancelar_conteudo.py <id> "<motivo>"
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

item_id = sys.argv[1]
motivo = sys.argv[2] if len(sys.argv) > 2 else "cancelamento"
script = f"""
import importlib.util as iu, json, base64
s = iu.spec_from_file_location('c', '/a0/usr/plugins/conteudo/helpers/conteudo.py'); c = iu.module_from_spec(s); s.loader.exec_module(c)
c.AUTOR['quem'] = {json.dumps('operador: ' + motivo)}
print(json.dumps(c.cancelar({json.dumps(item_id)}, {json.dumps(motivo)}), ensure_ascii=False))
"""
b64 = base64.b64encode(script.encode()).decode()
cmd = f"echo {b64} | base64 -d > /opt/a0/usr/tmp_cancelar.py && /opt/agentepessoal/a0py /a0/usr/tmp_cancelar.py; rm -f /opt/a0/usr/tmp_cancelar.py"
sys.exit(subprocess.call([sys.executable, str(RAIZ / "infra" / "operador" / "vmcmd.py"), cmd]))

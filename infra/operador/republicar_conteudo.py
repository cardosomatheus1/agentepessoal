"""Puts a failed @raiz.connect post back in the queue (falhou → pendente), through the plugin's own tentar_de_novo(),
after the cause was fixed. The job loop publishes it on its next pass if it is still that post's day. Usage, from the
repository root:
    python3 infra/operador/republicar_conteudo.py <id do post> "<motivo>"
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

if len(sys.argv) < 3:
    sys.exit(__doc__)
item, motivo = sys.argv[1], sys.argv[2]
script = f"""
import importlib.util as iu, json
s = iu.spec_from_file_location('c', '/a0/usr/plugins/conteudo/helpers/conteudo.py'); c = iu.module_from_spec(s); s.loader.exec_module(c)
c.AUTOR['quem'] = {json.dumps('operador: ' + motivo)}
print(json.dumps(c.tentar_de_novo({json.dumps(item)}), ensure_ascii=False))
"""
b64 = base64.b64encode(script.encode()).decode()
cmd = f"echo {b64} | base64 -d > /opt/a0/usr/tmp_republicar.py && docker exec agent-zero python3 /a0/usr/tmp_republicar.py; rm -f /opt/a0/usr/tmp_republicar.py"
sys.exit(subprocess.call([sys.executable, str(RAIZ / "infra" / "operador" / "vmcmd.py"), cmd]))

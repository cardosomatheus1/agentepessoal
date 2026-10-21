"""Moves every pending @raiz.connect post on a day or later N days ahead, through the plugin's own adiar_a_partir()
(operator only; refuses if a moved post would land on a taken day). Usage, from the repository root:
    python3 infra/operador/adiar_conteudo.py AAAA-MM-DD [dias] "<motivo>"
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

data = sys.argv[1]
dias = int(sys.argv[2]) if len(sys.argv) > 3 else 1
motivo = sys.argv[-1] if len(sys.argv) > 2 else "remarcação"
script = f"""
import importlib.util as iu, json
s = iu.spec_from_file_location('c', '/a0/usr/plugins/conteudo/helpers/conteudo.py'); c = iu.module_from_spec(s); s.loader.exec_module(c)
c.AUTOR['quem'] = {json.dumps('operador: ' + motivo)}
print(json.dumps(c.adiar_a_partir({data!r}, {dias}), ensure_ascii=False))
"""
b64 = base64.b64encode(script.encode()).decode()
cmd = f"echo {b64} | base64 -d > /opt/a0/usr/tmp_adiar.py && docker exec agent-zero python3 /a0/usr/tmp_adiar.py; rm -f /opt/a0/usr/tmp_adiar.py"
sys.exit(subprocess.call([sys.executable, str(RAIZ / "infra" / "operador" / "vmcmd.py"), cmd]))

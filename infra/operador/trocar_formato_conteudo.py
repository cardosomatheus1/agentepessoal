"""Swaps the format and files of ONE pending @raiz.connect post on the VM, through the plugin's own trocar_formato()
(operator only; keeps id, day, hour, caption and state; saves a copy of agenda.json first). The file is
{"id", "tipo", "arquivos", "capa"?}. Usage, from the repository root:
    python3 infra/operador/trocar_formato_conteudo.py <arquivo>.json "<motivo>"
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

m = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
motivo = sys.argv[2] if len(sys.argv) > 2 else "troca de formato"
script = f"""
import importlib.util as iu, json, base64
s = iu.spec_from_file_location('c', '/a0/usr/plugins/conteudo/helpers/conteudo.py'); c = iu.module_from_spec(s); s.loader.exec_module(c)
c.AUTOR['quem'] = {json.dumps('operador: ' + motivo)}
m = json.loads(base64.b64decode({base64.b64encode(json.dumps(m).encode()).decode()!r}))
print(json.dumps(c.trocar_formato(m['id'], m['tipo'], m['arquivos'], m.get('capa', '')), ensure_ascii=False))
"""
b64 = base64.b64encode(script.encode()).decode()
cmd = f"echo {b64} | base64 -d > /opt/a0/usr/tmp_trocar_formato.py && /opt/agentepessoal/a0py /a0/usr/tmp_trocar_formato.py; rm -f /opt/a0/usr/tmp_trocar_formato.py"
sys.exit(subprocess.call([sys.executable, str(RAIZ / "infra" / "operador" / "vmcmd.py"), cmd]))

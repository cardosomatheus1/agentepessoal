"""Changes the day and/or caption of pending @raiz.connect posts on the VM, through the plugin's own replanejar()
(operator only, all or nothing, one post per day, captions without emoji). The file is a list of
{"id", "data"?, "legenda"?}. Usage, from the repository root:
    python3 infra/operador/replanejar_conteudo.py infra/vm/plugins/conteudo/agendas/<arquivo>.json "<motivo>"
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

mudancas = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
motivo = sys.argv[2] if len(sys.argv) > 2 else "replanejamento"
script = f"""
import importlib.util as iu, json, base64
s = iu.spec_from_file_location('c', '/a0/usr/plugins/conteudo/helpers/conteudo.py'); c = iu.module_from_spec(s); s.loader.exec_module(c)
c.AUTOR['quem'] = {json.dumps('operador: ' + motivo)}
print(json.dumps(c.replanejar(json.loads(base64.b64decode({base64.b64encode(json.dumps(mudancas).encode()).decode()!r}))), ensure_ascii=False))
"""
b64 = base64.b64encode(script.encode()).decode()
cmd = f"echo {b64} | base64 -d > /opt/a0/usr/tmp_replanejar.py && /opt/agentepessoal/a0py /a0/usr/tmp_replanejar.py; rm -f /opt/a0/usr/tmp_replanejar.py"
sys.exit(subprocess.call([sys.executable, str(RAIZ / "infra" / "operador" / "vmcmd.py"), cmd]))

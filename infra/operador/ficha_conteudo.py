"""Gives a scheduled @raiz.connect post the ficha it lacks (what it is and where its source files are), through the
plugin's own anotar_ficha() on the VM (validates, journals, and the Crítico judges the post again on the next pass).
Usage, from the repository root:
    python3 infra/operador/ficha_conteudo.py <id do post> infra/vm/plugins/conteudo/agendas/fichas/<id>.json "<motivo>"
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

if len(sys.argv) < 4 or not sys.argv[3].strip():
    raise SystemExit(__doc__)
item_id, ficha, motivo = sys.argv[1], json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")), sys.argv[3]
script = f"""
import importlib.util as iu, json, base64
s = iu.spec_from_file_location('c', '/a0/usr/plugins/conteudo/helpers/conteudo.py'); c = iu.module_from_spec(s); s.loader.exec_module(c)
c.AUTOR['quem'] = {json.dumps('operador: ' + motivo)}
ficha = json.loads(base64.b64decode({base64.b64encode(json.dumps(ficha).encode()).decode()!r}))
print(json.dumps(c.anotar_ficha({json.dumps(item_id)}, ficha, {json.dumps(motivo)}), ensure_ascii=False))
"""
b64 = base64.b64encode(script.encode()).decode()
cmd = (f"echo {b64} | base64 -d > /opt/a0/usr/tmp_ficha.py && /opt/agentepessoal/a0py /a0/usr/tmp_ficha.py; "
       "rm -f /opt/a0/usr/tmp_ficha.py")
sys.exit(subprocess.call([sys.executable, str(RAIZ / "infra" / "operador" / "vmcmd.py"), cmd]))

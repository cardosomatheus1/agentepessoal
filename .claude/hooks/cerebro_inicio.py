"""SessionStart hook of the operator's sessions on this repository: the session starts knowing Matheus's decisions in
force, the open fronts (where they stopped) and his open to-dos, read from the Segundo Cérebro on the VM
(infra/vm/plugins/cerebro/helpers/briefing.py `para_operador`).

21/10, Matheus asked that his decisions hold the same for the agent, the operator and the reviewers: until then a new
operator session knew only the repository rules and the conversation (e.g. "aprovar o áudio antes de gerar o vídeo"
was known to the agent, not to the operator). Silent on any failure (the session starts as before)."""

import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
INICIO, FIM = "<<<CEREBRO>>>", "<<<FIM-CEREBRO>>>"
SCRIPT = (
    "import importlib.util as iu\n"
    "s = iu.spec_from_file_location('cerebro_modulos', '/a0/usr/plugins/cerebro/helpers/modulos.py')\n"
    "m = iu.module_from_spec(s); s.loader.exec_module(m)\n"
    "texto = m.m('briefing').para_operador(m)\n"
    # the markers are built in pieces: a traceback quoting this line must never look like a finished block
    f"print({INICIO[:5]!r} + {INICIO[5:]!r}); print(texto); print({FIM[:5]!r} + {FIM[5:]!r})\n"
)


def extrair(saida: str) -> str:
    if INICIO not in saida or FIM not in saida:
        return ""
    return saida.split(INICIO, 1)[1].split(FIM, 1)[0].strip()


def ler_da_vm(timeout: int = 40) -> str:
    import base64

    b64 = base64.b64encode(SCRIPT.encode()).decode()
    cmd = (f"echo {b64} | base64 -d > /opt/a0/usr/tmp_cerebro_inicio.py && "
           "docker exec agent-zero python3 /a0/usr/tmp_cerebro_inicio.py; rm -f /opt/a0/usr/tmp_cerebro_inicio.py")
    r = subprocess.run([sys.executable, str(RAIZ / "infra" / "operador" / "vmcmd.py"), cmd], cwd=str(RAIZ),
                       capture_output=True, text=True, timeout=timeout)
    return extrair(r.stdout)


def main() -> None:
    if os.environ.get("CEREBRO_OPERADOR", "1") == "0":
        return
    texto = ler_da_vm()
    if texto:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": texto}},
                         ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass

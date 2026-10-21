"""Send Matheus a notice on his phone from an operator session (the nightly fix session's summary), through the same
bridge the agent uses (plugins/whatsapp/helpers/ponte.py), as a "progresso" notice: held during his quiet hours and
delivered together in the morning.

Usage, from the repository root:  python3 infra/operador/avisar_matheus.py "texto"   (or the text on stdin)"""

import base64
import subprocess
import sys
from pathlib import Path

PONTE = "/a0/usr/plugins/whatsapp/helpers/ponte.py"


def comando(texto: str, tipo: str = "progresso") -> str:
    """The VM command: the text goes base64, so no quoting can break it or run anything."""
    t = base64.b64encode(texto.encode("utf-8")).decode()
    py = (f"import base64, importlib.util; s = importlib.util.spec_from_file_location('ponte', '{PONTE}'); "
          f"m = importlib.util.module_from_spec(s); s.loader.exec_module(m); "
          f"print(m.enviar('matheus', base64.b64decode('{t}').decode('utf-8'), tipo='{tipo}', reenviar=True) or 'enviado')")
    return f"docker exec agent-zero /opt/venv-a0/bin/python -c \"{py}\""


def main(argv: list) -> int:
    texto = " ".join(argv).strip() or sys.stdin.read().strip()
    if not texto:
        print("nada a enviar")
        return 1
    vm = Path(__file__).resolve().parent / "vmcmd.py"
    r = subprocess.run([sys.executable, str(vm), comando(texto)], capture_output=True, text=True)
    print(r.stdout.strip())
    return 0 if "enviado" in r.stdout else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

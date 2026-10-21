"""SessionStart hook of the operator's sessions on this repository: the session starts knowing Matheus's decisions in
force, the open fronts (where they stopped) and his open to-dos, read from the Segundo Cérebro on the VM
(infra/vm/plugins/cerebro/helpers/briefing.py `para_operador`).

21/10, Matheus asked that his decisions hold the same for the agent, the operator and the reviewers: until then a new
operator session knew only the repository rules and the conversation (e.g. "aprovar o áudio antes de gerar o vídeo"
was known to the agent, not to the operator). Silent on any failure (the session starts as before)."""

import json
import os
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


def ler_da_vm(timeout: int = 45) -> str:
    """Runs the script on the VM through SSM (like infra/operador/vmcmd.py, which keeps only the last 6,000 characters
    of the output: too little for the block)."""
    import base64
    import time

    import boto3

    ssm = boto3.client("ssm", region_name="us-east-1")
    iid = os.environ.get("VM_ID", "i-0498b4f39560b01a9")
    b64 = base64.b64encode(SCRIPT.encode()).decode()
    cmd = (f"echo {b64} | base64 -d > /opt/a0/usr/tmp_cerebro_inicio.py && "
           "docker exec agent-zero python3 /a0/usr/tmp_cerebro_inicio.py; rm -f /opt/a0/usr/tmp_cerebro_inicio.py")
    cid = ssm.send_command(InstanceIds=[iid], DocumentName="AWS-RunShellScript", Parameters={"commands": [cmd]},
                           TimeoutSeconds=60)["Command"]["CommandId"]
    fim = time.time() + timeout
    while time.time() < fim:
        time.sleep(2)
        try:
            r = ssm.get_command_invocation(CommandId=cid, InstanceId=iid)
        except ssm.exceptions.InvocationDoesNotExist:
            continue
        if r["Status"] not in ("Pending", "InProgress", "Delayed"):
            return extrair(r.get("StandardOutputContent") or "")
    return ""


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

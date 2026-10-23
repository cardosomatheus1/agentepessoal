"""A virada do agente para o Hermes e a volta ao A0 (migração, fase 8; docs/MIGRACAO_HERMES.md), pelo operador:

    python3 infra/operador/virada.py estado
    python3 infra/operador/virada.py virar  --motivo "..."    # o Hermes passa a ser o agente; o A0 fica parado, intacto
    python3 infra/operador/virada.py voltar --motivo "..."    # tudo de volta ao A0 em minutos (o Hermes volta ao ensaio)

Roda /opt/hermes/virada.sh na VM (instalado pelo implantar.py --hermes); acorda a VM se estiver hibernando."""

import base64
import subprocess
import sys
from pathlib import Path

VM = "i-0498b4f39560b01a9"


def comando(acao: str, motivo: str) -> str:
    m = base64.b64encode(motivo.encode("utf-8")).decode()
    return (f"touch /var/lib/agentepessoal/last-activity; "
            f"bash /opt/hermes/virada.sh {acao} \"operador: $(echo {m} | base64 -d)\"")


def main(argv: list) -> int:
    if not argv or argv[0] not in ("estado", "virar", "voltar"):
        print(__doc__)
        return 2
    acao = argv[0]
    motivo = argv[argv.index("--motivo") + 1] if "--motivo" in argv else ""
    if acao != "estado" and not motivo:
        print("diga o motivo com --motivo \"...\" (fica no histórico da chave)")
        return 2
    subprocess.run(["aws", "ec2", "start-instances", "--region", "us-east-1", "--instance-ids", VM],
                   capture_output=True)
    vm = Path(__file__).resolve().parent / "vmcmd.py"
    r = subprocess.run([sys.executable, str(vm), comando(acao, motivo or "estado")], capture_output=True, text=True)
    print(r.stdout.strip())
    ok = {"estado": "CHAVE", "virar": "VIRADA_OK", "voltar": "VOLTA_OK"}[acao]
    return 0 if ok in r.stdout else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

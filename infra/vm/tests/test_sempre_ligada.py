"""A VM fica ligada (24/10, Matheus: "toda hora cai o agente e o OpenCode, não consegue rodar 15 min"): a hibernação por
ociosidade (watchdog.sh) e a hibernação do "Desligar" (hibernate.sh) só com HIBERNAR=1; o setup.sh não religa o timer;
o OpenCode tem teto e volta sempre; o túnel dele não reinicia junto. Sem tocar na VM (comandos falsos num PATH próprio).
Run from the repository root: python3 infra/vm/tests/test_sempre_ligada.py"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
VM = RAIZ / "infra" / "vm"


def falsos(pasta: Path) -> Path:
    """logger/aws/shutdown/backup falsos que só anotam a chamada em chamadas.txt."""
    bin_ = pasta / "bin"
    bin_.mkdir(parents=True)
    for nome in ("logger", "aws", "shutdown", "curl"):
        f = bin_ / nome
        f.write_text(f'#!/bin/sh\necho "{nome} $*" >> "{pasta}/chamadas.txt"\nexit 0\n')
        f.chmod(0o755)
    base = pasta / "base"
    (base / "venv" / "bin").mkdir(parents=True)
    (base / "backup.sh").write_text(f'#!/bin/sh\necho "backup" >> "{pasta}/chamadas.txt"\n')
    (base / "backup.sh").chmod(0o755)
    py = base / "venv" / "bin" / "python"
    py.write_text(f'#!/bin/sh\necho "despertar" >> "{pasta}/chamadas.txt"\n')
    py.chmod(0o755)
    return bin_


def rodar(script: str, pasta: Path, **env) -> tuple[int, str]:
    bin_ = falsos(pasta) if not (pasta / "bin").exists() else pasta / "bin"
    (pasta / "chamadas.txt").write_text("")
    amb = {"PATH": f"{bin_}:/usr/bin:/bin", "BASE": str(pasta / "base"), "AWS": str(bin_ / "aws"), "IID": "i-1", **env}
    r = subprocess.run(["bash", str(VM / script)], env=amb, capture_output=True, text=True, timeout=60)
    return r.returncode, (pasta / "chamadas.txt").read_text()


def main() -> int:
    falhas = []

    def checa(ok, msg):
        if not ok:
            falhas.append(msg)

    tmp = Path(tempfile.mkdtemp(prefix="sempre-ligada-"))
    # 1. watchdog.sh: sem HIBERNAR=1 sai antes de olhar qualquer coisa (nem hiberna, nem anota nada)
    rc, ch = rodar("watchdog.sh", tmp / "w0", IDLE_MINUTES="0")
    checa(rc == 0 and ch == "", f"watchdog sem HIBERNAR: devia sair calado: rc={rc} {ch!r}")
    rc, ch = rodar("watchdog.sh", tmp / "w2", IDLE_MINUTES="0", HIBERNAR="0")
    checa(rc == 0 and ch == "", f"watchdog com HIBERNAR=0: devia sair calado: rc={rc} {ch!r}")

    # 2. hibernate.sh ("Desligar" na página): backup + desligamento normal; com HIBERNAR=1, hiberna como antes
    rc, ch = rodar("hibernate.sh", tmp / "h0", HIBERNAR="0")
    paradas = [l for l in ch.splitlines() if "ec2 stop-instances" in l]
    checa(rc == 0 and ch.startswith("backup") and len(paradas) == 1 and "--hibernate" not in paradas[0]
          and "shutdown" not in ch, f"hibernate.sh sem HIBERNAR: desliga normal: {ch!r}")
    checa("sem hibernar" in ch, f"hibernate.sh sem HIBERNAR: anota no log: {ch!r}")
    rc, ch = rodar("hibernate.sh", tmp / "h1", HIBERNAR="1")
    paradas = [l for l in ch.splitlines() if "ec2 stop-instances" in l]
    checa(len(paradas) == 1 and "--hibernate" in paradas[0], f"hibernate.sh com HIBERNAR=1: hiberna: {ch!r}")

    # 3. setup.sh: o timer da hibernação só se liga com HIBERNAR=1; senão é desligado (um --update não o religa)
    setup = (VM / "setup.sh").read_text()
    habilita = [l for l in setup.splitlines() if "systemctl enable" in l or "systemctl start" in l]
    soltos = [l for l in habilita if "agentepessoal-watchdog.timer" in l and "enable --now" not in l]
    checa(not soltos, f"setup.sh liga o timer da hibernação fora do HIBERNAR=1: {soltos}")
    i = setup.index("systemctl enable --now agentepessoal-watchdog.timer")
    checa('if [ "$HIBERNAR" = 1 ]' in setup[i - 80:i] and "disable --now agentepessoal-watchdog.timer" in setup[i:i + 200],
          "setup.sh: enable só dentro do HIBERNAR=1 e disable no else")
    checa('HIBERNAR="${HIBERNAR:-0}"' in setup, "setup.sh: HIBERNAR padrão 0")
    checa("agentepessoal-vigia-rede.timer" in setup and "opencodemobile.service opencodemobile-cloudflare" in setup,
          "setup.sh instala o vigia da rede e a unidade do OpenCode")
    tpl = (VM / "user-data.sh.tpl").read_text()
    checa("HIBERNAR={{HIBERNAR}}" in tpl, "user-data grava HIBERNAR no /etc/agentepessoal.env")

    # 4. OpenCode: volta sempre, com teto de memória/CPU; o túnel não reinicia junto (o endereço não muda)
    oc = (VM / "unidades" / "opencodemobile.service").read_text()
    for linha in ("Restart=always", "MemoryHigh=4G", "MemoryMax=5G", "CPUQuota=250%", "OOMScoreAdjust=500",
                  "StartLimitIntervalSec=0"):
        checa(linha in oc.splitlines(), f"opencodemobile.service sem {linha}")
    tun = (VM / "unidades" / "opencodemobile-cloudflare.service").read_text().splitlines()
    checa(not any(l.startswith("Requires=") for l in tun) and any("opencodemobile.service" in l and l.startswith("Wants=")
                                                                   for l in tun), f"túnel do OpenCode: Wants, não Requires: {tun}")
    vr = (VM / "unidades" / "agentepessoal-vigia-rede.service").read_text()
    checa("estabilidade.py rede" in vr, "vigia da rede chama estabilidade.py rede")

    print(f"TESTES {'ok' if not falhas else 'FALHOU'}")
    for f in falhas:
        print("  ✗", f)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

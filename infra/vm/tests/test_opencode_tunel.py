"""infra/vm/opencode_tunel.sh (23/10): endereço fixo com o token no cofre, túnel rápido sem ele; o endereço do
momento vai ao SSM; o token nunca na linha de comando. 24/10: o endereço fixo da AWS (url-aws) tem a preferência
quando responde; o túnel só volta ao celular depois de 3 falhas seguidas do da AWS. aws/systemctl/journalctl/setpriv falsos, cofre temporário.
Run from the repository root: python3 infra/vm/tests/test_opencode_tunel.py"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
SCRIPT = RAIZ / "infra" / "vm" / "opencode_tunel.sh"


def preparar(tmp: Path, cofre: dict, journal: str) -> dict:
    bins = tmp / "bin"
    bins.mkdir()
    reg = tmp / "chamadas.log"
    (tmp / "journal.txt").write_text(journal)
    falsos = {
        "aws": 'echo "aws $*" >> "$REG"; case "$*" in *get-parameter*url-aws*) cat "$TMP/aws.txt" 2>/dev/null;; '
               '*get-parameter*) cat "$TMP/ssm.txt" 2>/dev/null;; *put-parameter*) '
               'v=$(echo "$*" | sed "s/.*--value \\([^ ]*\\).*/\\1/"); echo "$v" > "$TMP/ssm.txt";; esac',
        "systemctl": 'echo "systemctl $*" >> "$REG"; case "$*" in show*) echo "Fri 2026-10-23 22:10:05 UTC";; esac',
        "journalctl": 'echo "journalctl $*" >> "$REG"; cat "$TMP/journal.txt"',
        "logger": 'echo "logger $*" >> "$REG"',
        "curl": 'echo "curl $*" >> "$REG"; cat "$TMP/curl.txt" 2>/dev/null || printf 000',
        "setpriv": 'echo "setpriv $* TOKEN=${TUNNEL_TOKEN:-}" >> "$REG"',
    }
    for nome, corpo in falsos.items():
        f = bins / nome
        f.write_text(f"#!/bin/bash\n{corpo}\n")
        f.chmod(0o755)
    (tmp / "cofre.json").write_text(json.dumps(cofre))
    av = bins / "avisar"
    av.write_text('#!/bin/bash\necho "avisar $*" >> "$REG"\n')
    av.chmod(0o755)
    return {**os.environ, "AVISAR": str(av), "PATH": f"{bins}:{os.environ['PATH']}", "REG": str(reg), "TMP": str(tmp),
            "COFRE": str(tmp / "cofre.json"), "AWS": str(bins / "aws"), "CURL": str(bins / "curl"),
            "ESTADO": str(tmp / "estado")}


def rodar(tmp: Path, env: dict, *args) -> tuple[int, str]:
    r = subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=30)
    reg = tmp / "chamadas.log"
    return r.returncode, reg.read_text() if reg.exists() else ""


def main() -> int:
    falhas = []

    def checa(ok, msg):
        if not ok:
            falhas.append(msg)

    rapido = "INF |  https://abc-def-ghi.trycloudflare.com  |\n"

    # 1. sem token: túnel rápido, endereço do journal desde que o túnel subiu vai ao SSM
    tmp = Path(tempfile.mkdtemp(prefix="octun-"))
    env = preparar(tmp, {"OUTRA": "x"}, rapido)
    rc, log = rodar(tmp, env, "publicar")
    checa(rc == 0 and "put-parameter" in log and (tmp / "ssm.txt").read_text().strip() == "https://abc-def-ghi.trycloudflare.com",
          f"rápido publica: rc={rc} {log}")
    checa('--since Fri 2026-10-23 22:10:05 UTC' in log, f"journal só desde o início do túnel: {log}")
    checa("systemctl restart" not in log, "sem token não reinicia nada")
    rc, log2 = rodar(tmp, env, "publicar")
    checa(log2.count("put-parameter") == 1, "mesmo endereço: não regrava o SSM")
    checa(log2.count("avisar https://abc-def-ghi.trycloudflare.com") == 1,
          f"endereço novo vai ao Telegram uma vez só (Matheus 24/10): {log2}")
    rc, log = rodar(tmp, env, "rodar")
    checa("--url http://127.0.0.1:4096" in log and "--reuid=opencodemobile" in log and "TOKEN=\n" in log,
          f"rodar sem token = túnel rápido como opencodemobile: {log}")

    # 2. token chega ao cofre com o túnel rápido no ar: reinicia para o fixo e publica o endereço fixo
    tmp = Path(tempfile.mkdtemp(prefix="octun-"))
    env = preparar(tmp, {"CLOUDFLARE_TUNEL_OPENCODE": "eyJhIjoi-segredo"}, rapido)
    rc, log = rodar(tmp, env, "publicar")
    checa("systemctl restart opencodemobile-cloudflare.service" in log, f"troca para o fixo: {log}")
    checa((tmp / "ssm.txt").read_text().strip() == "https://opencode.raizconnect.com.br", f"endereço padrão: {log}")

    # 3. rodar com token: túnel nomeado, token pelo ambiente e nunca nos argumentos
    tmp = Path(tempfile.mkdtemp(prefix="octun-"))
    env = preparar(tmp, {"CLOUDFLARE_TUNEL_OPENCODE": "eyJhIjoi-segredo", "OPENCODE_ENDERECO": "https://oc.exemplo.com.br/"}, "")
    rc, log = rodar(tmp, env, "rodar")
    linha = [l for l in log.splitlines() if l.startswith("setpriv")][0]
    checa("tunnel --no-autoupdate run" in linha and linha.endswith("TOKEN=eyJhIjoi-segredo"), f"nomeado: {linha}")
    checa("eyJhIjoi-segredo" not in linha.split(" TOKEN=")[0], "token fora dos argumentos")
    checa((tmp / "ssm.txt").read_text().strip() == "https://oc.exemplo.com.br", f"endereço do cofre: {log}")
    checa("eyJhIjoi-segredo" not in "".join(l for l in log.splitlines() if not l.startswith("setpriv")), "token fora dos logs")

    # 4. endereço fixo da AWS (24/10): respondendo (401 sem senha), é ele que vai ao SSM e ao Telegram, mesmo com o
    # túnel rápido no ar; o teste de vida é /api/session no próprio endereço
    aws = "https://d1abc2def3.cloudfront.net"
    tmp = Path(tempfile.mkdtemp(prefix="octun-"))
    env = preparar(tmp, {}, rapido)
    (tmp / "aws.txt").write_text(aws + "\n")
    rodar(tmp, env, "publicar")  # túnel rápido publicado antes
    # recém-criado e ainda sem responder (24/10: a distribuição levou 5 min): não vai ao celular antes de responder
    (tmp / "curl.txt").write_text("000")
    rc, log = rodar(tmp, env, "publicar")
    checa((tmp / "ssm.txt").read_text().strip().endswith("trycloudflare.com") and f"avisar {aws}" not in log
          and "reserva" not in log, f"AWS que ainda não respondeu não é publicado: {log}")
    (tmp / "curl.txt").write_text("401")
    rc, log = rodar(tmp, env, "publicar")
    checa(rc == 0 and (tmp / "ssm.txt").read_text().strip() == aws, f"AWS publicado: rc={rc} {log}")
    checa(f"curl -s -o /dev/null -w %{{http_code}} -m 15 --retry 1 {aws}/api/session" in log, f"teste de vida: {log}")
    checa(log.count(f"avisar {aws}") == 1 and "reserva" not in log, f"aviso do fixo, uma vez: {log}")
    # 5. AWS falhando: 2 minutos seguem no da AWS (nada muda nem é avisado); no 3º vai a reserva, avisada como provisória
    (tmp / "curl.txt").write_text("502")
    for _ in range(2):
        rc, log = rodar(tmp, env, "publicar")
    checa((tmp / "ssm.txt").read_text().strip() == aws and log.count(f"avisar {aws}") == 1 and "reserva" not in log,
          f"tropeço não troca: {log}")
    rc, log = rodar(tmp, env, "publicar")
    checa((tmp / "ssm.txt").read_text().strip() == "https://abc-def-ghi.trycloudflare.com", f"3ª falha vai à reserva: {log}")
    checa("avisar https://abc-def-ghi.trycloudflare.com reserva" in log, f"aviso de provisório: {log}")
    # 6. AWS volta: o fixo volta ao SSM e ao Telegram, e o contador zera
    (tmp / "curl.txt").write_text("401")
    rc, log = rodar(tmp, env, "publicar")
    checa((tmp / "ssm.txt").read_text().strip() == aws and log.count(f"avisar {aws}") == 2, f"fixo de volta: {log}")
    checa(not (tmp / "estado" / "opencode-aws-falhas").exists(), "contador zerado")
    # 7. endereço da AWS inválido no SSM: ignorado, sem curl
    tmp = Path(tempfile.mkdtemp(prefix="octun-"))
    env = preparar(tmp, {}, rapido)
    (tmp / "aws.txt").write_text("None\n")
    rc, log = rodar(tmp, env, "publicar")
    checa("curl " not in log and (tmp / "ssm.txt").read_text().strip().endswith("trycloudflare.com")
          and "reserva" not in log, f"sem AWS = como antes: {log}")

    rc, _ = rodar(tmp, env, "outra")
    checa(rc == 64, "ação desconhecida")
    print(f"TESTES {'ok' if not falhas else 'FALHOU'}")
    for f in falhas:
        print("  ✗", f)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

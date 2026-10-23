"""One-off (12/10 review): move the agent's browser profiles out of the container's own layer to /opt/a0/usr/navegador,
so the logins (Instagram, Google, Meta) survive recreating the container. Usage, from the repository root:

    python3 infra/operador/mover_perfis_navegador.py [--mesmo-com-rodada]

Stops the container (60 s grace), copies the profiles out (with the browser closed its databases are consistent) and
starts it again. On start, plugin navegador_por_pessoa points /a0/tmp/browser/sessions at the copy and keeps the old
folder aside (sessions.antes-*), never deleting it. Refuses while a scheduled round is running (unless
--mesmo-com-rodada), when backup.sh would upload the profiles to S3, or without disk space."""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import legado_a0; legado_a0.parar("mover_perfis_navegador.py", "feito em 12/10; o navegador do Hermes usa o perfil por navegador.sh")
import sys
import time

import boto3

VM = "i-0498b4f39560b01a9"
FORA = "/opt/a0/usr/navegador"
ssm = boto3.client("ssm", region_name="us-east-1")


def vm(comando: str, timeout: int = 600) -> str:
    cid = ssm.send_command(InstanceIds=[VM], DocumentName="AWS-RunShellScript",
                           Parameters={"commands": [comando]}, TimeoutSeconds=timeout)["Command"]["CommandId"]
    for _ in range(timeout // 3):
        time.sleep(3)
        try:
            r = ssm.get_command_invocation(CommandId=cid, InstanceId=VM)
        except ssm.exceptions.InvocationDoesNotExist:
            continue
        if r["Status"] not in ("Pending", "InProgress", "Delayed"):
            return (r["StandardOutputContent"] + r["StandardErrorContent"]).strip()
    raise SystemExit("a VM não respondeu a tempo")


def main() -> None:
    conferir = vm(
        "python3 -c \"import json; t=json.load(open('/opt/a0/usr/scheduler/tasks.json'))['tasks']; "
        "print('RODANDO', [x['name'] for x in t if x.get('state')=='running'])\"; "
        "grep -q 'navegador/' /opt/agentepessoal/backup.sh && echo BACKUP_OK; "
        f"[ -e {FORA}/sessions ] && echo JA_COPIADO; "
        "docker exec agent-zero readlink /a0/tmp/browser/sessions && echo JA_LIGADO; "
        "echo LIVRE_MB $(df -m --output=avail /opt/a0/usr | tail -1); "
        "echo PERFIS_MB $(docker exec agent-zero du -sm /a0/tmp/browser/sessions | cut -f1)")
    print(conferir)
    if "JA_LIGADO" in conferir:
        raise SystemExit("os perfis já estão fora do contêiner: nada a fazer.")
    if "BACKUP_OK" not in conferir:
        raise SystemExit("implante antes o backup.sh que deixa navegador/ fora do S3: "
                         "python3 infra/operador/implantar.py --host backup.sh")
    rodando = conferir.split("RODANDO", 1)[1].splitlines()[0].strip()
    if rodando != "[]" and "--mesmo-com-rodada" not in sys.argv:
        raise SystemExit(f"rodada em andamento ({rodando}): tente de novo entre as rodadas.")
    livre = int(conferir.split("LIVRE_MB")[1].split()[0])
    perfis = int(conferir.split("PERFIS_MB")[1].split()[0])
    if "JA_COPIADO" not in conferir and livre < perfis * 2 + 2048:
        raise SystemExit(f"pouco disco: {livre} MB livres para {perfis} MB de perfis.")
    copiar = ("true" if "JA_COPIADO" in conferir else
              f"mkdir -p {FORA} && (docker cp agent-zero:/a0/tmp/browser/sessions {FORA}/ && echo COPIADO "
              f"|| {{ rm -rf {FORA}/sessions; echo COPIA_FALHOU; }})")
    print(vm(f"docker stop -t 60 agent-zero >/dev/null && echo PARADO; {copiar}; "
             "docker start agent-zero >/dev/null && echo INICIADO; "
             "for i in $(seq 60); do docker exec agent-zero curl -s -o /dev/null -w '%{http_code}' "
             "http://127.0.0.1:80/ 2>/dev/null | grep -q 200 && break; sleep 5; done; "
             "for i in $(seq 24); do docker exec agent-zero readlink /a0/tmp/browser/sessions && break; sleep 5; done; "
             "docker logs --since 10m agent-zero 2>&1 | grep -a 'perfis do navegador' | tail -3; "
             f"du -sm {FORA}/sessions 2>/dev/null"))


if __name__ == "__main__":
    main()

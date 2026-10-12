"""The only way to put a plugin (or skill), or a host script, on the agent VM. Usage, from the repository root:

    python3 infra/operador/implantar.py prospeccao [--skill prospeccao-instagram] [--forcar]
    python3 infra/operador/implantar.py --host memguard.sh [--reiniciar agentepessoal-ponte.service] [--forcar]

Why (11/10): two Claude sessions deployed the same plugin over each other and one edited the live data by hand; a
reply lock stayed on and the only message to a lead was deleted. Rules enforced here:
1. Only what is committed AND pushed goes (the copy comes from `git archive HEAD`, never from the working tree).
2. The VM keeps the commit it is running (.versao). If that commit is not in this checkout's history, someone else
   deployed something newer: refuse (git pull first). --forcar only when the person says so.
3. The plugin's tests (tests/suite.py, when there is one) run on a staging copy on the VM BEFORE the live copy is
   replaced; a failing test stops the deploy and the live plugin is untouched.
"""

import io
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import boto3

RAIZ = Path(__file__).resolve().parents[2]
BUCKET = "agentepessoal-backup-964862484412"
VM = "i-0498b4f39560b01a9"
ssm = boto3.client("ssm", region_name="us-east-1")


def sh(*cmd: str) -> str:
    return subprocess.run(cmd, cwd=RAIZ, check=True, capture_output=True, text=True).stdout.strip()


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


# host scripts installed by setup.sh in /opt/agentepessoal (12/10 review: they were copied to the VM by hand)
HOST_ARQUIVOS = ("bedrock_proxy.py", "report_url.py", "watchdog.sh", "memguard.sh", "backup.sh", "hibernate.sh",
                 "entrada.sh", "credenciais_meta.py", "ponte_whatsapp.py", "proximo_despertar.py", "agent_tools.sh")


def _conferir_git(caminhos: list) -> str:
    sujo = sh("git", "status", "--porcelain", *caminhos)
    if sujo:
        raise SystemExit(f"há mudanças não commitadas:\n{sujo}\nCommite e faça push antes de implantar.")
    ramo = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    sh("git", "fetch", "-q", "origin", ramo)
    head, remoto = sh("git", "rev-parse", "HEAD"), sh("git", "rev-parse", f"origin/{ramo}")
    if head != remoto:
        raise SystemExit(f"HEAD ({head[:8]}) difere de origin/{ramo} ({remoto[:8]}): faça pull/push antes.")
    return head


def host(args: list) -> None:
    """A host script: committed and pushed, syntax-checked on the VM before it replaces the live one, version kept."""
    arquivo = args[args.index("--host") + 1] if len(args) > args.index("--host") + 1 else ""
    if arquivo not in HOST_ARQUIVOS:
        raise SystemExit(f"script de host desconhecido: {arquivo!r} (conhecidos: {', '.join(HOST_ARQUIVOS)})")
    caminho = f"infra/vm/{arquivo}"
    head = _conferir_git([caminho])
    versao = f"/opt/agentepessoal/.versao-{arquivo}"
    no_ar = vm(f"cat {versao} 2>/dev/null | head -1").split(" ")[0]
    if no_ar and "--forcar" not in args and subprocess.run(["git", "merge-base", "--is-ancestor", no_ar, head], cwd=RAIZ).returncode:
        raise SystemExit(f"a VM roda {arquivo} de {no_ar[:8]}, que não está no seu histórico: faça git pull (ou --forcar).")
    pacote = subprocess.run(["git", "archive", "--format=tar.gz", "HEAD", caminho], cwd=RAIZ, check=True, capture_output=True).stdout
    chave = f"tmp/implantar-host-{arquivo}-{head[:8]}.tgz"
    boto3.client("s3", region_name="us-east-1").put_object(Bucket=BUCKET, Key=chave, Body=pacote)
    checar = f"bash -n {{f}}" if arquivo.endswith(".sh") else "python3 -m py_compile {f}"
    unidade = args[args.index("--reiniciar") + 1] if "--reiniciar" in args else ""
    estagio = "/tmp/implantar-host"
    saida = vm(f"rm -rf {estagio} && mkdir -p {estagio} && aws s3 cp --quiet s3://{BUCKET}/{chave} - | tar xz -C {estagio} && "
               f"{checar.format(f=f'{estagio}/{caminho}')} && echo SINTAXE_OK && "
               f"install -m 755 {estagio}/{caminho} /opt/agentepessoal/{arquivo} && "
               f"echo '{head} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}' > {versao} && cat {versao}"
               + (f" && systemctl restart {unidade} && systemctl is-active {unidade}" if unidade else ""))
    print(saida[-800:])
    if "SINTAXE_OK" not in saida:
        raise SystemExit("o script não passou na conferência de sintaxe: nada foi trocado.")
    if head not in saida:
        raise SystemExit("a troca falhou depois da conferência: veja a saída acima.")
    print(f"implantado no host: {arquivo} @ {head[:8]}")


def main() -> None:
    args = sys.argv[1:]
    if "--host" in args:
        return host(args)
    if not args or args[0].startswith("-"):
        raise SystemExit(__doc__)
    plugin, forcar = args[0], "--forcar" in args
    skill = args[args.index("--skill") + 1] if "--skill" in args else ""
    caminho = f"infra/vm/plugins/{plugin}"
    if not (RAIZ / caminho).is_dir():
        raise SystemExit(f"plugin inexistente: {caminho}")

    # 1. committed and pushed
    sujo = sh("git", "status", "--porcelain", caminho, *( [f"infra/vm/skills/{skill}"] if skill else []))
    if sujo:
        raise SystemExit(f"há mudanças não commitadas:\n{sujo}\nCommite e faça push antes de implantar.")
    ramo = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    sh("git", "fetch", "-q", "origin", ramo)
    head, remoto = sh("git", "rev-parse", "HEAD"), sh("git", "rev-parse", f"origin/{ramo}")
    if head != remoto:
        raise SystemExit(f"HEAD ({head[:8]}) difere de origin/{ramo} ({remoto[:8]}): faça pull/push antes.")

    # 2. the VM is not running something newer from another session
    no_ar = vm(f"cat /opt/a0/usr/plugins/{plugin}/.versao 2>/dev/null | head -1").split(" ")[0]
    if no_ar and not forcar:
        conhecido = subprocess.run(["git", "merge-base", "--is-ancestor", no_ar, head], cwd=RAIZ).returncode == 0
        if not conhecido:
            raise SystemExit(f"a VM roda {no_ar[:8]}, que não está no seu histórico: outra sessão implantou algo mais "
                             "novo. Faça git pull, junte e tente de novo (ou --forcar se o Matheus mandar).")

    # package from git, not from the working tree
    pacote = io.BytesIO(subprocess.run(["git", "archive", "--format=tar.gz", "HEAD", caminho]
                                       + ([f"infra/vm/skills/{skill}"] if skill else []),
                                       cwd=RAIZ, check=True, capture_output=True).stdout)
    chave = f"tmp/implantar-{plugin}-{head[:8]}.tgz"
    boto3.client("s3", region_name="us-east-1").put_object(Bucket=BUCKET, Key=chave, Body=pacote.getvalue())

    # 3. staging copy + tests, then swap
    estagio = f"/tmp/implantar-{plugin}"
    teste = (f"docker cp {estagio}/{caminho} agent-zero:/tmp/estagio-{plugin} && "
             f"docker exec agent-zero sh -c 'cd /a0 && /opt/venv-a0/bin/python - <<\"PY\"\n"
             "import asyncio, importlib.util\n"
             f"s = importlib.util.spec_from_file_location(\"estagio\", \"/tmp/estagio-{plugin}/tests/suite.py\")\n"
             "m = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
             "r = asyncio.run(m.Suite().rodar(\"\"))\n"
             "[print(\"FALHA\", x[\"teste\"], x.get(\"erro\", \"\")[:200]) for x in r[\"resultados\"] if not x[\"ok\"]]\n"
             "print(\"TESTES\", r[\"passou\"], r[\"total\"])\n"
             "PY'"
             if (RAIZ / caminho / "tests" / "suite.py").exists() else "echo 'TESTES 0 0'")
    saida = vm(f"rm -rf {estagio} && mkdir -p {estagio} && aws s3 cp s3://{BUCKET}/{chave} - | tar xz -C {estagio} && "
               f"docker exec agent-zero rm -rf /tmp/estagio-{plugin}; {teste}")
    linha = next((l for l in saida.splitlines() if l.startswith("TESTES")), "")
    print(saida[-1500:])
    partes = linha.split()
    if not linha or partes[1] != partes[2]:
        raise SystemExit("testes falharam na cópia de estágio: nada foi implantado.")

    destino = f"/opt/a0/usr/plugins/{plugin}"
    copia_skill = (f" && mkdir -p /opt/a0/usr/skills/{skill} && cp -r {estagio}/infra/vm/skills/{skill}/. "
                   f"/opt/a0/usr/skills/{skill}/" if skill else "")
    print(vm(f"cp -r {estagio}/{caminho}/. {destino}/{copia_skill} && "
             f"echo '{head} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}' > {destino}/.versao && "
             "docker exec agent-zero curl -s -X POST http://127.0.0.1:80/api/cache_reset && echo && "
             f"cat {destino}/.versao"))
    print(f"implantado: {plugin} @ {head[:8]}" + (f" + skill {skill}" if skill else ""))


if __name__ == "__main__":
    main()

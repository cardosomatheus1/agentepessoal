"""The only way to put a plugin (or skill), or a host script, on the agent VM. Usage, from the repository root:

    python3 infra/operador/implantar.py prospeccao [--skill prospeccao-instagram] [--forcar]
    python3 infra/operador/implantar.py --host ponte_whatsapp.py [--reiniciar agentepessoal-whatsapp.service] [--forcar]
    python3 infra/operador/implantar.py --host caixa_convidados.py --unidade agentepessoal-caixas.service
    python3 infra/operador/implantar.py --host caixa_delegados.py --unidade agentepessoal-delegados.service
    python3 infra/operador/implantar.py --host estabilidade.py --unidade agentepessoal-estabilidade.service
    python3 infra/operador/implantar.py --host estabilidade.py --unidade agentepessoal-limpeza-disco.timer
    python3 infra/operador/implantar.py --host opencode_tunel.sh --unidade opencodemobile-publish-url.timer
    python3 infra/operador/implantar.py --host opencode_tunel.sh --unidade opencodemobile-cloudflare.service --sem-reiniciar
    python3 infra/operador/implantar.py --host opencode_tunel.sh --unidade opencodemobile.service --sem-reiniciar
    python3 infra/operador/implantar.py --host opencode_tunel.sh --unidade opencodemobile-aws.socket   (endereço fixo AWS, 24/10)
    python3 infra/operador/implantar.py --host estabilidade.py --unidade agentepessoal-vigia-rede.timer
    python3 infra/operador/implantar.py --host watchdog.sh   (hibernação só com HIBERNAR=1, 24/10)
    python3 infra/operador/implantar.py --hermes          (o Hermes ao lado do A0: infra/vm/hermes, fase 1 da migração)
        (--unidade also installs/updates that committed systemd unit, infra/vm/unidades/<unidade>, enables and restarts it;
         a .timer or a .socket also brings the .service of the same name; --sem-reiniciar installs without restarting it, e.g. a
         tunnel whose address would change: it takes effect on the next start)
    python3 infra/operador/implantar.py --moldes [--forcar]   (video/carousel templates, infra/reels/moldes, for the agent)
    python3 infra/operador/implantar.py --calibracao   (AR Board criteria, calibracao/*/criterios.md, for the Crítico)
    python3 infra/operador/implantar.py --controle [--forcar]   (the control page / webhooks Lambda, infra/control)
    python3 infra/operador/implantar.py --segundo-cerebro [--rollback | --preparar | --adotar-manual]   (page + gateway plugin; no --forcar)

Why (11/10): two Claude sessions deployed the same plugin over each other and one edited the live data by hand; a
reply lock stayed on and the only message to a lead was deleted. Rules enforced here:
1. Only what is committed AND pushed goes (the copy comes from `git archive HEAD`, never from the working tree).
2. The VM keeps the commit it is running (.versao). If that commit is not in this checkout's history, someone else
   deployed something newer: refuse (git pull first). --forcar only when the person says so.
3. The plugin's tests (tests/suite.py, when there is one) run on a staging copy on the VM BEFORE the live copy is
   replaced; a failing test stops the deploy and the live plugin is untouched.
"""

import io
import re
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



# 27/10: no container descartável (A0 parado) a imagem guarda o código do A0 em /git/agent-zero (o /a0 só se enche na
# inicialização dele, que o `sleep` pula): teste que importa `helpers` do A0 (ex.: o receber.py do WhatsApp) falhava com
# "No module named 'helpers'" e nenhum plugin com teste assim podia ser implantado.
CODIGO_A0_IMAGEM = "/git/agent-zero"


def ambiente_estagio(a0_no_ar: bool) -> str:
    return "" if a0_no_ar else f"-e PYTHONPATH={CODIGO_A0_IMAGEM} "

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
                 "entrada.sh", "credenciais_meta.py", "ponte_whatsapp.py", "proximo_despertar.py", "agent_tools.sh",
                 "saude.py", "firewall.sh", "usuarios.py", "caixa_convidados.py", "caixa_delegados.py",
                 "delegado_hermes.py", "delegado_openclaw.py", "estabilidade.py", "opencode_tunel.sh")


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


def unidades_de(unidade: str) -> list:
    """The unit files a --unidade brings: a .timer (23/10, daily disk cleanup) or a .socket (24/10, the OpenCode fixed
    AWS address) also brings the .service of the same name, which is what it starts."""
    if not unidade:
        return []
    for sufixo in (".timer", ".socket"):
        if unidade.endswith(sufixo):
            return [unidade, unidade[: -len(sufixo)] + ".service"]
    return [unidade]


def host(args: list) -> None:
    """A host script: committed and pushed, syntax-checked on the VM before it replaces the live one, version kept."""
    arquivo = args[args.index("--host") + 1] if len(args) > args.index("--host") + 1 else ""
    if arquivo not in HOST_ARQUIVOS:
        raise SystemExit(f"script de host desconhecido: {arquivo!r} (conhecidos: {', '.join(HOST_ARQUIVOS)})")
    caminho = f"infra/vm/{arquivo}"
    unidade_nova = args[args.index("--unidade") + 1] if "--unidade" in args else ""
    unidades = unidades_de(unidade_nova)
    caminhos = [caminho] + [f"infra/vm/unidades/{u}" for u in unidades]
    for c in caminhos[1:]:
        if not (RAIZ / c).exists():
            raise SystemExit(f"unidade desconhecida: {c} (esperada em infra/vm/unidades/)")
    head = _conferir_git(caminhos)
    versao = f"/opt/agentepessoal/.versao-{arquivo}"
    no_ar = vm(f"cat {versao} 2>/dev/null | head -1").split(" ")[0]
    if no_ar and "--forcar" not in args and subprocess.run(["git", "merge-base", "--is-ancestor", no_ar, head], cwd=RAIZ).returncode:
        raise SystemExit(f"a VM roda {arquivo} de {no_ar[:8]}, que não está no seu histórico: faça git pull (ou --forcar).")
    pacote = subprocess.run(["git", "archive", "--format=tar.gz", "HEAD", *caminhos], cwd=RAIZ, check=True, capture_output=True).stdout
    chave = f"tmp/implantar-host-{arquivo}-{head[:8]}.tgz"
    boto3.client("s3", region_name="us-east-1").put_object(Bucket=BUCKET, Key=chave, Body=pacote)
    checar = f"bash -n {{f}}" if arquivo.endswith(".sh") else "python3 -m py_compile {f}"
    unidade = args[args.index("--reiniciar") + 1] if "--reiniciar" in args else unidade_nova
    instalar = ("".join(f" && install -m 644 {{e}}/infra/vm/unidades/{u} /etc/systemd/system/{u}" for u in unidades)
                + f" && systemctl daemon-reload && systemctl enable -q {unidade_nova}") if unidade_nova else ""
    estagio = "/tmp/implantar-host"
    saida = vm(f"rm -rf {estagio} && mkdir -p {estagio} && aws s3 cp --quiet s3://{BUCKET}/{chave} - | tar xz -C {estagio} && "
               f"{checar.format(f=f'{estagio}/{caminho}')} && echo SINTAXE_OK && "
               f"install -m 755 {estagio}/{caminho} /opt/agentepessoal/{arquivo} && "
               f"echo '{head} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}' > {versao} && cat {versao}"
               + instalar.format(e=estagio)
               + (f" && systemctl restart {unidade} && systemctl is-active {unidade}" if unidade and "--sem-reiniciar" not in args else ""))
    print(saida[-800:])
    if "SINTAXE_OK" not in saida:
        raise SystemExit("o script não passou na conferência de sintaxe: nada foi trocado.")
    if head not in saida:
        raise SystemExit("a troca falhou depois da conferência: veja a saída acima.")
    print(f"implantado no host: {arquivo} @ {head[:8]}")


HERMES_ARQUIVOS = ("infra/vm/hermes", "infra/vm/portal")  # config.yaml, SOUL.md, subir.sh, plugins/ e o portal (fase 6)


def hermes(args: list) -> None:
    """The Hermes next to Agent Zero (23/10, migration, docs/MIGRACAO_HERMES.md): committed and pushed, config checked
    on the VM, container recreated by subir.sh (it waits for a real answer from the model), version recorded. The A0 is not touched."""
    head = _conferir_git(list(HERMES_ARQUIVOS))
    pacote = subprocess.run(["git", "archive", "--format=tar.gz", "HEAD", *HERMES_ARQUIVOS], cwd=RAIZ, check=True,
                            capture_output=True).stdout
    chave = f"tmp/implantar-hermes-{head[:8]}.tgz"
    boto3.client("s3", region_name="us-east-1").put_object(Bucket=BUCKET, Key=chave, Body=pacote)
    estagio = "/tmp/implantar-hermes"
    saida = vm(f"rm -rf {estagio} && mkdir -p {estagio} && aws s3 cp --quiet s3://{BUCKET}/{chave} - | tar xz -C {estagio} && "
               f"bash -n {estagio}/infra/vm/hermes/subir.sh && "
               f"python3 -c \"import yaml,sys; yaml.safe_load(open(sys.argv[1]))\" {estagio}/infra/vm/hermes/config.yaml && "
               f"echo CONFERIDO && bash {estagio}/infra/vm/hermes/subir.sh && "
               f"echo '{head} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}' > /opt/hermes/.versao && cat /opt/hermes/.versao")
    print(saida[-1500:])
    if "CONFERIDO" not in saida:
        raise SystemExit("config ou script não passou na conferência: nada foi trocado.")
    if "HERMES_OK" not in saida or head not in saida:
        raise SystemExit("o Hermes não subiu: veja a saída acima (o Agent Zero segue no ar, intocado).")
    print(f"implantado: hermes @ {head[:8]}")


CALIBRACAO_VM = "/opt/a0/usr/calibracao"  # /a0/usr/calibracao in the container: read by plugins/especialistas (Crítico)


def arquivos_calibracao(raiz: Path = RAIZ) -> list:
    """The AR Board criteria the agent reads (calibracao/<agente>/criterios.md). The judged cases (casos.jsonl) stay in
    git only: they quote real people's profiles and the Crítico needs just the rules."""
    return sorted(str(f.relative_to(raiz)) for f in (raiz / "calibracao").glob("*/criterios.md"))


def calibracao(args: list) -> None:
    """Matheus's AR Board criteria to the VM (20/10): committed and pushed, the whole set replaced at once, the
    previous set kept next to it (calibracao.anterior), version recorded."""
    caminhos = arquivos_calibracao()
    if not caminhos:
        raise SystemExit("nenhum calibracao/<agente>/criterios.md no repositório")
    head = _conferir_git(caminhos)
    pacote = subprocess.run(["git", "archive", "--format=tar.gz", "HEAD", *caminhos], cwd=RAIZ, check=True,
                            capture_output=True).stdout
    chave = f"tmp/implantar-calibracao-{head[:8]}.tgz"
    boto3.client("s3", region_name="us-east-1").put_object(Bucket=BUCKET, Key=chave, Body=pacote)
    estagio = "/tmp/implantar-calibracao"
    saida = vm(f"rm -rf {estagio} && mkdir -p {estagio} && aws s3 cp --quiet s3://{BUCKET}/{chave} - | tar xz -C {estagio} && "
               f"echo '{head} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}' > {estagio}/calibracao/.versao && "
               f"rm -rf {CALIBRACAO_VM}.anterior && (test -d {CALIBRACAO_VM} && mv {CALIBRACAO_VM} {CALIBRACAO_VM}.anterior || true) && "
               f"mv {estagio}/calibracao {CALIBRACAO_VM} && chmod -R a+rX {CALIBRACAO_VM} && "
               f"find {CALIBRACAO_VM} -name criterios.md | sort && cat {CALIBRACAO_VM}/.versao")
    print(saida[-800:])
    if head not in saida:
        raise SystemExit("a troca dos critérios falhou: veja a saída acima.")
    print(f"implantado: {len(caminhos)} arquivo(s) de critérios @ {head[:8]}")


MOLDES = "infra/reels/moldes"
MOLDES_VM = "/opt/a0/usr/moldes"  # /a0/usr/moldes in the container: rendered by plugins/conteudo (22/10)
MOLDES_TESTES = ("motor/test_validar.py", "motor/test_audio.py", "motor/test_voz.py", "motor/test_patchright.py")


# onde os moldes rodam: no Hermes (desde 23/10, o A0 parado) ou no A0 (a volta); (container, opções do exec, python)
ALVOS_MOLDES = {"hermes": ("hermes", "-u 10000 -e HOME=/opt/data", "/opt/hermes/.venv/bin/python3"),
                "agent-zero": ("agent-zero", "", "/opt/venv-a0/bin/python")}


def comando_moldes(head: str, chave: str, quando: str, alvo: str = "agent-zero") -> str:
    """The VM side of --moldes: unpack next to the live copy, reuse node_modules when package-lock.json did not change
    (else npm ci), run the motor tests and one preview of a real narrated ficha inside the agent container (patchright
    and its Chromium, and the voice through the host's short-lived /voz credentials, as the agent will), and only then
    swap; the previous copy stays as moldes.anterior."""
    novo, ct = f"{MOLDES_VM}.novo", "/a0/usr/moldes.novo"
    container, opcoes, py = ALVOS_MOLDES[alvo]
    testes = " && ".join(f"{py} {ct}/{t}" for t in MOLDES_TESTES)
    return (f"rm -rf {novo} /tmp/implantar-moldes && mkdir -p /tmp/implantar-moldes && "
            f"aws s3 cp --quiet s3://{BUCKET}/{chave} - | tar xz -C /tmp/implantar-moldes && "
            f"mv /tmp/implantar-moldes/{MOLDES} {novo} && "
            f"if cmp -s {MOLDES_VM}/motor/package-lock.json {novo}/motor/package-lock.json && test -d {MOLDES_VM}/motor/node_modules; "
            f"then cp -a {MOLDES_VM}/motor/node_modules {novo}/motor/; "
            f"else docker exec {opcoes} -w {ct}/motor {container} npm ci --omit=dev --no-audit --no-fund >/dev/null; fi && "
            f"printf '[profile voz]\\nregion = us-east-1\\ncredential_process = python3 {ct}/motor/credencial_voz.py\\n' "
            f"> {novo}/aws-voz.config && "
            f"docker exec -e MOLDES_CACHE=/a0/usr/conteudo/cache-moldes -e AWS_CONFIG_FILE={ct}/aws-voz.config "
            f"-e AWS_PROFILE=voz -e AWS_REGION=us-east-1 -e AWS_SDK_LOAD_CONFIG=1 {opcoes} {container} sh -c '{testes} && "
            f"{py} {ct}/motor/render.py lanca-app {ct}/lanca-app/exemplos/raiz-sistema-computador.json "
            f"--previa --saida /tmp/moldes-previa' && echo TESTES_OK && "
            f"echo '{head} {quando}' > {novo}/.versao && "
            f"rm -rf {MOLDES_VM}.anterior && (test -d {MOLDES_VM} && mv {MOLDES_VM} {MOLDES_VM}.anterior || true) && "
            f"mv {novo} {MOLDES_VM} && cat {MOLDES_VM}/.versao")


def moldes(args: list) -> None:
    """The templates the agent renders its Reels and carousels with (22/10, Matheus: "Leve"): committed and pushed,
    refused when the VM runs a newer version from another session, tested on the VM before the swap."""
    # 23/10 (virada ao Hermes): os moldes rodam no Hermes (patchright e o Chromium do A0 montado na imagem dele);
    # no A0 só quando ele está no ar (a volta)
    alvo = "agent-zero" if "true" in vm("docker inspect -f '{{.State.Running}}' agent-zero 2>/dev/null || echo false") \
        else "hermes"
    head = _conferir_git([MOLDES])
    no_ar = vm(f"cat {MOLDES_VM}/.versao 2>/dev/null | head -1").split(" ")[0]
    if no_ar and "--forcar" not in args and subprocess.run(["git", "merge-base", "--is-ancestor", no_ar, head], cwd=RAIZ).returncode:
        raise SystemExit(f"a VM roda moldes de {no_ar[:8]}, que não está no seu histórico: faça git pull (ou --forcar).")
    pacote = subprocess.run(["git", "archive", "--format=tar.gz", "HEAD", MOLDES], cwd=RAIZ, check=True, capture_output=True).stdout
    chave = f"tmp/implantar-moldes-{head[:8]}.tgz"
    boto3.client("s3", region_name="us-east-1").put_object(Bucket=BUCKET, Key=chave, Body=pacote)
    saida = vm(comando_moldes(head, chave, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), alvo), timeout=1800)
    print(saida[-1500:])
    if "TESTES_OK" not in saida:
        raise SystemExit("os testes dos moldes falharam na VM: nada foi trocado.")
    if head not in saida:
        raise SystemExit("a troca falhou depois dos testes: veja a saída acima.")
    print(f"implantado: moldes @ {head[:8]} (testado no {alvo})")


CONTROLE = ("index.py", "whatsapp.py", "telegram.py")  # what deploy.py zips into the control function
FUNCAO = "agentepessoal-control"


def controle(args: list) -> None:
    """The control function (Lambda): committed and pushed code only, compiled here first, version kept in its
    description; then the page must still load and refuse a wrong key. Same files deploy.py packs."""
    import urllib.error
    import urllib.request
    import zipfile

    caminhos = [f"infra/control/{a}" for a in CONTROLE]
    head = _conferir_git(caminhos)
    lam = boto3.client("lambda", region_name="us-east-1")
    no_ar = (lam.get_function_configuration(FunctionName=FUNCAO).get("Description") or "").split(" ")
    no_ar = no_ar[1] if len(no_ar) > 1 and no_ar[0] == "versao" else ""
    if no_ar and "--forcar" not in args and subprocess.run(["git", "merge-base", "--is-ancestor", no_ar, head], cwd=RAIZ).returncode:
        raise SystemExit(f"a função de controle roda {no_ar[:8]}, que não está no seu histórico: faça git pull (ou --forcar).")
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, caminho in zip(CONTROLE, caminhos):
            fonte = subprocess.run(["git", "show", f"HEAD:{caminho}"], cwd=RAIZ, check=True, capture_output=True).stdout
            compile(fonte, caminho, "exec")  # a syntax error stops here, before anything is replaced
            z.writestr(nome, fonte)
    lam.update_function_code(FunctionName=FUNCAO, ZipFile=pacote.getvalue())
    lam.get_waiter("function_updated_v2").wait(FunctionName=FUNCAO)
    lam.update_function_configuration(FunctionName=FUNCAO,
                                      Description=f"versao {head} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    lam.get_waiter("function_updated_v2").wait(FunctionName=FUNCAO)
    url = lam.get_function_url_config(FunctionName=FUNCAO)["FunctionUrl"]
    with urllib.request.urlopen(url, timeout=20) as r:
        pagina = r.read().decode("utf-8", "replace")
    req = urllib.request.Request(url, data=b'{"password": "errada", "action": "status"}', method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20)
        recusou = False
    except urllib.error.HTTPError as exc:
        recusou = exc.code == 401
    if "Agente" not in pagina or not recusou:
        raise SystemExit("a função de controle subiu mas não respondeu como esperado (página ou senha): confira já.")
    print(f"implantado: função de controle @ {head[:8]} (página ok, chave errada recusada)")


def segundo_cerebro(args: list) -> None:
    """Segundo Cérebro (infra/operador/segundo_cerebro.py does the work): --preparar is local only (no AWS);
    deploy and --rollback first confirm the existing account and instance. Only the owned plugin and release move."""
    import urllib.error
    import urllib.request

    import segundo_cerebro as sc

    if "--forcar" in args:
        raise SystemExit("--forcar não vale para o Segundo Cérebro: resolva a causa (git pull, commit, push).")
    python_suite = args[args.index("--python-suite") + 1] if "--python-suite" in args else sys.executable  # needs Flask
    if "--preparar" in args:
        sc.preparar(None, python_suite)
        return
    # 23/10 (virada ao Hermes): com o A0 parado, o Segundo Cérebro é testado e servido pelo portal (mesmo plugin e
    # mesma release em /opt/a0/usr/segundo_cerebro; o portal serve uma cópia, sincronizada na troca)
    hermes_alvo = "true" not in vm("docker inspect -f '{{.State.Running}}' agent-zero 2>/dev/null || echo false")
    if hermes_alvo:
        sc.ALVO_VM = sc.ALVO_HERMES

    def conferir_conta() -> None:
        conta = boto3.client("sts", region_name="us-east-1").get_caller_identity()["Account"]
        if conta != sc.CONTA:
            raise SystemExit(f"conta AWS {conta} não é a do agente ({sc.CONTA}): nada foi feito.")
        info = ssm.describe_instance_information(Filters=[{"Key": "InstanceIds", "Values": [VM]}])["InstanceInformationList"]
        if not info or info[0].get("PingStatus") != "Online":
            raise SystemExit(f"a VM {VM} não está online no SSM: nada foi feito.")

    if "--rollback" in args:
        conferir_conta()
        return sc.reverter(vm)

    def url_publica() -> str:
        return ssm.get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")

    def sondar_publico(url: str) -> dict:
        """From outside, without a session: page and API refuse (401), Agent Zero's login still loads."""
        codigos = {}
        for caminho in ("/segundo-cerebro", "/api/segundo-cerebro", "/login"):
            try:
                with urllib.request.urlopen(url + caminho, timeout=20) as r:
                    codigos[caminho] = r.status
            except urllib.error.HTTPError as exc:
                codigos[caminho] = exc.code
            except OSError as exc:
                codigos[caminho] = f"erro: {type(exc).__name__}"
        if hermes_alvo:  # o portal: a página manda ao login (302), a API recusa (401), o login abre (200)
            with_login = {}
            try:
                with urllib.request.urlopen(url + "/entrar", timeout=20) as r:
                    with_login["/entrar"] = r.status
            except (urllib.error.HTTPError, OSError) as exc:
                with_login["/entrar"] = getattr(exc, "code", f"erro: {type(exc).__name__}")
            ok = codigos["/segundo-cerebro"] in (302, 200) and codigos["/api/segundo-cerebro"] == 401 \
                and with_login["/entrar"] == 200
            return {"ok": ok, **codigos, **with_login}
        ok = codigos["/segundo-cerebro"] == 401 and codigos["/api/segundo-cerebro"] == 401 and codigos["/login"] == 200
        return {"ok": ok, **codigos}

    def eh_ancestral(a: str, b: str) -> bool:
        return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=RAIZ).returncode == 0

    s3 = boto3.client("s3", region_name="us-east-1")
    sc.implantar(vm, lambda chave, dados: s3.put_object(Bucket=BUCKET, Key=chave, Body=dados), _conferir_git,
                 eh_ancestral, url_publica, sondar_publico, conferir_conta, BUCKET, python_suite,
                 adotar="--adotar-manual" in args)


def main() -> None:
    args = sys.argv[1:]
    if "--segundo-cerebro" in args:
        return segundo_cerebro(args)
    if "--hermes" in args:
        return hermes(args)
    if "--host" in args:
        return host(args)
    if "--controle" in args:
        return controle(args)
    if "--calibracao" in args:
        return calibracao(args)
    if "--moldes" in args:
        return moldes(args)
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
    # 23/10 (virada ao Hermes): com o A0 parado (7 dias, para a volta) a suíte roda num container descartável da MESMA
    # imagem do A0, sem rede, com a cópia de estágio, os plugins no ar só para leitura e /a0/usr vazio (como no CI; nada
    # dos dados vivos é tocado). O Hermes roda o mesmo
    # código dos plugins pela ponte_a0, que relê a ferramenta quando o arquivo muda: não precisa reiniciar.
    a0_no_ar = "true" in vm("docker inspect -f '{{.State.Running}}' agent-zero 2>/dev/null || echo false")
    alvo = "agent-zero" if a0_no_ar else f"estagio-{plugin}"
    preparo = ("" if a0_no_ar else
               f"docker rm -f {alvo} >/dev/null 2>&1; docker run -d --name {alvo} --network none --entrypoint sleep "
               f"--mount type=tmpfs,destination=/a0/usr -v /opt/a0/usr/plugins:/a0/usr/plugins:ro "
               f"$(docker inspect -f '{{{{.Config.Image}}}}' agent-zero) 3600 >/dev/null && ")
    teste = (preparo + f"docker cp {estagio}/{caminho} {alvo}:/tmp/estagio-{plugin} && "
             # ESTAGIO=1: suites skip what only runs inside the agent (e.g. tests that write the live scheduler)
             f"docker exec -e ESTAGIO=1 {ambiente_estagio(a0_no_ar)}{alvo} sh -c 'cd /a0 && /opt/venv-a0/bin/python - <<\"PY\"\n"
             "import asyncio, importlib.util\n"
             f"s = importlib.util.spec_from_file_location(\"estagio\", \"/tmp/estagio-{plugin}/tests/suite.py\")\n"
             "m = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
             "r = asyncio.run(m.Suite().rodar(\"\"))\n"
             "[print(\"FALHA\", x[\"teste\"], x.get(\"erro\", \"\")[:200]) for x in r[\"resultados\"] if not x[\"ok\"]]\n"
             "print(\"TESTES\", r[\"passou\"], r[\"total\"])\n"
             "PY'"
             if (RAIZ / caminho / "tests" / "suite.py").exists() else "echo 'TESTES 0 0'")
    saida = vm(f"rm -rf {estagio} && mkdir -p {estagio} && aws s3 cp s3://{BUCKET}/{chave} - | tar xz -C {estagio} && "
               f"docker exec {alvo} rm -rf /tmp/estagio-{plugin} 2>/dev/null; {teste}"
               + ("" if a0_no_ar else f"; docker rm -f {alvo} >/dev/null 2>&1"))
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
             + ("docker exec agent-zero curl -s -X POST http://127.0.0.1:80/api/cache_reset && echo && " if a0_no_ar else "")
             + f"cat {destino}/.versao"))
    print(f"implantado: {plugin} @ {head[:8]}" + (f" + skill {skill}" if skill else ""))
    if skill:  # 12/10: a chat that already loaded the skill keeps the old text ("already loaded in visible chat history")
        chats = vm(f"grep -l 'skill_name.*{skill}' /opt/a0/usr/chats/*/chat.json 2>/dev/null | cut -d/ -f6 | sort -u | head -20")
        ids = [c for c in chats.split() if re.fullmatch(r"[A-Za-z0-9_-]{4,40}", c)]
        if ids:
            print(f"ATENÇÃO: estas conversas já carregaram a skill {skill} e continuam com a versão antiga até serem "
                  "reiniciadas (quando estiverem paradas): A0_SENHA=… python3 infra/operador/resetar_chat.py " + " ".join(ids))


if __name__ == "__main__":
    main()

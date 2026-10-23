"""(LEGADO desde 23/10: as rotinas do agente vivem no cron do Hermes, fonte em infra/vm/hermes/rotinas/; exportar e
comparar ainda leem o tasks.json do A0 parado; aplicar e criar só com A0_LEGADO=1.)
The agent's scheduled routines kept in git (12/10 review, §4.5: 5 routine prompts lived only on the VM). Usage:

    python3 infra/operador/rotinas.py exportar          # live → infra/vm/rotinas/<uuid>.json (then review and commit)
    python3 infra/operador/rotinas.py comparar          # what differs between the VM and git
    A0_SENHA=... python3 infra/operador/rotinas.py aplicar <uuid>   # git → VM (name, schedule, prompts, off; by the API)
    A0_SENHA=... python3 infra/operador/rotinas.py criar <arquivo>  # a new routine (JSON without uuid) → VM, then exportar

The prospecting rounds stay in infra/vm/plugins/prospeccao/rodadas.py. Reading is by SSM (tasks.json is never
edited); "aplicar" goes through the scheduler's own API, like tarefa_atualizar.py. Anything that looks like a secret
stops the export of that routine."""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

import boto3

RAIZ = Path(__file__).resolve().parents[2]
PASTA = RAIZ / "infra" / "vm" / "rotinas"
VM = "i-0498b4f39560b01a9"
BUCKET = "agentepessoal-backup-964862484412"
CAMPOS =("uuid", "name", "state", "schedule", "system_prompt", "prompt")
FORA = ("🎯 Prospecção",)  # managed by plugins/prospeccao/rodadas.py
SEGREDO = re.compile(r"\b(EAA[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]{30,}|"
                     r"xox[abp]-[A-Za-z0-9-]{20,}|AIza[A-Za-z0-9_-]{30,}|apify_api_[A-Za-z0-9]{20,})")


def _vm(comando: str) -> str:
    ssm = boto3.client("ssm", region_name="us-east-1")
    cid = ssm.send_command(InstanceIds=[VM], DocumentName="AWS-RunShellScript",
                           Parameters={"commands": [comando]}, TimeoutSeconds=120)["Command"]["CommandId"]
    for _ in range(60):
        time.sleep(2)
        try:
            r = ssm.get_command_invocation(CommandId=cid, InstanceId=VM)
        except ssm.exceptions.InvocationDoesNotExist:
            continue
        if r["Status"] not in ("Pending", "InProgress", "Delayed"):
            return r["StandardOutputContent"]
    raise SystemExit("a VM não respondeu a tempo")


def ao_vivo() -> dict:
    """The live task list through S3 (an SSM answer is cut at 24 thousand characters)."""
    chave = f"tmp/rotinas-{int(time.time())}.json"
    saida = _vm(f"aws s3 cp --quiet /opt/a0/usr/scheduler/tasks.json s3://{BUCKET}/{chave} && echo COPIADO")
    if "COPIADO" not in saida:
        raise SystemExit(f"não consegui ler as rotinas da VM: {saida[-300:]}")
    s3 = boto3.client("s3", region_name="us-east-1")
    try:
        tarefas = json.loads(s3.get_object(Bucket=BUCKET, Key=chave)["Body"].read())["tasks"]
    finally:
        s3.delete_object(Bucket=BUCKET, Key=chave)
    return {t["uuid"]: {k: t.get(k) for k in CAMPOS} for t in tarefas
            if t.get("type") == "scheduled" and not str(t.get("name", "")).startswith(FORA)}


def no_git() -> dict:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(PASTA.glob("*.json"))}


def exportar() -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    for uuid, t in ao_vivo().items():
        if t.get("state") == "disabled" and not (PASTA / f"{uuid}.json").exists():
            print(f"· {uuid} {t['name']}: desligada, fica fora do git")
            continue
        if SEGREDO.search(json.dumps(t, ensure_ascii=False)):
            print(f"✗ {uuid} {t['name']}: parece ter um segredo no texto; não exportada (troque por §§secret(NOME))")
            continue
        (PASTA / f"{uuid}.json").write_text(json.dumps(t, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"✓ {uuid} {t['name']}")


def comparar() -> int:
    vivo, git = ao_vivo(), no_git()
    diferencas = 0
    for uuid in sorted(set(vivo) | set(git)):
        if uuid not in git:
            if vivo[uuid].get("state") == "disabled":
                continue  # switched off and never kept: nothing to compare
            print(f"+ {uuid} {vivo[uuid]['name']}: só na VM (rode exportar)")
        elif uuid not in vivo:
            print(f"- {uuid} {git[uuid]['name']}: só no git (apagada na VM?)")
        else:
            campos = [c for c in CAMPOS if vivo[uuid].get(c) != git[uuid].get(c)]
            if not campos:
                continue
            print(f"≠ {uuid} {vivo[uuid]['name']}: {', '.join(campos)} diferente(s)")
        diferencas += 1
    print("iguais" if not diferencas else f"{diferencas} diferença(s)")
    return 1 if diferencas else 0


async def _entrar(p):
    """A logged-in page of the agent's web UI (the scheduler API is called from it, like the UI does)."""
    url = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")
    b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"),
                                headless=True)
    a = await (await b.new_context()).new_page()
    await a.goto(url + "/login", timeout=120000)
    await a.wait_for_selector("#username")
    await a.fill("#username", os.environ.get("A0_LOGIN", "matheus"))
    await a.fill("#password", os.environ["A0_SENHA"])
    await a.click("button[type=submit]")
    await a.wait_for_selector("#chat-input", timeout=90000)
    return b, a


async def criar(arquivo: str) -> None:
    """A routine kept in git before it exists on the VM (a file without "uuid"): created by the scheduler API, unless
    a live routine already has that name. Then `exportar` writes it as <uuid>.json and the uuid-less file goes."""
    from playwright.async_api import async_playwright

    t = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    if t.get("uuid"):
        raise SystemExit(f"{arquivo} já tem uuid: use aplicar")
    if SEGREDO.search(json.dumps(t, ensure_ascii=False)):
        raise SystemExit("parece ter um segredo no texto (troque por §§secret(NOME))")
    if any(v.get("name") == t["name"] for v in ao_vivo().values()):
        raise SystemExit(f"já existe uma rotina '{t['name']}' na VM: rode exportar")
    async with async_playwright() as p:
        b, a = await _entrar(p)
        r = await a.evaluate("""async (dados) => { const api = await import('/js/api.js');
            const r = await api.callJsonApi('scheduler_task_create', dados);
            return (r.task || {}).uuid || ('ERRO ' + (r.error || JSON.stringify(r).slice(0, 200))); }""",
                             {"name": t["name"], "prompt": t["prompt"], "system_prompt": t.get("system_prompt", ""),
                              "schedule": t["schedule"]})
        print(f"{t['name']}: criada = {r}")
        await b.close()


async def aplicar(uuid: str) -> None:
    from playwright.async_api import async_playwright

    t = no_git().get(uuid)
    if not t:
        raise SystemExit(f"{uuid} não está em {PASTA}")
    async with async_playwright() as p:
        b, a = await _entrar(p)
        r = await a.evaluate("""async (dados) => { const api = await import('/js/api.js');
            const r = await api.callJsonApi('scheduler_task_update', dados); return String(!!(r.task || r.ok)) + (r.error ? ' ' + r.error : ''); }""",
                             {"task_id": uuid, "name": t["name"], "prompt": t["prompt"], "system_prompt": t["system_prompt"],
                              # 12/10: schedules go from git too (the scheduler API takes the cron fields + timezone)
                              **({"schedule": t["schedule"]} if t.get("schedule") else {}),
                              # switching off goes from git as well; switching on is never sent here (a routine that is
                              # running would be marked idle under the scheduler: use tarefa_atualizar.py estado idle)
                              **({"state": "disabled"} if t.get("state") == "disabled" else {})})
        print(f"{uuid} {t['name']}: atualizada = {r}")
        await b.close()


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] not in ("exportar", "comparar", "aplicar", "criar"):
        raise SystemExit(__doc__)
    if args[0] == "exportar":
        exportar()
    elif args[0] == "comparar":
        sys.exit(comparar())
    else:
        if len(args) < 2:
            raise SystemExit(__doc__)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import legado_a0  # 23/10: as rotinas vivem no cron do Hermes (infra/vm/hermes/rotinas/, implantar.py --hermes)
        legado_a0.parar("rotinas.py " + args[0], "mude infra/vm/hermes/rotinas/<uuid>.json (com teste) e rode implantar.py --hermes")
        asyncio.run(criar(args[1]) if args[0] == "criar" else aplicar(args[1]))


if __name__ == "__main__":
    main()

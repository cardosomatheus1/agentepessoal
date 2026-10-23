"""Side-by-side test (23/10, Matheus): the same 10 tasks to our agent (Agent Zero, preset "Sonnet 5 teste") and to
Hermes (delegate box, anthropic.claude-sonnet-5), with the same information (preparar_vm.py builds the input folder),
no help from the operator. Records, per task and engine: finished alone or not, the final answer, seconds, the output
files; the tokens come from the proxy's usage log afterwards. Run from the repository root:
    A0_SENHA=... python3 infra/operador/lado_a_lado/rodar.py <saida.json> [t01,t02,...]"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import boto3
from playwright.async_api import async_playwright

AQUI = Path(__file__).resolve().parent
VMCMD = AQUI.parent / "vmcmd.py"
ENTRADA = "/a0/usr/workdir/lado_a_lado/entrada"
PRESET = "Sonnet 5 teste"
MODELO_HERMES = "anthropic.claude-sonnet-5"
MINUTOS = 20
A0_JUNTAS = 2
HERMES_JUNTAS = 2

REGRAS = ("Teste lado a lado pedido pelo Matheus: faça a tarefa até o fim sozinho, sem perguntar nada a ninguém. Se "
          "faltar algo, decida pelo mais sensato e diga o que decidiu. Não envie mensagem, não publique, não entre em "
          "conta de ninguém, não pague nada, não use as ferramentas delegar, Hermes ou OpenClaw. Termine com uma "
          "resposta curta: o que fez, o que decidiu sozinho e onde estão os arquivos.")


def vm(cmd: str, timeout: int = 300) -> str:
    r = subprocess.run([sys.executable, str(VMCMD), cmd], capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def texto_a0(t: dict) -> str:
    saida = f"/a0/usr/workdir/lado_a_lado/a0/{t['id']}/"
    arqs = ", ".join(f"{ENTRADA}/{a}" for a in t["arquivos"]) or "nenhum"
    return (f"{REGRAS}\n\nArquivos desta tarefa: {arqs} (o contexto.zip, quando aparece, é a mesma Pasta do seu "
            f"Segundo Cérebro). Grave o que produzir em {saida}\n\nTarefa: {t['texto']}")


def texto_hermes(t: dict) -> str:
    return (f"{REGRAS}\n\nVocê é o assistente pessoal do Matheus. Tudo o que ele já registrou sobre ele e a Raiz Connect "
            "está em /trabalho/entrada/contexto.zip: descompacte e leia segundo_cerebro/CLAUDE.md antes de começar; as "
            "decisões em segundo_cerebro/Decisoes valem até ele mudar. Os outros arquivos da tarefa estão em "
            f"/trabalho/entrada/. Grave o que produzir em /trabalho/saida/\n\nTarefa: {t['texto']}")


def hermes(acao: str, dados: dict) -> dict:
    corpo = json.dumps(dados, ensure_ascii=False).replace("'", "'\"'\"'")
    out = vm(f"S=$(cat /opt/a0/usr/delegados/segredo.txt); curl -s -m 60 -X POST http://172.17.0.1:8791/{acao} "
             f"-H \"X-Segredo: $S\" -H 'content-type: application/json' --data-binary '{corpo}'")
    try:
        return json.loads(out.splitlines()[-1])
    except (ValueError, IndexError):
        return {"erro": out[-300:]}


ESTADO_A0 = r'''import json,sys
try: d=json.load(open('/opt/a0/usr/chats/%s/chat.json'))
except Exception as e: print(json.dumps({"erro":str(e)})); sys.exit()
lg=d["log"]["logs"]; r=[x for x in lg if x["type"]=="response" and x.get("agentno")==0]
fim=bool(r) and bool(r[-1].get("kvps",{}).get("finished")) and lg.index(r[-1])>=len(lg)-4
print(json.dumps({"fim":fim,"progresso":d["log"].get("progress"),"n":len(lg),"resposta":(r[-1]["content"] if r else "")[:6000],
 "ultima":lg[-1]["timestamp"] if lg else 0,"ferramentas":[x.get("heading","")[:60] for x in lg if x["type"]=="tool"][-60:]},ensure_ascii=False))'''


def estado_a0(chat: str) -> dict:
    codigo = base64.b64encode((ESTADO_A0 % chat).encode()).decode()
    out = vm(f"echo {codigo} | base64 -d | python3 -")
    try:
        return json.loads(out.splitlines()[-1])
    except (ValueError, IndexError):
        return {"erro": out[-300:]}


async def rodar_a0(pagina, t: dict) -> dict:
    criar = "globalThis.sendJsonData('/chat_create', {}).then(r=>JSON.stringify(r))"
    r = json.loads(await pagina.evaluate(criar))
    chat = r.get("ctxid") or r.get("context") or r.get("id")
    await pagina.evaluate("([c,p])=>globalThis.sendJsonData('/plugins/_model_config/model_override', "
                          "{context_id:c, action:'set_preset', preset_name:p})", [chat, PRESET])
    inicio = time.time()
    await pagina.evaluate("([m,c])=>globalThis.sendJsonData('/message_async', {text:m, context:c})", [texto_a0(t), chat])
    est = {}
    while time.time() - inicio < MINUTOS * 60:
        await asyncio.sleep(30)
        est = await asyncio.to_thread(estado_a0, chat)
        if est.get("fim"):
            break
    seg = round(time.time() - inicio)
    arquivos = await asyncio.to_thread(vm, f"ls -la /opt/a0/usr/workdir/lado_a_lado/a0/{t['id']}/ 2>&1 | tail -n +2")
    return {"motor": "a0", "chat": chat, "terminou": bool(est.get("fim")), "segundos": seg,
            "resposta": est.get("resposta", ""), "ferramentas": est.get("ferramentas", []), "arquivos": arquivos}


async def rodar_hermes(t: dict) -> dict:
    inicio = time.time()
    r = await asyncio.to_thread(hermes, "iniciar", {"motor": "hermes", "modelo": MODELO_HERMES, "minutos": MINUTOS,
                                                    "tarefa": texto_hermes(t),
                                                    "arquivos": [f"{ENTRADA}/{a}" for a in t["arquivos"]]})
    if not r.get("id"):
        return {"motor": "hermes", "terminou": False, "erro": r.get("erro") or str(r)[:300], "segundos": 0}
    est = {}
    while time.time() - inicio < MINUTOS * 60 + 180:
        await asyncio.sleep(30)
        est = await asyncio.to_thread(hermes, "estado", {"id": r["id"]})
        if est.get("status") not in (None, "rodando", "iniciando"):
            break
    return {"motor": "hermes", "id": r["id"], "terminou": est.get("status") == "pronto" and bool(est.get("resposta")),
            "segundos": est.get("segundos") or round(time.time() - inicio), "resposta": est.get("resposta") or "",
            "erro": est.get("erro"), "status": est.get("status"), "ferramentas": est.get("ferramentas", []),
            "arquivos": est.get("arquivos", [])}


async def main(saida: Path, ids: list):
    tarefas = [t for t in json.loads((AQUI / "tarefas.json").read_text()) if not ids or t["id"] in ids]
    resultados = json.loads(saida.read_text()) if saida.exists() else {}
    url = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")
    trava_a0, trava_h = asyncio.Semaphore(A0_JUNTAS), asyncio.Semaphore(HERMES_JUNTAS)

    def guardar(t, r):
        resultados.setdefault(t["id"], {"titulo": t["titulo"], "criterio": t["criterio"]})[r["motor"]] = r
        saida.write_text(json.dumps(resultados, ensure_ascii=False, indent=1))
        print(f"{t['id']} {r['motor']}: terminou={r['terminou']} {r.get('segundos')} s", flush=True)

    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"), headless=True)
        pagina = await (await b.new_context()).new_page()
        await pagina.goto(url + "/login", timeout=120000)
        await pagina.fill("#username", "matheus")
        await pagina.fill("#password", os.environ["A0_SENHA"])
        await pagina.click("button[type=submit]")
        await pagina.wait_for_selector("#chat-input", timeout=90000)

        async def um_a0(t):
            async with trava_a0:
                guardar(t, await rodar_a0(pagina, t))

        async def um_hermes(t):
            async with trava_h:
                guardar(t, await rodar_hermes(t))

        await asyncio.gather(*[um_a0(t) for t in tarefas], *[um_hermes(t) for t in tarefas])
        await b.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), [x for x in (sys.argv[2] if len(sys.argv) > 2 else "").split(",") if x]))

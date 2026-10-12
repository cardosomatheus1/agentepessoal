"""Update one scheduled task of the agent through its API (never by editing tasks.json). Usage:

    python3 infra/operador/tarefa_atualizar.py <task_uuid> <campo: prompt|system_prompt> <arquivo_com_o_texto>

Prints the field before and after. Login as A0_LOGIN (default matheus) with A0_SENHA.
"""
import asyncio
import json
import os
import sys

import boto3
from playwright.async_api import async_playwright

URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")


async def main():
    uuid, campo, arquivo = sys.argv[1:4]
    if campo not in ("prompt", "system_prompt"):
        raise SystemExit("campo: prompt ou system_prompt")
    texto = open(arquivo, encoding="utf-8").read().strip()
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"), headless=True)
        a = await (await b.new_context()).new_page()
        await a.goto(URL + "/login", timeout=120000)
        await a.wait_for_selector("#username")
        await a.fill("#username", os.environ.get("A0_LOGIN", "matheus"))
        await a.fill("#password", os.environ["A0_SENHA"])
        await a.click("button[type=submit]")
        await a.wait_for_selector("#chat-input", timeout=90000)
        api = """async ([op, dados]) => { const api = await import('/js/api.js');
            if (op === 'lista') { const l = await api.callJsonApi('scheduler_tasks_list', {}); return JSON.stringify(l.tasks || []); }
            const r = await api.callJsonApi('scheduler_task_update', dados); return String(!!(r.task || r.ok)) + (r.error ? ' ' + r.error : ''); }"""
        tarefas = {t["uuid"]: t for t in json.loads(await a.evaluate(api, ["lista", None]))}
        if uuid not in tarefas:
            raise SystemExit(f"tarefa {uuid} não encontrada")
        print("ANTES:", (tarefas[uuid].get(campo) or "")[:400])
        print("update:", await a.evaluate(api, ["update", {"task_id": uuid, campo: texto}]))
        tarefas = {t["uuid"]: t for t in json.loads(await a.evaluate(api, ["lista", None]))}
        print("DEPOIS:", (tarefas[uuid].get(campo) or "")[:600])
        await b.close()


asyncio.run(main())

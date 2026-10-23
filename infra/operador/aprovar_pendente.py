"""Shows, and approves, the action waiting for Matheus's ok in one agent conversation (same as the ✅ button).
Usage: A0_SENHA=... python3 infra/operador/aprovar_pendente.py <chat id> [--so-ver]

Only for what Matheus already said he approves (12/10: "aprovo tudo lá do Instagram"); it prints what is approved."""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import legado_a0; legado_a0.parar("aprovar_pendente.py", "o pedido de ok chega como botões no Telegram; pelo operador: hermes_ao_vivo.py aprovar <run_id> once|deny")
import asyncio
import json
import os
import sys

import boto3
from playwright.async_api import async_playwright

URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")


async def main(chat: str, so_ver: bool) -> None:
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", headless=True)
        a = await (await b.new_context()).new_page()
        await a.goto(URL + "/login", timeout=120000)
        await a.wait_for_selector("#username")
        await a.fill("#username", os.environ.get("A0_LOGIN", "matheus"))
        await a.fill("#password", os.environ["A0_SENHA"])
        await a.click("button[type=submit]")
        await a.wait_for_selector("#chat-input", timeout=90000)
        api = """async ([op, dados]) => { const api = await import('/js/api.js');
            return JSON.stringify(await api.callJsonApi('/plugins/aprovacoes/' + op, dados)); }"""
        pend = json.loads(await a.evaluate(api, ["pendente", {"context": chat}])).get("pendente")
        print("pendente:", pend)
        if pend and not so_ver:
            r = json.loads(await a.evaluate(api, ["decidir", {"context": chat, "decisao": "aprovar", "id": pend["id"]}]))
            print("aprovado:", r.get("ok"))
        await b.close()


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    asyncio.run(main(args[0], "--so-ver" in sys.argv))

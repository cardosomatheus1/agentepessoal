import os
import asyncio, boto3, json, sys
from playwright.async_api import async_playwright
URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"), headless=True)
        a = await (await b.new_context()).new_page()
        await a.goto(URL + "/login", timeout=120000); await a.wait_for_selector("#username")
        await a.fill("#username", os.environ.get("A0_LOGIN", "matheus")); await a.fill("#password", os.environ["A0_SENHA"]); await a.click("button[type=submit]")
        await a.wait_for_selector("#chat-input", timeout=90000)
        r = await a.evaluate("async (so) => { const api = await import('/js/api.js'); return JSON.stringify(await api.callJsonApi('/plugins/prospeccao/testar', so === 'LIMPAR' ? {limpar: true} : {so})); }", sys.argv[1] if len(sys.argv) > 1 else "")
        d = json.loads(r)
        if "removidos" in d:
            print("removidos:", d["removidos"]); return
        if "resultados" not in d:
            print(r[:2000]); return
        for x in d["resultados"]:
            print(("✓" if x["ok"] else "✗"), x["teste"], x.get("s", ""), x.get("erro", ""), x.get("onde", "") if not x["ok"] else "", json.dumps(x.get("info", ""), ensure_ascii=False) if x.get("info") else "")
        print(f"{d['passou']}/{d['total']}")
        await b.close()
asyncio.run(main())

import os
import asyncio, json, sys, boto3
from playwright.async_api import async_playwright
URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")
MSG = open(sys.argv[1]).read()
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"), headless=True)
        a = await (await b.new_context()).new_page()
        await a.goto(URL + "/login", timeout=120000); await a.wait_for_selector("#username")
        await a.fill("#username", os.environ.get("A0_LOGIN", "matheus")); await a.fill("#password", os.environ["A0_SENHA"]); await a.click("button[type=submit]")
        await a.wait_for_selector("#chat-input", timeout=90000); await a.wait_for_timeout(1500)
        chat = sys.argv[2] if len(sys.argv) > 2 else json.loads(await a.evaluate("globalThis.sendJsonData('/chat_create', {}).then(r=>JSON.stringify(r))"))
        if isinstance(chat, dict): chat = chat.get("ctxid") or chat.get("context") or chat.get("id")
        print("chat", chat)
        print(await a.evaluate("([m,c])=>globalThis.sendJsonData('/message_async', {text: m, context: c}).then(r=>JSON.stringify(r))", [MSG, chat]))
        await b.close()
asyncio.run(main())

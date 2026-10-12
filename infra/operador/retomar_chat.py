"""Resumes (unpauses) one agent conversation through the agent's API, as the "Resume Agent" button does.
Usage: A0_SENHA=... python3 infra/operador/retomar_chat.py <chat id>

Why (12/10): the loop detector pauses a conversation that repeats the same step; a scheduled round paused that way
never moves again (nobody presses the button), and the next runs of the same round get stuck behind it."""
import asyncio
import json
import os
import sys

import boto3
from playwright.async_api import async_playwright

URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")


async def main(chat: str) -> None:
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", headless=True)
        a = await (await b.new_context()).new_page()
        await a.goto(URL + "/login", timeout=120000)
        await a.wait_for_selector("#username")
        await a.fill("#username", os.environ.get("A0_LOGIN", "matheus"))
        await a.fill("#password", os.environ["A0_SENHA"])
        await a.click("button[type=submit]")
        await a.wait_for_selector("#chat-input", timeout=90000)
        r = await a.evaluate("""async (ctx) => { const api = await import('/js/api.js');
            return JSON.stringify(await api.callJsonApi('pause', {paused: false, context: ctx})); }""", chat)
        print(json.loads(r))
        await b.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    asyncio.run(main(sys.argv[1]))

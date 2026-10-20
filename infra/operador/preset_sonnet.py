"""Creates/updates the "Sonnet" model preset (Claude Sonnet 5.5 on Bedrock, through the VM proxy, which adds the cache
points) via Agent Zero's own preset API — never by editing presets.yaml. The chat model is Sonnet; the utility model
(summaries, memory) stays on the default's cheap one. Usage:

    A0_SENHA=... python3 infra/operador/preset_sonnet.py

Who uses it is decided by login_usuarios/modelo_por_dono.json (in git, deployed with the plugin)."""

import asyncio
import json
import os

import boto3
from playwright.async_api import async_playwright

URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")
NOME = "Sonnet"
# ctx_history 0.4 (20/10, Matheus ok): history compressed past ~80k tokens instead of ~50k; in the simulation of
# resumo_seguro (tests/compressao.py) compressions fell from 19 to 11, each call a bit larger but mostly cached.
CHAT = {"provider": "bedrock", "name": "converse/us.anthropic.claude-sonnet-5-5", "ctx_length": 200000,
        "ctx_history": 0.4, "vision": True, "max_embeds": 30, "rl_requests": 0, "rl_input": 0, "rl_output": 0,
        "kwargs": {"a0_api_mode": "chat", "api_base": "http://host.docker.internal:8787/bedrock", "api_key": "proxy",
                   "aws_region_name": "us-east-1", "max_tokens": 32000, "output_config": {"effort": "medium"}}}


def com_sonnet(presets: list) -> list:
    """The list with the Sonnet preset added or replaced; the utility/embedding come from Default (cheap model)."""
    padrao = next((p for p in presets if p.get("name") == "Default"), {})
    novo = {"name": NOME, "chat": CHAT}
    for chave in ("utility", "embedding"):
        if padrao.get(chave):
            novo[chave] = padrao[chave]
    return [p for p in presets if p.get("name") != NOME] + [novo]


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"), headless=True)
        a = await (await b.new_context()).new_page()
        await a.goto(URL + "/login", timeout=120000)
        await a.wait_for_selector("#username")
        await a.fill("#username", os.environ.get("A0_LOGIN", "matheus"))
        await a.fill("#password", os.environ["A0_SENHA"])
        await a.click("button[type=submit]")
        await a.wait_for_selector("#chat-input", timeout=90000)
        chamar = "([d]) => globalThis.sendJsonData('/plugins/_model_config/model_presets', d).then(r => JSON.stringify(r))"
        atual = json.loads(await a.evaluate(chamar, [{"action": "get"}]))["presets"]
        r = json.loads(await a.evaluate(chamar, [{"action": "save", "presets": com_sonnet(atual)}]))
        print("salvo:", r.get("ok"), [x.get("name") for x in r.get("presets", [])])
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())

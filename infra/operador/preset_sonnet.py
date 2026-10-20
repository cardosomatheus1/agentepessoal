"""Creates/updates the "Sonnet" model preset (Claude Sonnet 5.5 on Bedrock, through the VM proxy, which adds the cache
points) via Agent Zero's own preset API — never by editing presets.yaml. The chat model is Sonnet; the utility model
(summaries, memory) stays on the default's cheap one. Usage:

    A0_SENHA=... python3 infra/operador/preset_sonnet.py            # the "Sonnet" preset (mode: MODO below)
    A0_SENHA=... python3 infra/operador/preset_sonnet.py --teste    # "Sonnet nativo": same, native tool calling,
                                                                    # for a test chat (per-chat override), no one else

Who uses it is decided by login_usuarios/modelo_por_dono.json (in git, deployed with the plugin).

Modes (20/10): "texto" = `a0_api_mode: chat` (no native tools; the model must write Agent Zero's JSON, and Sonnet often
answers in its own <invoke> XML, which prompt_enxuto converts). "nativo" = `a0_api_mode: responses`: Agent Zero sends
its tools as function tools; LiteLLM's Responses bridge turns them into Converse toolConfig and the model's toolUse
comes back as a function call Agent Zero runs. Needs prompt_enxuto's chat_model_call_before/_05_nativo_bedrock.py
(without it Agent Zero's own cache markers force Chat Completions and the tools are silently dropped); the cache points
then come from our proxy. `tool_choice: auto` because Sonnet 5.5 on Bedrock rejects Agent Zero's default "required"
("type any is not supported for this model"); `responses_state: local` because there is no stored response on Bedrock."""

import asyncio
import json
import os
import sys

import boto3
from playwright.async_api import async_playwright

URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")
NOME = "Sonnet"
NOME_TESTE = "Sonnet nativo"
# 20/10 ~22h: "nativo" after the test chats (same tasks, text x native): 0 <invoke> conversions, fewer model calls
# (browser on python.org 5 -> 4, 29.5 s -> 21 s; example.com + 3 terminal steps 7 -> 6, 37 s -> 33 s), cache hits the
# same (proxy cache points). Back to text mode: MODO = "texto" and run this script.
MODO = "nativo"
# ctx_history 0.4 (20/10, Matheus ok): history compressed past ~80k tokens instead of ~50k; in the simulation of
# resumo_seguro (tests/compressao.py) compressions fell from 19 to 11, each call a bit larger but mostly cached.
CHAT = {"provider": "bedrock", "name": "converse/us.anthropic.claude-sonnet-5-5", "ctx_length": 200000,
        "ctx_history": 0.4, "vision": True, "max_embeds": 30, "rl_requests": 0, "rl_input": 0, "rl_output": 0,
        "kwargs": {"a0_api_mode": "chat", "api_base": "http://host.docker.internal:8787/bedrock", "api_key": "proxy",
                   "aws_region_name": "us-east-1", "max_tokens": 32000, "output_config": {"effort": "medium"}}}
NATIVO = {"a0_api_mode": "responses", "responses_state": "local", "tool_choice": "auto"}


def chat(modo: str) -> dict:
    """The chat model of the preset in `modo` ("texto" or "nativo")."""
    if modo not in ("texto", "nativo"):
        raise ValueError(modo)
    conf = json.loads(json.dumps(CHAT))
    if modo == "nativo":
        conf["kwargs"].update(NATIVO)
    return conf


def com_sonnet(presets: list, nome: str = NOME, modo: str = MODO) -> list:
    """The list with the preset `nome` added or replaced (the others untouched); the utility/embedding come from Default
    (cheap model)."""
    padrao = next((p for p in presets if p.get("name") == "Default"), {})
    novo = {"name": nome, "chat": chat(modo)}
    for chave in ("utility", "embedding"):
        if padrao.get(chave):
            novo[chave] = padrao[chave]
    return [p for p in presets if p.get("name") != nome] + [novo]


async def main(nome: str, modo: str):
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
        r = json.loads(await a.evaluate(chamar, [{"action": "save", "presets": com_sonnet(atual, nome, modo)}]))
        print("salvo:", r.get("ok"), [x.get("name") for x in r.get("presets", [])])
        await b.close()


if __name__ == "__main__":
    teste = "--teste" in sys.argv[1:]
    asyncio.run(main(NOME_TESTE if teste else NOME, "nativo" if teste else MODO))

"""The Sonnet preset keeps 40% of the context for history (20/10) and the cheap utility model from Default."""

import importlib.util
import os
os.environ["A0_LEGADO"] = "1"  # preset_sonnet.py é do A0 (legado desde 23/10): o teste segue valendo para a volta
import sys
import types
from pathlib import Path

sys.modules.setdefault("boto3", types.SimpleNamespace(client=lambda *a, **k: types.SimpleNamespace(
    get_parameter=lambda **k: {"Parameter": {"Value": "http://x/"}})))
sys.modules.setdefault("playwright", types.ModuleType("playwright"))
api = types.ModuleType("playwright.async_api")
api.async_playwright = None
sys.modules.setdefault("playwright.async_api", api)
spec = importlib.util.spec_from_file_location("preset_sonnet", Path(__file__).resolve().parents[1] / "preset_sonnet.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_historico_40():
    assert m.CHAT["ctx_history"] == 0.4


def test_utilitario_do_padrao():
    saida = m.com_sonnet([{"name": "Default", "utility": {"name": "luna"}}, {"name": "Sonnet", "chat": {}}])
    assert [p["name"] for p in saida] == ["Default", "Sonnet"]
    assert saida[1]["utility"] == {"name": "luna"} and saida[1]["chat"]["ctx_history"] == 0.4


def test_nativo_so_muda_o_modo():
    texto, nativo = m.chat("texto"), m.chat("nativo")
    assert texto["kwargs"]["a0_api_mode"] == "chat" and "tool_choice" not in texto["kwargs"]
    assert nativo["kwargs"]["a0_api_mode"] == "responses"
    # Sonnet 5.5 on Bedrock rejects tool_choice "any" (Agent Zero's default "required"); no stored responses there
    assert nativo["kwargs"]["tool_choice"] == "auto" and nativo["kwargs"]["responses_state"] == "local"
    resto = {k: v for k, v in nativo["kwargs"].items() if k not in m.NATIVO}
    assert resto == {k: v for k, v in texto["kwargs"].items() if k != "a0_api_mode"}
    assert m.CHAT["kwargs"]["a0_api_mode"] == "chat", "chat() does not change the shared constant"


def test_sonnet_no_modo_nativo():
    saida = m.com_sonnet([{"name": "Default"}])
    assert saida[-1]["name"] == "Sonnet" and saida[-1]["chat"]["kwargs"]["a0_api_mode"] == "responses"


def test_preset_de_teste_nao_mexe_no_sonnet():
    sonnet = {"name": "Sonnet", "chat": m.chat("texto")}
    saida = m.com_sonnet([{"name": "Default"}, sonnet], m.NOME_TESTE, "nativo")
    assert [p["name"] for p in saida] == ["Default", "Sonnet", "Sonnet nativo"]
    assert saida[1] is sonnet and saida[2]["chat"]["kwargs"]["a0_api_mode"] == "responses"


def test_haiku_mesmo_caminho_outro_modelo():
    saida = m.com_sonnet([{"name": "Default", "utility": {"name": "luna"}}, {"name": "Sonnet", "chat": m.chat("nativo")}],
                         m.HAIKU, "nativo")
    haiku = saida[-1]
    assert [p["name"] for p in saida] == ["Default", "Sonnet", "Haiku"]
    assert haiku["chat"]["name"] == "converse/us.anthropic.claude-haiku-5-5" and haiku["utility"] == {"name": "luna"}
    assert haiku["chat"]["kwargs"] == m.chat("nativo")["kwargs"], "same proxy, cache and native mode as Sonnet"
    assert saida[1]["chat"]["name"] == "converse/us.anthropic.claude-sonnet-5-5"


def test_sonnet5_do_teste_lado_a_lado():
    saida = m.com_sonnet([{"name": "Default", "utility": {"name": "luna"}}, {"name": "Haiku", "chat": m.chat("nativo", m.HAIKU)}],
                         m.SONNET5, "nativo")
    assert [p["name"] for p in saida] == ["Default", "Haiku", "Sonnet 5 teste"]
    assert saida[-1]["chat"]["name"] == "converse/us.anthropic.claude-sonnet-5", "the model Hermes gets too"
    assert saida[1]["chat"]["name"] == "converse/us.anthropic.claude-haiku-5-5", "his everyday preset untouched"


if __name__ == "__main__":
    test_sonnet5_do_teste_lado_a_lado()
    test_haiku_mesmo_caminho_outro_modelo()
    test_historico_40()
    test_utilitario_do_padrao()
    test_nativo_so_muda_o_modo()
    test_preset_de_teste_nao_mexe_no_sonnet()
    test_sonnet_no_modo_nativo()
    print("ok")

"""The Sonnet preset keeps 40% of the context for history (20/10) and the cheap utility model from Default."""

import importlib.util
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


if __name__ == "__main__":
    test_historico_40()
    test_utilitario_do_padrao()
    print("ok")

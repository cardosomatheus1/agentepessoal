"""The native tool list of each model call carries only the connector tools this chat needs (helpers/sob_demanda.py):
the usual Google ones, GitHub's when the chat talks about code, and the ones activated with the `conector` tool.
Another person's connector does not go at all. Runs before prompt_enxuto (_50), which shortens the local tools.
Any surprise leaves the list as it was."""

import importlib.util
import json
import sys
from pathlib import Path

from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("conectores_carregar", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)
DONOS = _RAIZ / "donos.json"
MAPA = "responses_tool_name_map"  # Agent.DATA_NAME_RESPONSES_TOOL_NAME_MAP: native name -> original ("google.x")


def donos() -> dict:
    try:
        return json.loads(DONOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def dono_da_conversa(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")


class FerramentasDoConector(Extension):
    async def execute(self, call_data: dict | None = None, **kwargs):
        agent = self.agent
        if agent is None or not isinstance(call_data, dict) or not call_data.get("a0_responses_function_tools"):
            return
        try:
            s = carregar.modulo("sob_demanda")
            if not s.ligado():
                return
            mapa = agent.get_data(MAPA) or {}
            if not isinstance(mapa, dict) or not mapa:
                return
            contexto = agent.context
            s.lembrar_codigo(agent)  # GitHub's core set when the chat talks about code (stays: stable list)
            eu = dono_da_conversa(contexto)
            de_outros = {servidor for servidor, dono in donos().items() if dono and dono != eu}
            call_data["a0_responses_function_tools"] = s.filtrar(
                call_data["a0_responses_function_tools"], mapa, set(s.ativas(contexto)), False, de_outros)
        except Exception as exc:  # never in the way of a model call
            print(f"conectores: lista de ferramentas mantida inteira: {type(exc).__name__}: {exc}", flush=True)

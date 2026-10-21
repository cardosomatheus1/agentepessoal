"""In native mode, a tool Agent Zero sends with an empty schema gets its real parameters (helpers/argumentos.esquema),
as Hermes does. Wraps helpers.responses_tools._schema_for_tool once per server; Agent Zero's schema stays whenever it
lists parameters or ours cannot be built."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_ARQ = Path(__file__).resolve().parents[3] / "helpers" / "argumentos.py"
_spec = importlib.util.spec_from_file_location("controle_agente_argumentos_esquema", _ARQ)
argumentos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(argumentos)

MARCA = "_controle_agente_esquema"


class EsquemaDasFerramentas(Extension):
    def execute(self, **kwargs):
        try:
            from helpers import responses_tools as rt

            if getattr(rt._schema_for_tool, MARCA, False):
                return
            original = rt._schema_for_tool
            cache: dict = {}

            def _schema_for_tool(agent, tool_name, prompt):
                base = original(agent, tool_name, prompt)
                if isinstance(base, dict) and base.get("properties"):
                    return base
                try:
                    for caminho in rt.subagents.get_paths(agent, "tools", tool_name + ".py"):
                        if not rt.files.exists(caminho):
                            continue
                        if caminho not in cache:
                            cache[caminho] = argumentos.esquema(Path(caminho).read_text(encoding="utf-8"))
                        return cache[caminho] or base
                except Exception as exc:
                    print(f"controle_agente: esquema de {tool_name}: {exc}", flush=True)
                return base

            setattr(_schema_for_tool, MARCA, True)
            rt._schema_for_tool = _schema_for_tool
            print("controle_agente: ferramentas com esquema de verdade no modo nativo", flush=True)
        except Exception as exc:  # never block the agent over this
            print(f"controle_agente: esquema das ferramentas indisponível: {exc}", flush=True)

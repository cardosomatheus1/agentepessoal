"""History summaries keep their anchors and the person's words (see helpers/ancoras.py).

Agent Zero's helpers/history.py has no hook of its own, but every topic and bulk summary goes through
Agent.call_utility_model (@extensible) with the fw.topic_summary.sys.md system prompt. Other utility calls are
left alone. Also: an empty summary becomes an error, so the messages are never replaced with nothing.
"""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

SISTEMA = "fw.topic_summary.sys.md"


def _ancoras():
    nome = "resumo_seguro_ancoras"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "ancoras.py"
    mtime = caminho.stat().st_mtime
    antigo = sys.modules.get(nome)
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


class Ancoras(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        agent = self.agent
        if not isinstance(data, dict) or agent is None:
            return
        try:
            args, kw = data.get("args") or (), data.get("kwargs") or {}
            # args[0] is the agent itself (bound method)
            system = kw.get("system", args[1] if len(args) > 1 else None)
            message = kw.get("message", args[2] if len(args) > 2 else None)
            if not isinstance(system, str) or not isinstance(message, str):
                return
            if system != agent.read_prompt(SISTEMA):
                return
            ancoras = _ancoras()
        except Exception:
            return
        ancoras.depois_do_resumo(data, message, str(getattr(getattr(agent, "context", None), "id", "") or ""))

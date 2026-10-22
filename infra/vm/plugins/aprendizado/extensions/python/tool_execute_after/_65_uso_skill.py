"""Counts each skill the agent loads (helpers/aprender.registrar_uso), so the ones it wrote and nobody uses can be
archived (22/10). Never raises: the tool already ran."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def aprender():
    caminho = RAIZ / "helpers" / "aprender.py"
    antigo = sys.modules.get("aprendizado_helper")
    if antigo is None or getattr(antigo, "_mtime", None) != caminho.stat().st_mtime:
        spec = importlib.util.spec_from_file_location("aprendizado_helper", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = caminho.stat().st_mtime
        sys.modules["aprendizado_helper"] = m
    return sys.modules["aprendizado_helper"]


class UsoSkill(Extension):
    async def execute(self, tool_name: str = "", response=None, **kwargs):
        try:
            tool = getattr(getattr(self.agent, "loop_data", None), "current_tool", None)
            args = getattr(tool, "args", None) or kwargs.get("tool_args") or {}
            nome = args.get("skill_name") if isinstance(args, dict) else None
            if nome and "skill" in str(tool_name or "").lower():
                aprender().registrar_uso(str(nome))
        except Exception as exc:
            print(f"aprendizado: uso de skill não registrado: {exc}", flush=True)

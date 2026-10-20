"""Tell the model to ask for independent calls together (Hermes Agent's PARALLEL_TOOL_CALL_GUIDANCE): the runner only
helps when the answer brings several calls. Only with native tool calls (a0_api_mode responses): in text mode an answer
carries one call. A fixed text, the same in every call (the prompt cache stays)."""

import importlib.util
import sys
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def _modulo(arquivo: str):
    nome, caminho = f"acoes_paralelas_{arquivo}", RAIZ / "helpers" / f"{arquivo}.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def nativo(agent) -> bool:
    try:
        kwargs = getattr(agent.get_chat_model(), "kwargs", {}) or {}
    except Exception:
        return False
    return str(kwargs.get("a0_api_mode") or "").strip().lower() in ("response", "responses", "responses_api")


class OrientacaoParalelo(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        try:
            if self.agent and nativo(self.agent) and _modulo("executar").ligado():
                system_prompt.append(_modulo("plano").ORIENTACAO)
        except Exception as exc:
            print(f"acoes_paralelas: orientação não entrou: {type(exc).__name__}: {exc}", flush=True)

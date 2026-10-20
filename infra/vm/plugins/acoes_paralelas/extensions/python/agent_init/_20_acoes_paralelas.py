"""Install, once per process, the parallel runner of tool calls (helpers/executar.py) in place of
Agent.process_llm_result_tools. /a0 is not edited: the method is swapped on the class at runtime, and only when
Agent Zero's code is the one this was written against (the md5 of both methods below, read on the VM on 21/10);
any other version keeps Agent Zero's own method and says so in the log."""

import hashlib
import importlib.util
import inspect
import sys
import textwrap
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
CONHECIDOS = {
    "process_llm_result_tools": "d57aba60669f04c2ca382837073e6392",
    "_execute_tool_request": "724264ac450fad4897de10fcb7a4370c",
}
MARCA = "_acoes_paralelas_original"


def executar():
    nome, caminho = "acoes_paralelas_executar", RAIZ / "helpers" / "executar.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def assinatura(funcao) -> str:
    return hashlib.md5(textwrap.dedent(inspect.getsource(funcao)).encode()).hexdigest()


def instalar(classe) -> str:
    """"instalado" | "ja" | "versao diferente: <método>". Idempotent."""
    if getattr(classe, MARCA, None) is not None:
        return "ja"
    for metodo, md5 in CONHECIDOS.items():
        try:
            atual = assinatura(getattr(classe, metodo))
        except (OSError, TypeError, AttributeError):
            atual = ""
        if atual != md5:
            return f"versao diferente: {metodo}"
    original = classe.process_llm_result_tools

    async def process_llm_result_tools(self, llm_result):
        try:
            modulo = executar()
        except Exception as exc:  # the plugin broke: Agent Zero's own way
            print(f"acoes_paralelas: helper não carregou ({type(exc).__name__}: {exc}); execução normal", flush=True)
            return await original(self, llm_result)
        return await modulo.processar(self, llm_result, original)

    process_llm_result_tools.__wrapped__ = original
    setattr(classe, MARCA, original)
    classe.process_llm_result_tools = process_llm_result_tools
    return "instalado"


class AcoesParalelas(Extension):
    def execute(self, **kwargs):
        try:
            from agent import Agent

            r = instalar(Agent)
            if r not in ("ja",):
                print(f"acoes_paralelas: {r}", flush=True)
        except Exception as exc:
            print(f"acoes_paralelas: não instalou ({type(exc).__name__}: {exc})", flush=True)

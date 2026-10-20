"""Replaces Agent Zero's extensions/python/message_loop_end/_10_organize_history.py (same file name: a plugin
extension with the name of a core one is loaded instead of it). Same background task as the core file; the
compression itself is resumo_seguro's (helpers/compressao.py: summarize less often and deeper, keep the task in
progress whole). If the plugin helper cannot load, Agent Zero's own compression runs, as before.

Core file this mirrors (md5 checked by tests/suite.py): 38f8222cdfd7b81216f251a0f9ccffe6."""

import importlib.util
import sys
from pathlib import Path

from agent import LoopData
from helpers.defer import THREAD_BACKGROUND, DeferredTask
from helpers.extension import Extension

DATA_NAME_TASK = "_organize_history_task"


def _compressao():
    nome = "resumo_seguro_compressao"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "compressao.py"
    mtime = caminho.stat().st_mtime
    antigo = sys.modules.get(nome)
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


async def compress_history(agent) -> bool:
    try:
        compressao = _compressao()
    except Exception as exc:
        print(f"resumo_seguro: compressão do Agent Zero (helper não carregou: {type(exc).__name__}: {exc})", flush=True)
        from helpers.history import clear_responses_provider_state

        compressed = bool(await agent.history.compress())
        if compressed:
            clear_responses_provider_state(agent)
        return compressed
    return await compressao.compress_history(agent)


class OrganizeHistory(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return

        # is there a running task? if yes, skip this round, the wait extension will double check the context size
        task: DeferredTask | None = self.agent.get_data(DATA_NAME_TASK)
        if task and not task.is_ready():
            return

        # start task
        task = DeferredTask(thread_name=THREAD_BACKGROUND)
        task.start_task(compress_history, self.agent)
        # set to agent to be able to wait for it
        self.agent.set_data(DATA_NAME_TASK, task)

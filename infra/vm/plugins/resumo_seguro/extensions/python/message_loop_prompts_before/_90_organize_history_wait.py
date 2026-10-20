"""Replaces Agent Zero's extensions/python/message_loop_prompts_before/_90_organize_history_wait.py (same file name):
the same wait, but every compression goes through resumo_seguro's compress_history (the core file imports the core
one by name, which would run Agent Zero's own compression whenever no background task was running).

Core file this mirrors (md5 checked by tests/suite.py): 67051c4aeceb3093a7663fd30e81e80b."""

import importlib.util
import sys
from pathlib import Path

from agent import LoopData
from helpers.defer import DeferredTask
from helpers.extension import Extension

DATA_NAME_TASK = "_organize_history_task"
MAX_SYNC_COMPRESSION_PASSES = 64


def _organizar():
    nome = "resumo_seguro_organizar"
    raiz = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
    caminho = raiz / "extensions" / "python" / "message_loop_end" / "_10_organize_history.py"
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
    return await _organizar().compress_history(agent)


class OrganizeHistoryWait(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return

        # sync action only required if the history is too large, otherwise leave it in background
        passes = 0
        while self.agent.history.is_over_limit():
            passes += 1
            before_tokens = self.agent.history.get_tokens()

            # get task
            task: DeferredTask | None = self.agent.get_data(DATA_NAME_TASK)

            # Check if the task is already done
            if task:
                if not task.is_ready():
                    self.agent.context.log.set_progress("Compressing history...")

                # Wait for the task to complete
                compressed = bool(await task.result())

                # Clear the coroutine data after it's done
                self.agent.set_data(DATA_NAME_TASK, None)
            else:
                # no task was running, start and wait
                self.agent.context.log.set_progress("Compressing history...")
                compressed = await compress_history(self.agent)

            after_tokens = self.agent.history.get_tokens()
            if not compressed or after_tokens >= before_tokens:
                self._log_compression_stalled(before_tokens, after_tokens)
                break

            if passes >= MAX_SYNC_COMPRESSION_PASSES:
                self._log_compression_stalled(
                    before_tokens, after_tokens, max_passes=True
                )
                break

    def _log_compression_stalled(
        self, before_tokens: int, after_tokens: int, max_passes: bool = False
    ) -> None:
        if not self.agent:
            return

        detail = (
            f"History compression stopped after {MAX_SYNC_COMPRESSION_PASSES} passes"
            if max_passes
            else "History compression could not reduce the prompt history further"
        )
        self.agent.context.log.log(
            type="warning",
            heading="History compression stalled",
            content=f"{detail}. Tokens before: {before_tokens}; after: {after_tokens}.",
        )

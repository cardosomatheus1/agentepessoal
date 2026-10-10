"""Keep big tool results out of the history: save them whole to a file, keep head + tail + path.

A tool result stays in the history and is resent with every later model call until the history is
summarized. Terminal dumps, browser states and subordinate reports of 10-50k characters were the
largest single items there. The full text goes to /a0/usr/chats/<chat>/saidas/ (deleted with the
chat); the history keeps the start, the end and how to read the rest. The chat window (log) still
shows the full result.
"""

import re
from pathlib import Path

from helpers.extension import Extension

LIMIT = 8_000  # characters; smaller results stay as they are
HEAD = 5_000
TAIL = 1_500
# the final answer is never cut, nor the overviews whose whole point is to be read at once (capped at ~24k)
SKIP = {"response", "fios", "iniciativa"}


class SalvarGrande(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        if not isinstance(data, dict) or not self.agent:
            return
        result, tool = data.get("tool_result"), str(data.get("tool_name") or "ferramenta")
        if not isinstance(result, str) or len(result) <= LIMIT or tool in SKIP:
            return
        try:
            folder = Path("/a0/usr/chats") / self.agent.context.id / "saidas"
            folder.mkdir(parents=True, exist_ok=True)
            number = sum(1 for _ in folder.glob("*.txt")) + 1
            path = folder / f"{number:04d}-{re.sub(r'[^A-Za-z0-9_.-]', '_', tool)[:40]}.txt"
            path.write_text(result, encoding="utf-8")
        except OSError:
            return  # keep the full result rather than lose it
        omitted = len(result) - HEAD - TAIL
        data["tool_result"] = (
            result[:HEAD]
            + f"\n\n[… {omitted:,} caracteres do meio omitidos do histórico para economizar contexto. "
            f"Resultado completo ({len(result):,} caracteres) em {path}. Se precisar, leia só o trecho "
            f"necessário, por exemplo `grep -n 'termo' {path}` ou `sed -n '100,160p' {path}`.]\n\n"
            + result[-TAIL:]
        )

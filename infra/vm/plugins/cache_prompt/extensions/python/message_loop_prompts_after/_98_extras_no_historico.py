"""Move the per-step extras into the history, keeping only what changed since the last step.

Agent Zero rebuilds an "[EXTRAS]" block (time, open browsers, recalled memories, skills...) on
every model call and appends it after the history. The block differs at each step, and the
Bedrock prompt cache only reuses a previous prompt when the new one starts with all of it — so
no call was ever served from the cache. Here the extras become a normal history message, added
once and only with the keys whose value changed, and the trailing block is left empty (removed
from the prompt by _functions/agent/Agent/prepare_prompt/end). Each prompt then starts with the
whole previous one.

Runs last among the message_loop_prompts_after extensions (after the browser page cap at _21).
"""

from pathlib import Path

from agent import LoopData
from helpers import dirty_json
from helpers.extension import Extension

KEY = "cache_prompt_extras"
PAGE_CHARS = 8_000  # browser page text per snapshot (the browser plugin alone allows 20k)
# One chat id per line, or "*" for every chat; no file = on everywhere.
SWITCH = Path("/a0/usr/plugins/cache_prompt/conversas.txt")


def _on(ctx_id: str) -> bool:
    try:
        ids = {line.strip() for line in SWITCH.read_text().splitlines() if line.strip()}
    except OSError:
        return True
    return "*" in ids or ctx_id in ids


class ExtrasNoHistorico(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        agent = self.agent
        if not agent or not _on(agent.context.id):
            return
        values = {**loop_data.extras_persistent, **loop_data.extras_temporary}
        page = values.get("browser_context")
        if isinstance(page, str) and len(page) > PAGE_CHARS:
            # every page change now stays in the history: keep each snapshot short
            cut = page.rfind("\n", 0, PAGE_CHARS)
            cut = cut if cut > PAGE_CHARS // 2 else PAGE_CHARS
            values["browser_context"] = (
                page[:cut] + f"\n\n[page text cut at {cut:,} of {len(page):,} characters. To read another "
                "part, call the browser tool with action `content` and a CSS `selector`, or `scroll`.]"
            )
        last = agent.get_data(KEY) or {}
        changed = {k: v for k, v in values.items() if last.get(k) != v}
        agent.set_data(KEY, dict(values))
        loop_data.extras_temporary.clear()
        loop_data.extras_persistent.clear()
        if not changed:
            return
        text = agent.read_prompt(
            "agent.context.extras.md", extras=dirty_json.stringify(changed, separators=(",", ":"))
        )
        agent.hist_add_message(False, content=text)
        loop_data.history_output = agent.history.output()

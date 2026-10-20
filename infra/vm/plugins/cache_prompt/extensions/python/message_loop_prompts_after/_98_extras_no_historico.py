"""Move the per-step extras into the history, keeping only what changed since the last step.

Agent Zero rebuilds an "[EXTRAS]" block (time, open browsers, recalled memories, skills...) on
every model call and appends it after the history. The block differs at each step, and the
Bedrock prompt cache only reuses a previous prompt when the new one starts with all of it — so
no call was ever served from the cache. Here the extras become a normal history message, added
once and only with the keys whose value changed, and the trailing block is left empty (removed
from the prompt by _functions/agent/Agent/prepare_prompt/end). Each prompt then starts with the
whole previous one.

20/10 (prompt enxuto): the plugins' volatile blocks (phone notices, loose ends, this chat's contexto.md, the latest
initiative messages) left the system prompt and come here as extras (`loop_data.extras_persistent[key]`), so the start
of the prompt stays the same between calls of a chat. Two fixes make that safe:
- a key that is missing at one step (memories are recalled every 3 steps) is still remembered: when it comes back
  unchanged it is not written again;
- a key whose message was summarized away (history compression) is written again, so a block that only changes once
  in a while (the chat's contexto.md) is never lost from the prompt.

Runs last among the message_loop_prompts_after extensions (after the browser page cap at _21).
"""

from pathlib import Path

from agent import LoopData
from helpers import dirty_json
from helpers.extension import Extension

KEY = "cache_prompt_extras"
IDS = "cache_prompt_extras_ids"  # key -> id of the history message that carries its current value
PAGE_CHARS = 8_000  # browser page text per snapshot (the browser plugin alone allows 20k)
# Keys written again when the message that carries them is more than N history messages behind the end (20/10,
# objetivo_vivo: the request and its steps stay near the end of a long task, like Cline's focus chain). Appending is
# cache-safe: the start of the prompt does not change.
REPETIR = {"objetivo_vivo": 12}
# One chat id per line, or "*" for every chat; no file = on everywhere.
SWITCH = Path("/a0/usr/plugins/cache_prompt/conversas.txt")


def _on(ctx_id: str) -> bool:
    try:
        ids = {line.strip() for line in SWITCH.read_text().splitlines() if line.strip()}
    except OSError:
        return True
    return "*" in ids or ctx_id in ids


def _visiveis(agent, history_output) -> set:
    """Ids of the history messages the model still sees in full (not replaced by a summary)."""
    ids = set()
    for m in history_output or []:
        mid = m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
        if mid:
            ids.add(mid)
    try:
        resumidas = {m.id for m in agent.history.all_messages() if getattr(m, "summary", "")}
    except Exception:
        resumidas = set()
    return ids - resumidas


def longe(ids: dict, history_output, repetir: dict | None = None) -> set:
    """Keys of REPETIR whose carrier message is more than N messages behind the end of the history."""
    repetir = REPETIR if repetir is None else repetir
    saida = list(history_output or [])
    pos = {}
    for i, m in enumerate(saida):
        mid = m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
        if mid:
            pos[mid] = i
    return {k for k, n in repetir.items() if k in ids and ids[k] in pos and len(saida) - 1 - pos[ids[k]] > n}


def mudou(values: dict, last: dict, ids: dict, visiveis: set, distantes: set = frozenset()) -> dict:
    """The keys to write now: new or different value, the message that carried it is gone from the prompt, or it is
    a REPETIR key that fell far behind."""
    return {k: v for k, v in values.items()
            if last.get(k) != v or (k in ids and ids[k] not in visiveis) or k in distantes}


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
        ids = dict(agent.get_data(IDS) or {})
        changed = mudou(values, last, ids, _visiveis(agent, loop_data.history_output),
                        longe(ids, loop_data.history_output))
        agent.set_data(KEY, {**last, **values})
        loop_data.extras_temporary.clear()
        loop_data.extras_persistent.clear()
        if not changed:
            return
        text = agent.read_prompt(
            "agent.context.extras.md", extras=dirty_json.stringify(changed, separators=(",", ":"))
        )
        msg = agent.hist_add_message(False, content=text)
        mid = getattr(msg, "id", None)
        if mid:
            ids.update({k: mid for k in changed})
            agent.set_data(IDS, ids)
        loop_data.history_output = agent.history.output()

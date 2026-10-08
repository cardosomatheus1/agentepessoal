"""Cap the page text the browser plugin adds to every model call.

A big page (e.g. a Wikipedia article: ~260k chars, ~65k tokens) was resent in full at
every step, making each step slower and pricier. Keep the top of the page and tell the
agent how to read the rest on demand.
"""

from agent import LoopData
from helpers.extension import Extension

MAX_CHARS = 20_000  # ~5k tokens per step; the agent reads other parts on demand


class LimitarPagina(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        text = loop_data.extras_temporary.get("browser_context")
        if not isinstance(text, str) or len(text) <= MAX_CHARS:
            return
        cut = text.rfind("\n", 0, MAX_CHARS)
        cut = cut if cut > MAX_CHARS // 2 else MAX_CHARS
        loop_data.extras_temporary["browser_context"] = (
            text[:cut]
            + f"\n\n[page text cut at {cut:,} of {len(text):,} characters to keep steps fast. "
            "To read another part, call the browser tool with action `content` and a CSS `selector` "
            "for that section, or `scroll` and read again.]"
        )

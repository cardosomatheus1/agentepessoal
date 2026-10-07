"""Runtime fixes for Agent Zero's built-in browser (plugins/_browser), applied in place.

1. back/forward waited for "domcontentloaded", which never fires when Chromium restores
   the page from its back/forward cache: every Voltar/Avançar cost a 10 s timeout and
   was reported as a failure, so the agent repeated it.
2. A click that navigates destroys the page's JS context mid-evaluate; the navigation
   happened, but the tool reported "click failed" and the agent retried.
3. Before every model call the agent captures the whole page as text. The capture
   script checked, for every element, the computed style of every ancestor up to
   <html> (elements x depth style lookups): ~6 s on a big page like Wikipedia. We
   serve both capture scripts with that check memoized while a capture runs.
"""

import re

HIDDEN_FUNCTION = re.compile(r"  function isEffectivelyHiddenByAncestor\(element\) \{\n.*?\n  \}\n", re.S)

HIDDEN_MEMO = """  let navegadorRapidoHidden = null;  // WeakMap only while a capture runs
  function isEffectivelyHiddenByAncestor(element) {
    if (!isElementNode(element)) {
      return false;
    }
    const memo = navegadorRapidoHidden;
    if (memo) {
      const known = memo.get(element);
      if (known !== undefined) {
        return known;
      }
    }
    const hidden = Boolean(
      element.hidden
      || element.getAttribute?.("aria-hidden") === "true"
      || isStyleDeclarationHidden(element.getAttribute?.("style"))
      || isComputedStyleHidden(getComputedStyleSafe(element))
      || isEffectivelyHiddenByAncestor(element.parentElement)
    );
    if (memo) {
      memo.set(element, hidden);
    }
    return hidden;
  }
"""


def _memoize_during(source: str, entry: str) -> str | None:
    """Memoize the ancestor check while `entry` (an async capture function) runs."""
    header = f"  async function {entry}("
    if len(HIDDEN_FUNCTION.findall(source)) != 1 or source.count(header) != 1:
        return None
    line_end = source.index("\n", source.index(header)) + 1
    signature = source[source.index(header) + len("  async function "):line_end - 3]  # e.g. capture(payload = null)
    args = signature[signature.index("(") + 1:signature.rindex(")")].split("=")[0].strip()
    wrapper = (
        f"  async function {signature} {{\n"
        f"    navegadorRapidoHidden = new WeakMap();\n"
        f"    try {{\n"
        f"      return await navegadorRapidoOriginal_{entry}({args});\n"
        f"    }} finally {{\n"
        f"      navegadorRapidoHidden = null;\n"
        f"    }}\n"
        f"  }}\n\n"
    )
    source = HIDDEN_FUNCTION.sub(lambda _: HIDDEN_MEMO, source)
    return source.replace(header, wrapper + f"  async function navegadorRapidoOriginal_{entry}(", 1)


def script_rapido(source: str) -> str | None:
    """Page-content script with the ancestor check memoized, or None if it changed upstream."""
    return _memoize_during(source, "capture")


def helper_rapido(source: str) -> str | None:
    """DOM helper script with the same fix, or None if it changed upstream."""
    return _memoize_during(source, "captureDocument")

MARK = "_navegador_rapido_v3"


def aplicar() -> None:
    from plugins._browser.helpers import runtime

    core = runtime._BrowserRuntimeCore
    if getattr(core, MARK, False):
        return

    from patchright.async_api import Error as PlaywrightError

    original_back, original_forward = core.back, core.forward
    original_reference_action = core._reference_action
    original_ensure_content_helper = core._ensure_content_helper
    original_ensure_dom_helper = core._ensure_dom_helper
    fast_source = script_rapido(runtime.CONTENT_HELPER_PATH.read_text(encoding="utf-8"))
    fast_helper = helper_rapido(runtime.DOM_HELPER_PATH.read_text(encoding="utf-8"))
    if fast_source is None or fast_helper is None:
        print("navegador_rapido: capture scripts changed upstream; leaving them as is", flush=True)
        fast_source = fast_helper = None

    # "commit" returns as soon as the history navigation lands; the original then
    # gives the page a short settle (up to 1 s for domcontentloaded).
    async def back(self, browser_id=None, *, wait_until="domcontentloaded"):
        return await original_back(self, browser_id, wait_until="commit")

    async def forward(self, browser_id=None, *, wait_until="domcontentloaded"):
        return await original_forward(self, browser_id, wait_until="commit")

    async def _reference_action(self, helper_method, browser_id, reference_id, text=None):
        try:
            return await original_reference_action(self, helper_method, browser_id, reference_id, text)
        except PlaywrightError as exc:
            msg = str(exc)
            if "context was destroyed" not in msg and "navigation" not in msg.lower():
                raise
            resolved_id = self._resolve_browser_id(browser_id)
            await self._settle(self._page(resolved_id))
            self._maybe_promote(resolved_id)
            return {
                "action": {"ok": True, "navigated": True, "note": "the click opened a new page"},
                "state": await self._state(resolved_id),
            }

    async def _ensure_content_helper(self, page):
        if fast_source is not None:
            self._content_helper_source = fast_source
        return await original_ensure_content_helper(self, page)

    async def _ensure_dom_helper(self, page):
        if fast_helper is not None:
            self._dom_helper_source = fast_helper
        return await original_ensure_dom_helper(self, page)

    core.back, core.forward, core._reference_action = back, forward, _reference_action
    core._ensure_content_helper = _ensure_content_helper
    core._ensure_dom_helper = _ensure_dom_helper
    setattr(core, MARK, True)

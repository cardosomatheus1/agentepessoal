"""Is the focused element of the agent's browser page a text field? The phone viewer asks this
right after a tap, to raise the phone's own keyboard only when the tap landed on one."""

from helpers.api import ApiHandler, Request, Response

from plugins._browser.helpers.runtime import get_runtime

SCRIPT = """(() => {
  let e = document.activeElement;
  for (let i = 0; i < 5 && e; i++) {
    if (e.shadowRoot && e.shadowRoot.activeElement) { e = e.shadowRoot.activeElement; continue; }
    if (e.tagName === "IFRAME") { try { e = e.contentDocument.activeElement; continue; } catch (x) { break; } }
    break;
  }
  if (!e) return { editavel: false, tipo: "" };
  const t = (e.getAttribute("type") || "").toLowerCase();
  const naoTexto = ["button", "submit", "reset", "checkbox", "radio", "range", "color", "file", "image", "hidden"];
  const editavel = e.isContentEditable || e.tagName === "TEXTAREA" || (e.tagName === "INPUT" && !naoTexto.includes(t));
  return { editavel: !!editavel && !e.disabled && !e.readOnly, tipo: editavel ? (t || e.tagName.toLowerCase()) : "",
    tela: [innerWidth, innerHeight, devicePixelRatio, outerWidth, outerHeight, screenX, screenY] };
})()"""


class Foco(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        contexto = str(input.get("context_id") or "").strip()
        if not contexto:
            return {"editavel": False, "tipo": ""}
        runtime = await get_runtime(contexto, create=False)
        if runtime is None:
            return {"editavel": False, "tipo": ""}
        try:
            r = await runtime.call("evaluate", input.get("browser_id"), SCRIPT)
        except Exception as exc:  # page gone, navigating, etc.
            return {"editavel": False, "tipo": "", "erro": str(exc)[:200]}
        valor = (r or {}).get("result") or {}
        return {"editavel": bool(valor.get("editavel")), "tipo": str(valor.get("tipo") or ""), "tela": valor.get("tela")}

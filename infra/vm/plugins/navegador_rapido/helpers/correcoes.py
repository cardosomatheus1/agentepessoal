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
4. type/click with a `selector` (no ref) acted on the FIRST match, even when it is hidden.
   21/10, 99Food login: one password field per login tab. The password went into the
   hidden one, the visible field stayed empty and "Entrar" never enabled. When the first
   form-control match is hidden and another is visible, the visible one is used.
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


ROTULO_FIM = "    return [...new Set(collectedLabels.filter(Boolean))];\n  }\n\n  function getLabelText("
ROTULO_MARCA = "a0RotuloVisual"
# 21/10, Keeta: the page listed the fields as bare numbers ("[input 12]") because their names were not in a <label for>
# but in a separate box above them ("* Address"); the agent typed the address into "Company Website". A field with no
# label of its own now gets the one aria-labelledby points to, or else the short text right before it in the form.
ROTULO_FUNCAO = """  function a0RotuloVisual(element) {
    try {
      const ids = String(element.getAttribute?.("aria-labelledby") || "").split(/\\s+/).filter(Boolean);
      const porId = ids.map((id) => document.getElementById(id)).filter(Boolean)
        .map((n) => String(n.innerText || n.textContent || "").replace(/\\s+/g, " ").trim()).join(" ").trim();
      if (porId) {
        return porId.slice(0, 80);
      }
      let node = element;
      for (let nivel = 0; nivel < 4 && node && node !== document.body; nivel += 1) {
        let irmao = node.previousElementSibling;
        for (let k = 0; irmao && k < 3; k += 1, irmao = irmao.previousElementSibling) {
          if (irmao.querySelector?.("input,textarea,select,button,[contenteditable=true]")) {
            break;
          }
          const texto = String(irmao.innerText || irmao.textContent || "").replace(/\\s+/g, " ").trim()
            .replace(/^\\*\\s*/, "").replace(/\\s*\\*$/, "");
          if (texto && texto.length <= 60) {
            return texto;
          }
          if (texto) {
            break;
          }
        }
        node = node.parentElement;
      }
    } catch {
      // never break the capture over a label guess
    }
    return "";
  }

"""
ROTULO_USO = """    if (!collectedLabels.length && /^(INPUT|TEXTAREA|SELECT)$/.test(String(element?.tagName || "").toUpperCase())) {
      const visual = a0RotuloVisual(element);
      if (visual) {
        collectedLabels.push(visual);
      }
    }
"""


def com_rotulo_visual(source: str) -> str:
    """Fields without a label of their own get the visual one (see ROTULO_FUNCAO); unchanged if upstream changed."""
    if ROTULO_MARCA in source or source.count(ROTULO_FIM) != 1:
        return source
    return source.replace(ROTULO_FIM, ROTULO_USO + ROTULO_FIM.replace("  function getLabelText(",
                                                                      ROTULO_FUNCAO + "  function getLabelText("), 1)


VALOR_FIM = "    fileInputElementFor,\n"
VALOR_MARCA = "a0ValorDe"
# Exposes the current value of a captured field, read after typing (Fix 7).
VALOR_FUNCAO = """    a0ValorDe(referenceId) {
      try {
        const entry = state.entries.get(normalizeReferenceId(referenceId));
        const el = entry && entry.element;
        if (!el) {
          return null;
        }
        const tipo = String(el.getAttribute?.("type") || "").toLowerCase();
        if (tipo === "password") {
          return { valor: null, senha: true };
        }
        const valor = "value" in el ? el.value : el.textContent;
        return { valor: String(valor ?? "").slice(0, 300) };
      } catch {
        return null;
      }
    },
"""


def com_valor_lido(source: str) -> str:
    """Adds a0ValorDe(ref) to the page API; unchanged if upstream changed."""
    if VALOR_MARCA in source or source.count(VALOR_FIM) != 1:
        return source
    return source.replace(VALOR_FIM, VALOR_FIM + VALOR_FUNCAO, 1)


def conferir_digitado(pedido: str, lido) -> str:
    """The note for a typed field: what is in it now, and a warning when it is not what was typed."""
    if not isinstance(lido, dict) or lido.get("senha"):
        return ""
    valor = lido.get("valor")
    if valor is None:
        return ""
    pedido = str(pedido or "")
    norm = lambda t: " ".join(str(t).split()).lower()
    if norm(valor) == norm(pedido) or (pedido and norm(pedido) in norm(valor)):
        return f"✓ conferido: o campo agora contém {valor!r}."
    digitos = lambda t: re.sub(r"\D", "", str(t))
    if digitos(pedido) and digitos(valor) == digitos(pedido):
        return f"✓ conferido: o site formatou como {valor!r} (mesmos números)."
    return (f"⚠️ O campo NÃO ficou com o que você digitou: contém {valor!r} (você mandou {pedido!r}). "
            "O site pode ter reformatado ou recusado. Releia a página; se estiver errado, clique no campo, apague e "
            "digite de novo, ou use outro campo pelo nome.")


def script_rapido(source: str) -> str | None:
    """Page-content script with the ancestor check memoized and visual field labels, or None if it changed upstream."""
    rapido = _memoize_during(source, "capture")
    return com_valor_lido(com_rotulo_visual(rapido)) if rapido is not None else None


def helper_rapido(source: str) -> str | None:
    """DOM helper script with the same fix, or None if it changed upstream."""
    return _memoize_during(source, "captureDocument")

ALVO = "data-a0-alvo"

# (selector) -> a selector for the first VISIBLE match, or "" when the original already
# points at it. Only for form controls: a selector used to read a page section is left as is.
ALVO_VISIVEL = """(sel) => {
  let els;
  try { els = [...document.querySelectorAll(sel)]; } catch (e) { return ""; }
  if (els.length < 2 || !els.every(e => /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(e.tagName))) return "";
  const visivel = e => {
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0";
  };
  const alvo = els.find(visivel);
  if (!alvo || alvo === els[0]) return "";
  document.querySelectorAll("[%s]").forEach(e => e.removeAttribute("%s"));
  alvo.setAttribute("%s", "1");
  return '[%s="1"]';
}""" % (ALVO, ALVO, ALVO, ALVO)


def _alvo_visivel(core) -> None:
    """Fix 4: a form-control selector acts on its first VISIBLE match."""
    original_content = core.content

    # The browser tool resolves a selector to a ref through content({"selector": ...}).
    async def content(self, browser_id=None, payload=None):
        sel = (payload or {}).get("selector") if isinstance(payload, dict) else None
        if isinstance(sel, str) and sel.strip():
            try:
                await self.ensure_started()
                page = self._page(self._resolve_browser_id(browser_id))
                visivel = await page.evaluate(ALVO_VISIVEL, sel, isolated_context=True)
                if visivel:
                    payload = {**payload, "selector": visivel}
            except Exception as exc:  # never block the original over this
                print(f"navegador_rapido: alvo visível: {exc}", flush=True)
        return await original_content(self, browser_id, payload)

    core.content = content
    setattr(core, MARK_ALVO, True)


def _baixados(core) -> None:
    """Fix 5: each download also saved under its real name, registered for the next tool result (downloads.py)."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("navegador_rapido_downloads", Path(__file__).with_name("downloads.py"))
    downloads = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(downloads)
    original_start = core._start

    async def _start(self):
        await original_start(self)
        ctx = getattr(self, "context", None)
        if ctx is None:
            return

        def ouvir(page):
            page.on("download", downloads.salvar)

        for page in ctx.pages:
            ouvir(page)
        ctx.on("page", ouvir)

    core._start = _start
    setattr(core, MARK_BAIXADOS, True)


ARQUIVO = "__arquivo__"  # ref used when the page's file field is hidden (no ref of its own)


def escolher_input(campos: list[dict], caminhos: list[str]) -> int | None:
    """Which <input type=file> gets the files: one whose `accept` takes them, the most recent (last) first.
    campos: [{"accept": ".xlsx,image/*", ...}] in page order."""
    import mimetypes

    def aceita(accept: str, caminho: str) -> bool:
        regras = [r.strip().lower() for r in str(accept or "").split(",") if r.strip()]
        if not regras:
            return True
        ext = "." + caminho.rsplit(".", 1)[-1].lower() if "." in caminho else ""
        mime = (mimetypes.guess_type(caminho)[0] or "").lower()
        return any(r == ext or r == mime or (r.endswith("/*") and mime.startswith(r[:-1])) for r in regras)

    for i in range(len(campos) - 1, -1, -1):
        if all(aceita(campos[i].get("accept", ""), c) for c in caminhos):
            return i
    return None


async def enviar_pelo_campo(page, caminhos: list[str]) -> int | None:
    """Puts the files in the page's file field, hidden or not (Playwright allows it); returns its index or None."""
    campos = page.locator("input[type=file]")
    infos = [{"accept": await campos.nth(i).get_attribute("accept") or ""} for i in range(await campos.count())]
    i = escolher_input(infos, caminhos)
    if i is not None:
        await campos.nth(i).set_input_files(caminhos)
    return i


def argumentos_de_upload(args) -> bool:
    """upload_file with only a selector goes straight to the page's file field. The tool resolves a selector to a
    ref and a hidden file field has none ("could not resolve selector 'input[type=file]'"); the tool class is
    reloaded on every call, so this is done on its arguments (tool_execute_before), not by patching it."""
    if not isinstance(args, dict):
        return False
    acao = str(args.get("action", "")).strip().lower().replace("-", "_")
    if acao != "upload_file" or str(args.get("ref") or "").strip():
        return False
    args["ref"] = ARQUIVO
    return True


def _envio_de_arquivo(core) -> None:
    """Fix 6: upload_file also works on a hidden file field (21/10: claude.ai's attach input has no ref, and the
    agent gave up after 'could not resolve selector' and 'cannot upload through helper-backed reference').
    A ref that is not a file field (the attach button) falls back to the page's file field too."""
    original_upload = core.upload_file

    async def upload_file(self, browser_id, ref, path="", paths=None):
        erro = None
        if ref != ARQUIVO:
            try:
                return await original_upload(self, browser_id, ref, path=path, paths=paths)
            except Exception as exc:
                erro = exc
        caminhos = self._normalize_upload_paths(path=path, paths=paths)
        await self.ensure_started()
        resolved_id = self._resolve_browser_id(browser_id)
        page = self._page(resolved_id)
        i = await enviar_pelo_campo(page, caminhos)
        if i is None:
            raise erro or ValueError("a página não tem campo de arquivo que aceite esse arquivo; clique antes no botão "
                                     "de anexar (ele cria o campo) e tente upload_file de novo")
        await self._settle(page, short=True)
        self._maybe_promote(resolved_id)
        return {"action": {"files": caminhos, "input": {"via": "campo de arquivo da página", "indice": i},
                           "ref": ref},
                "state": await self._state(resolved_id)}

    core.upload_file = upload_file
    setattr(core, MARK_ARQUIVO, True)


MARK = "_navegador_rapido_v3"
MARK_ALVO = "_navegador_rapido_alvo"
MARK_BAIXADOS = "_navegador_rapido_baixados"
MARK_ARQUIVO = "_navegador_rapido_arquivo"
MARK_DIGITADO = "_navegador_rapido_digitado"


def _conferir_digitacao(core) -> None:
    """Fix 7: after type/type_submit the field is read back and the result says what it holds now (OpenClaw does not
    do this; its snapshot shows value=, ours now says it right in the typing result)."""
    import asyncio

    for nome in ("type", "type_submit"):
        original = getattr(core, nome)

        async def digitar(self, browser_id, reference_id, text, _original=original):
            resultado = await _original(self, browser_id, reference_id, text)
            try:
                await asyncio.sleep(0.3)
                page = self._page(self._resolve_browser_id(browser_id))
                lido = await page.evaluate(
                    "(ref) => globalThis.__spaceBrowserPageContent__.a0ValorDe ? "
                    "globalThis.__spaceBrowserPageContent__.a0ValorDe(ref) : null",
                    reference_id, isolated_context=True)
                nota = conferir_digitado(text, lido)
                if nota and isinstance(resultado, dict):
                    resultado["conferido"] = nota
            except Exception as exc:  # a page that navigated after Enter has nothing to read: fine
                print(f"navegador_rapido: conferir digitação: {exc}", flush=True)
            return resultado

        setattr(core, nome, digitar)
    setattr(core, MARK_DIGITADO, True)


def _atualizar_script_vivo(core) -> None:
    """The fast capture script is fixed when the server first applies these fixes, inside the wrapper's closure; a
    server already running (deploys do not restart the agent) gets a newer version of it swapped in here."""
    for cell in getattr(core._ensure_content_helper, "__closure__", None) or ():
        try:
            atual = cell.cell_contents
        except ValueError:
            continue
        if isinstance(atual, str) and "navegadorRapidoHidden" in atual and (
                ROTULO_MARCA not in atual or VALOR_MARCA not in atual):
            cell.cell_contents = com_valor_lido(com_rotulo_visual(atual))


def aplicar() -> None:
    from plugins._browser.helpers import runtime

    core = runtime._BrowserRuntimeCore
    if not getattr(core, MARK_ALVO, False):
        _alvo_visivel(core)
    if not getattr(core, MARK_BAIXADOS, False):
        _baixados(core)
    if not getattr(core, MARK_ARQUIVO, False):
        _envio_de_arquivo(core)
    if not getattr(core, MARK_DIGITADO, False):
        _conferir_digitacao(core)
    if getattr(core, MARK, False):
        _atualizar_script_vivo(core)
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

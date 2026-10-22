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
VIVO_MARCA = "a0VivoV1"  # the page functions that find the live element (also through the DOM helper)
# Exposes the current value of a captured field, read after typing (Fix 7).
VALOR_FUNCAO = """    a0ValorDe(referenceId) {
      try {
        const vivo = (entry) => {
          if (entry && entry.element && entry.element.isConnected) {
            return entry.element;
          }
          const h = globalThis.__spaceBrowserDomHelper__;
          const cadeia = entry && Array.isArray(entry.frameChain) ? entry.frameChain : [];
          return h && h.a0Elemento && entry && entry.nodeId && cadeia.length === 1 && cadeia[0] === h.frameId
            ? h.a0Elemento(entry.nodeId) : null;
        };  // a0VivoV1
        const entry = state.entries.get(normalizeReferenceId(referenceId));
        const el = vivo(entry);
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


# Item 12 (Hermes browser_vision annotate, OpenClaw screenshot-annotate.ts): the screenshot shows each ref's number on
# its element, so what the agent sees in the image is what it can click by ref (it used to guess x,y or the wrong ref).
ROTULOS_MARCA = "a0Rotulos"
ROTULOS_ID = "__a0_rotulos__"
ROTULOS_MAX = 150
ROTULOS_FUNCAO = """    a0Rotulos(mostrar) {
      try {
        document.getElementById("%(id)s")?.remove();
        if (!mostrar) {
          return 0;
        }
        const caixa = document.createElement("div");
        caixa.id = "%(id)s";
        caixa.style.cssText = "position:fixed;left:0;top:0;width:0;height:0;z-index:2147483647;pointer-events:none";
        let n = 0;
        const vivo = (entry) => {
            if (entry && entry.element && entry.element.isConnected) {
              return entry.element;
            }
            const h = globalThis.__spaceBrowserDomHelper__;
            const cadeia = entry && Array.isArray(entry.frameChain) ? entry.frameChain : [];
            return h && h.a0Elemento && entry && entry.nodeId && cadeia.length === 1 && cadeia[0] === h.frameId
              ? h.a0Elemento(entry.nodeId) : null;
          };  // a0VivoV1
        for (const [ref, entry] of state.entries) {
          const el = vivo(entry);
          if (!el || !el.isConnected || !el.getBoundingClientRect) {
            continue;
          }
          const r = el.getBoundingClientRect();
          if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.right < 0 || r.top > innerHeight || r.left > innerWidth) {
            continue;
          }
          const t = document.createElement("div");
          t.textContent = String(ref);
          t.style.cssText = "position:fixed;left:" + Math.max(0, r.left - 2) + "px;top:" + Math.max(0, r.top - 2) +
            "px;font:bold 11px/13px monospace;color:#000;background:#ffe500;border:1px solid #000;padding:0 2px;" +
            "border-radius:3px;opacity:0.92";
          caixa.appendChild(t);
          if (++n >= %(max)d) {
            break;
          }
        }
        document.documentElement.appendChild(caixa);
        return n;
      } catch {
        return 0;
      }
    },
""" % {"id": ROTULOS_ID, "max": ROTULOS_MAX}


def com_rotulos(source: str) -> str:
    """Adds a0Rotulos(show) to the page API; unchanged if upstream changed."""
    if ROTULOS_MARCA in source or source.count(VALOR_FIM) != 1:
        return source
    return source.replace(VALOR_FIM, VALOR_FIM + ROTULOS_FUNCAO, 1)


# 21/10, 99 portal (caso marcado pelo operador): the agent typed §§secret(NOVENTAENOVE) into the field "Insira o número de
# telefone do gerente" (ref 21) and only noticed afterwards. A vault secret now goes only into a password field (type
# password, or a name/label of password), unless the secret itself is an identifier (e-mail, user, CPF...).
DESCREVER_JS = """const a0Descrever = (el) => {
    // only a field one types into; a component's host (closed shadow root), a frame from another site or a wrapper says
    // nothing about the real field inside, so it is not read (and not blocked)
    if (!el || !/^(INPUT|TEXTAREA|SELECT)$/.test(String(el.tagName || "").toUpperCase()) && !el.isContentEditable) {
      return null;
    }
    const at = (n) => String(el.getAttribute?.(n) || "");
    const rotulos = [];
    try {
      for (const l of el.labels || []) {
        rotulos.push(l.innerText || l.textContent || "");
      }
      for (const id of at("aria-labelledby").split(/\\s+/).filter(Boolean)) {
        rotulos.push(el.ownerDocument.getElementById(id)?.textContent || "");
      }
    } catch {}
    return { tag: String(el.tagName).toLowerCase(), tipo: String(("type" in el ? el.type : at("type")) || "").toLowerCase(),
             texto: [at("name"), at("id"), at("autocomplete"), at("placeholder"), at("aria-label"), at("title"), ...rotulos]
               .filter(Boolean).join(" | ").replace(/\\s+/g, " ").slice(0, 400) };
  };"""
CAMPO_MARCA = "a0Campo"
CAMPO_FUNCAO = """    a0Campo(referenceId) {
      try {
        const vivo = (entry) => {
          if (entry && entry.element && entry.element.isConnected) {
            return entry.element;
          }
          const h = globalThis.__spaceBrowserDomHelper__;
          const cadeia = entry && Array.isArray(entry.frameChain) ? entry.frameChain : [];
          return h && h.a0Elemento && entry && entry.nodeId && cadeia.length === 1 && cadeia[0] === h.frameId
            ? h.a0Elemento(entry.nodeId) : null;
        };  // a0VivoV1
        %s
        return a0Descrever(vivo(state.entries.get(normalizeReferenceId(referenceId))));
      } catch {
        return null;
      }
    },
""" % DESCREVER_JS
# by ref: the page function (a page opened before this deploy only has a0ValorDe, which knows type=password)
CAMPO_POR_REF_JS = """(ref) => {
  const p = globalThis.__spaceBrowserPageContent__;
  if (p && p.a0Campo) {
    return p.a0Campo(ref);
  }
  const v = p && p.a0ValorDe ? p.a0ValorDe(ref) : null;
  return v ? { tag: "", tipo: v.senha ? "password" : "", texto: "" } : null;
}"""
CAMPO_FOCADO_JS = """() => {
  %s
  let el = document.activeElement;
  try {
    while (el && ((el.tagName === "IFRAME" && el.contentDocument) || el.shadowRoot?.activeElement)) {
      el = el.tagName === "IFRAME" ? el.contentDocument.activeElement : el.shadowRoot.activeElement;
    }
  } catch {}
  return a0Descrever(el);
}""" % DESCREVER_JS
CAMPO_POR_SELETOR_JS = """(sel) => {
  %s
  let els = [];
  try {
    els = [...document.querySelectorAll(sel)];
  } catch {
    return null;
  }
  const visivel = els.find((e) => e.getClientRects().length && getComputedStyle(e).visibility !== "hidden");
  return a0Descrever(visivel || els[0] || null);
}""" % DESCREVER_JS
SEGREDO = re.compile(r"§§secret\(([^)]+)\)")
SEGREDO_IDENTIFICADOR = re.compile(r"E_?MAIL|USUARIO|USER|LOGIN|CPF|CNPJ|TELEFONE|PHONE|CELULAR|WHATSAPP", re.I)
CAMPO_DE_SENHA = re.compile(r"senha|pass(?!a|port)|\bpwd\b|\bpin\b|token|chave|api.?key|secret|segredo", re.I)
DIGITAR = {"type", "type_submit", "typesubmit", "keyboard"}
MARK_CAMPO = "_navegador_rapido_campo"


def com_campo(source: str) -> str:
    """Adds a0Campo(ref) to the page API; unchanged if upstream changed."""
    if CAMPO_MARCA in source or source.count(VALOR_FIM) != 1:
        return source
    return source.replace(VALOR_FIM, VALOR_FIM + CAMPO_FUNCAO, 1)


def segredos_a_digitar(args) -> list[str]:
    """Names of the vault secrets a browser call would type ([] for any other call)."""
    if not isinstance(args, dict) or str(args.get("action", "")).strip().lower() not in DIGITAR:
        return []
    return [n for n in SEGREDO.findall(str(args.get("text") or ""))
            if CAMPO_DE_SENHA.search(n) or not SEGREDO_IDENTIFICADOR.search(n)]  # SENHA_USUARIO_99 is a password


def segredo_no_campo(args, campo) -> str:
    """The refusal for typing a vault password into a field that is not for passwords ('' = may type). campo: what
    core.a0_campo read ({"tag", "tipo", "texto"}), None when the field could not be read (then it is not blocked)."""
    nomes = segredos_a_digitar(args)
    if not nomes or not isinstance(campo, dict):
        return ""
    if campo.get("tipo") == "password" or CAMPO_DE_SENHA.search(str(campo.get("texto") or "")):
        return ""
    descricao = str(campo.get("texto") or "").strip() or f"<{campo.get('tag') or 'campo'}> sem rótulo"
    return (f"NÃO digitei §§secret({nomes[0]}): o campo onde ele iria não é de senha ({descricao[:160]}). Senha do cofre só "
            "vai em campo de senha. Se este campo pede outro dado (telefone, e-mail, nome), use o dado certo, nunca um "
            "segredo; se você queria o campo de senha, leia a página (`content`) e use a ref dele.")


def _campo(core) -> None:
    async def a0_campo(self, browser_id, ref=None, seletor=""):
        page = self._page(self._resolve_browser_id(browser_id))
        if not _sem(ref):
            return await page.evaluate(CAMPO_POR_REF_JS, str(ref), isolated_context=True)
        if str(seletor or "").strip():
            return await page.evaluate(CAMPO_POR_SELETOR_JS, str(seletor), isolated_context=True)
        return await page.evaluate(CAMPO_FOCADO_JS, isolated_context=True)

    core.a0_campo = a0_campo
    setattr(core, MARK_CAMPO, True)


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
    return com_campo(com_rotulos(com_valor_lido(com_rotulo_visual(rapido)))) if rapido is not None else None


ELEMENTO_FIM = "    captureDocument(payload) {\n      return captureDocument(payload);\n    },\n"
ELEMENTO_MARCA = "a0Elemento"
# 21/10: on most sites the page reading goes through the DOM helper and each ref keeps only a parsed COPY of its element
# (entry.element is not on the page), so reading a typed field back (Fix 7) and the ref numbers on the print found
# nothing. The helper keeps the live element of each node id in its own frame; this exposes it.
ELEMENTO_FUNCAO = """    a0Elemento(nodeId) {
      return elementsByNodeId.get(String(nodeId)) || null;
    },
"""


def com_elemento_vivo(source: str) -> str:
    if ELEMENTO_MARCA in source or source.count(ELEMENTO_FIM) != 1:
        return source
    return source.replace(ELEMENTO_FIM, ELEMENTO_FIM + ELEMENTO_FUNCAO, 1)


def helper_rapido(source: str) -> str | None:
    """DOM helper script with the same fix, or None if it changed upstream."""
    rapido = _memoize_during(source, "captureDocument")
    return com_elemento_vivo(rapido) if rapido is not None else None

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


# Item 1 of docs/AUDITORIA_MATURIDADE_AGENTE.md (OpenClaw act:wait, pw-tools-core.interactions.content.ts:146): the
# agent could only sleep a fixed time, then re-read the page again and again until the loop detector stopped it.
# browser {"action": "wait", "text"|"text_gone"|"selector"|"url"|"load": ..., "timeout": s} waits for the condition.
ESPERA_JS = """async (c) => {
  const fim = Date.now() + c.ms, comeco = Date.now();
  const norm = (t) => String(t || "").replace(/\\s+/g, " ").toLowerCase();
  const visivel = (sel) => { try { return [...document.querySelectorAll(sel)].some((e) => {
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none"; }); } catch (e) { return false; } };
  const pronto = () => {
    const corpo = norm(document.body ? document.body.innerText : "");
    if (c.text && !corpo.includes(norm(c.text))) return false;
    if (c.text_gone && corpo.includes(norm(c.text_gone))) return false;
    if (c.selector && !visivel(c.selector)) return false;
    if (c.url && !location.href.includes(c.url)) return false;
    if (c.load && document.readyState !== "complete") return false;
    return true;
  };
  while (true) {
    if (pronto()) return { ok: true, esperou_s: Math.round((Date.now() - comeco) / 100) / 10, url: location.href };
    if (Date.now() >= fim) return { ok: false, esperou_s: c.ms / 1000, url: location.href,
      aviso: "não aconteceu no tempo: releia a página (content) e veja o que mudou; talvez outra aba, um aviso por cima ou a ação anterior não pegou" };
    await new Promise((r) => setTimeout(r, 250));
  }
}"""
ESPERA_CHAVES = ("text", "text_gone", "selector", "url", "load")


def argumentos_de_espera(args) -> bool:
    """browser wait → an evaluate that polls the page for the condition (at most 60 s)."""
    import json

    if not isinstance(args, dict):
        return False
    acao = str(args.get("action", "")).strip().lower().replace("-", "_")
    if acao not in ("wait", "wait_for", "esperar"):
        return False
    cond = {k: args.get(k) for k in ESPERA_CHAVES if args.get(k) not in (None, "", False)}
    if not cond:
        cond = {"load": True}
    try:
        segundos = float(args.get("timeout") or args.get("seconds") or 15)
    except (TypeError, ValueError):
        segundos = 15.0
    cond["ms"] = int(max(1.0, min(segundos, 60.0)) * 1000)
    for k in ESPERA_CHAVES + ("timeout", "seconds"):
        args.pop(k, None)
    args["action"] = "evaluate"
    args["script"] = f"({ESPERA_JS})({json.dumps(cond, ensure_ascii=False)})"
    return True


def _original(core, nome: str, livre: str):
    """The unpatched method: kept on the class since v2 of a fix; from an older wrapper's closure (`livre` is the name of
    the variable that held it) on a server that is still running an older version (deploys do not restart the agent)."""
    guardado = getattr(core, f"_a0_original_{nome}", None)
    if guardado is not None:
        return guardado
    atual = getattr(core, nome)
    codigo = getattr(atual, "__code__", None)
    if codigo is not None and livre in codigo.co_freevars and atual.__closure__:
        atual = atual.__closure__[codigo.co_freevars.index(livre)].cell_contents
    setattr(core, f"_a0_original_{nome}", atual)
    return atual


async def pelo_seletor_de_arquivos(page, ponto: dict, caminhos: list[str], espera_ms: int = 6000) -> bool:
    """Item 8 (OpenClaw pw-tools-core.downloads.ts:256-268): click the trigger with the mouse and hand the files to the
    file window it opens. Outlook, 21/10: several hidden file fields, and the one picked by `enviar_pelo_campo` sent the
    file to OneDrive ("Carregar em"); its "Navegar neste computador" opens the window the email attachment listens to."""
    try:
        async with page.expect_file_chooser(timeout=espera_ms) as janela:
            await page.mouse.click(float(ponto["x"]), float(ponto["y"]))
        await (await janela.value).set_files(caminhos)
        return True
    except Exception:
        return False


# Outlook, 21/10 (again): the agent called upload_file with only a selector, so the file went to a hidden field and
# Outlook answered "Não foi possível anexar" or opened OneDrive's "Carregar em". With no ref, the tool now looks for the
# trigger itself: an open "from this computer" item first, else the attach button (which may open that menu).
GATILHO_COMPUTADOR = r"(neste|deste|do|meu) (computador|dispositivo)|this (computer|device)|my (computer|device)|browse (files|computer|this)|procurar (arquivo|no computador)|upload from (computer|device)|carregar do (computador|dispositivo)"
GATILHO_ANEXAR = r"^(anexar|anexo|attach|adicionar arquivo|add file|enviar arquivo|carregar arquivo|upload( file)?|escolher arquivo|selecionar arquivo|choose file|select file)\b|anexar arquivo|attach file"
ACHAR_GATILHO_JS = """(padrao) => {
  const re = new RegExp(padrao, "i");
  const visivel = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && r.bottom > 0 && r.top < innerHeight; };
  const alvos = [...document.querySelectorAll('button,[role=button],[role=menuitem],[role=option],a,label,[tabindex]')];
  for (const e of alvos) {
    const t = ((e.getAttribute("aria-label") || "") + " " + (e.innerText || "") + " " + (e.getAttribute("title") || "")).replace(/\\s+/g, " ").trim();
    if (!t || t.length > 80 || !re.test(t) || !visivel(e)) continue;
    const r = e.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2, texto: t.slice(0, 60) };
  }
  return null;
}"""


async def achar_gatilho(page, padrao: str) -> dict | None:
    try:
        return await page.evaluate(ACHAR_GATILHO_JS, padrao)
    except Exception:
        return None


async def pelo_gatilho_da_pagina(page, caminhos: list[str]) -> str:
    """No ref given: an open "from this computer" item, else the attach button and then that item. Returns what was
    clicked, or "" when no click opened a file window."""
    ponto = await achar_gatilho(page, GATILHO_COMPUTADOR)
    if ponto and await pelo_seletor_de_arquivos(page, ponto, caminhos, espera_ms=4000):
        return ponto["texto"]
    anexar = await achar_gatilho(page, GATILHO_ANEXAR)
    if not anexar:
        return ""
    if await pelo_seletor_de_arquivos(page, anexar, caminhos, espera_ms=2500):  # the button itself opens the window
        return anexar["texto"]
    ponto = None
    for _ in range(16):  # it opened a menu instead: up to ~4 s for its items (slow pages, a busy machine)
        await page.wait_for_timeout(250)
        ponto = await achar_gatilho(page, GATILHO_COMPUTADOR)
        if ponto:
            break
    if ponto and await pelo_seletor_de_arquivos(page, ponto, caminhos, espera_ms=4000):
        return f"{anexar['texto']} → {ponto['texto']}"
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    return ""


def _envio_de_arquivo(core) -> None:
    """Fix 6: upload_file also works on a hidden file field (21/10: claude.ai's attach input has no ref, and the
    agent gave up after 'could not resolve selector' and 'cannot upload through helper-backed reference').
    v2 (item 8): a ref that is not a file field is the trigger: click it and use the file window it opens; only then
    the page's file field."""
    original_upload = _original(core, "upload_file", "original_upload")

    async def upload_file(self, browser_id, ref, path="", paths=None):
        erro = None
        caminhos = self._normalize_upload_paths(path=path, paths=paths)
        await self.ensure_started()
        resolved_id = self._resolve_browser_id(browser_id)
        page = self._page(resolved_id)
        via = ""
        if ref != ARQUIVO:
            try:
                return await original_upload(self, browser_id, ref, path=path, paths=paths)
            except Exception as exc:
                erro = exc
            try:
                ponto = await self._point_for(page, ref)
                if await pelo_seletor_de_arquivos(page, ponto, caminhos):
                    via = "janela de arquivos aberta pelo clique"
            except Exception:
                pass
        else:
            clicado = await pelo_gatilho_da_pagina(page, caminhos)
            if clicado:
                via = f"janela de arquivos aberta por '{clicado}'"
        indice = None
        if not via:
            indice = await enviar_pelo_campo(page, caminhos)
            if indice is None:
                raise erro or ValueError("a página não tem campo de arquivo que aceite esse arquivo; use upload_file com a "
                                         "ref do botão que abre a escolha de arquivo (ex.: 'Anexar', 'Navegar neste "
                                         "computador')")
            via = "campo de arquivo da página"
        await self._settle(page, short=True)
        self._maybe_promote(resolved_id)
        return {"action": {"files": caminhos, "input": {"via": via, "indice": indice}, "ref": ref,
                           "conferir": "veja no print se o arquivo aparece anexado; se o site abriu outra janela (ex.: "
                                       "OneDrive), feche-a e use a ref do botão de anexar do computador"},
                "state": await self._state(resolved_id)}

    core.upload_file = upload_file
    setattr(core, MARK_ARQUIVO, VERSAO_ARQUIVO)


MARK = "_navegador_rapido_v3"
MARK_ALVO = "_navegador_rapido_alvo"
MARK_BAIXADOS = "_navegador_rapido_baixados"
MARK_ARQUIVO = "_navegador_rapido_arquivo"
VERSAO_ARQUIVO = 3
MARK_DIALOGO = "_navegador_rapido_dialogo"
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


def _celulas(fn, profundidade: int = 4):
    """Closure cells of a wrapper and of the wrappers it wraps (other fixes wrap the same method)."""
    for cell in getattr(fn, "__closure__", None) or ():
        yield cell
        try:
            dentro = cell.cell_contents
        except ValueError:
            continue
        if profundidade and callable(dentro) and getattr(dentro, "__closure__", None):
            yield from _celulas(dentro, profundidade - 1)


def _atualizar_script_vivo(core) -> None:
    """The fast capture scripts are fixed when the server first applies these fixes, inside the wrappers' closures; a
    server already running (deploys do not restart the agent) gets the newer versions swapped in here, rebuilt from
    Agent Zero's own files (the old ones carry older versions of our functions)."""
    import sys

    modulo = sys.modules.get(getattr(core, "__module__", ""), None)

    def do_arquivo(nome, montar, atual):
        caminho = getattr(modulo, nome, None)
        try:
            novo = montar(caminho.read_text(encoding="utf-8")) if caminho is not None else None
        except OSError:
            novo = None
        return novo or atual

    for cell in _celulas(core._ensure_content_helper):
        try:
            atual = cell.cell_contents
        except ValueError:
            continue
        if isinstance(atual, str) and "navegadorRapidoHidden" in atual and (VIVO_MARCA not in atual
                                                                            or CAMPO_MARCA not in atual):
            novo = do_arquivo("CONTENT_HELPER_PATH", script_rapido, None)
            cell.cell_contents = novo or com_campo(com_rotulos(com_valor_lido(com_rotulo_visual(atual))))
    for cell in _celulas(getattr(core, "_ensure_dom_helper", None)):
        try:
            atual = cell.cell_contents
        except ValueError:
            continue
        if isinstance(atual, str) and "captureDocument" in atual and ELEMENTO_MARCA not in atual:
            cell.cell_contents = do_arquivo("DOM_HELPER_PATH", helper_rapido, None) or com_elemento_vivo(atual)


# --- Item 5: JavaScript dialogs (alert / confirm / prompt / beforeunload) ---------------------------------------------
# Playwright dismisses any dialog nobody listens to: a site's "Excluir? OK/Cancelar" became Cancelar, the page did not
# change and the agent saw "click ok". OpenClaw (pw-session-dialogs.ts, armDialog) and Hermes (browser_dialog_tool.py)
# record the dialog and let the agent answer. Here: alert → OK; beforeunload → leave (the agent asked to navigate);
# confirm/prompt → the answer the agent armed with {"action": "dialog", "accept": true} (that goes through the
# approvals, which review browser actions before this runs), else Cancelar, the safe answer. Every dialog is reported
# in the next browser result.
DIALOGOS = "_a0_dialogos"   # on the core class: {context_id: [dialogs not yet reported]}
ARMADO = "_a0_dialogo_armado"  # on the core class: {context_id: {"accept": bool, "text": str}}


def _tabela(core, nome: str) -> dict:
    if not isinstance(getattr(core, nome, None), dict):
        setattr(core, nome, {})
    return getattr(core, nome)


async def responder_dialogo(core, contexto: str, dialogo) -> dict:
    tipo = str(getattr(dialogo, "type", "") or "")
    armado = _tabela(core, ARMADO).pop(contexto, None)
    if tipo == "alert":
        await dialogo.accept()
        resposta = "OK (era só um aviso)"
    elif armado is not None and tipo in ("confirm", "prompt"):
        if armado.get("accept"):
            texto = armado.get("text")
            await (dialogo.accept(str(texto)) if texto not in (None, "") else dialogo.accept())
            resposta = "OK (como você deixou armado)"
        else:
            await dialogo.dismiss()
            resposta = "Cancelar (como você deixou armado)"
    elif tipo == "beforeunload":
        await dialogo.accept()
        resposta = "Sair da página (a navegação que você pediu seguiu)"
    else:
        await dialogo.dismiss()
        resposta = "Cancelar (padrão seguro)"
    item = {"tipo": tipo, "mensagem": str(getattr(dialogo, "message", "") or "")[:300], "resposta": resposta}
    _tabela(core, DIALOGOS).setdefault(contexto, []).append(item)
    return item


def aviso_dialogos(itens: list[dict]) -> str:
    linhas = []
    for i in itens:
        linha = f"🗨️ O site abriu uma janela ({i['tipo']}): «{i['mensagem']}». Respondi: {i['resposta']}."
        if i["resposta"].startswith("Cancelar (padrão"):
            linha += (' Se era para confirmar (e a ação foi pedida ou já está autorizada), chame browser '
                      '{"action": "dialog", "accept": true} e repita a mesma ação.')
        linhas.append(linha)
    return ("\n\n" + "\n".join(linhas)) if linhas else ""


def argumentos_de_dialogo(args, contexto: str, core) -> bool:
    """browser {"action": "dialog", "accept": bool, "text": "..."} arms the answer to the next dialog of this chat;
    the tool itself then just reports the page state."""
    if not isinstance(args, dict) or str(args.get("action", "")).strip().lower() not in ("dialog", "dialogo", "diálogo"):
        return False
    aceitar = args.get("accept")
    aceitar = aceitar if isinstance(aceitar, bool) else str(aceitar).strip().lower() in ("1", "true", "sim", "yes", "ok")
    _tabela(core, ARMADO)[contexto] = {"accept": aceitar, "text": args.get("text") or args.get("value") or ""}
    for k in ("accept", "value", "text"):
        args.pop(k, None)
    args["action"] = "state"
    return True


# --- Item 9: the page's own errors and failed requests ----------------------------------------------------------------
# "I clicked and nothing happened" had no diagnosis: Hermes (browser_console) and OpenClaw (console/requests/errors)
# show the page's console errors, JS exceptions and failed requests. Collected per chat (last 40) and shown with
# browser {"action": "erros"}.
EVENTOS = "_a0_eventos"
EVENTOS_MAX = 40


def registrar_evento(core, contexto: str, tipo: str, texto: str) -> None:
    lista = _tabela(core, EVENTOS).setdefault(contexto, [])
    lista.append({"tipo": tipo, "texto": str(texto or "")[:300]})
    del lista[:-EVENTOS_MAX]


def argumentos_de_erros(args, contexto: str, core) -> str:
    """browser {"action": "erros"} → the page state, plus the collected errors (returned, to add to the result)."""
    if not isinstance(args, dict) or str(args.get("action", "")).strip().lower() not in (
            "erros", "errors", "console", "requests", "rede"):
        return ""
    args["action"] = "state"
    eventos = _tabela(core, EVENTOS).pop(contexto, [])
    if not eventos:
        return "\n\n🔎 Nenhum erro da página nem chamada falhando desde a última vez que olhei."
    linhas = [f"- [{e['tipo']}] {e['texto']}" for e in eventos[-15:]]
    return ("\n\n🔎 Erros da página e chamadas que falharam (mais recentes por último):\n" + "\n".join(linhas)
            + "\nUse isso para entender por que a ação não teve efeito (ex.: 400/422 = o site recusou os dados; "
              "401/403 = sessão ou permissão; 500 = erro do site, tente de novo depois).")


def _ouvintes(core) -> None:
    """Listeners on every page the tool touches: JS dialogs (item 5) and errors/failed requests (item 9)."""
    import asyncio

    original = core._ensure_content_helper

    async def _ensure_content_helper(self, page):
        if not getattr(page, "_a0_ouve_dialogo", False):
            contexto = str(getattr(self, "context_id", "") or "")
            classe = type(self)

            def ao_abrir(dialogo):
                asyncio.ensure_future(responder_dialogo(classe, contexto, dialogo))

            def no_console(msg):
                if getattr(msg, "type", "") == "error":
                    registrar_evento(classe, contexto, "console", msg.text)

            def na_resposta(resp):
                try:
                    if resp.status >= 400 and resp.request.resource_type in ("xhr", "fetch", "document"):
                        registrar_evento(classe, contexto, f"HTTP {resp.status}", f"{resp.request.method} {resp.url}")
                except Exception:
                    pass

            page.on("dialog", ao_abrir)
            page.on("console", no_console)
            page.on("pageerror", lambda exc: registrar_evento(classe, contexto, "erro JS", str(exc)))
            page.on("requestfailed", lambda req: registrar_evento(
                classe, contexto, "falhou", f"{req.method} {req.url} ({getattr(req, 'failure', '') or ''})"))
            page.on("response", na_resposta)
            try:
                page._a0_ouve_dialogo = True
            except Exception:
                pass
        return await original(self, page)

    core._ensure_content_helper = _ensure_content_helper
    setattr(core, MARK_DIALOGO, True)


# ---- 21/10, from the agent's own logs (4 days, every browser call): the failures that repeat the most ----

# 55 failed clicks: `click` with `selector` and no ref ("could not resolve selector \"button[aria-label='Next']\"").
# The tool only maps a selector to a ref of the page reading, and many elements have none. The selector now goes
# straight to the page: CSS, `text=...` or `:has-text(...)`; the first visible match is clicked with the mouse.
PONTO_DO_SELETOR_JS = """(sel) => {
  const visivel = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none"; };
  const norm = (t) => String(t || "").replace(/\\s+/g, " ").trim().toLowerCase();
  let lista = [];
  const texto = sel.match(/^text\\s*=\\s*["']?(.+?)["']?$/i) || sel.match(/:has-text\\(\\s*["'](.+?)["']\\s*\\)/i);
  if (texto) {
    const t = norm(texto[1]);
    const todos = [...document.querySelectorAll("a,button,[role],input,label,span,div,li,td,p,h1,h2,h3,h4,option")];
    const iguais = todos.filter((e) => norm(e.innerText || e.value || e.getAttribute("aria-label")) === t);
    lista = (iguais.length ? iguais : todos.filter((e) => norm(e.innerText).includes(t)))
      .sort((a, b) => a.getBoundingClientRect().width * a.getBoundingClientRect().height
                    - b.getBoundingClientRect().width * b.getBoundingClientRect().height);
  } else {
    try { lista = [...document.querySelectorAll(sel)]; } catch (e) { return { erro: "seletor inválido" }; }
  }
  const e = lista.find(visivel);
  if (!e) return { achados: lista.length };
  e.scrollIntoView({ block: "center", inline: "center" });
  const r = e.getBoundingClientRect(), tag = e.tagName.toLowerCase();
  return { achados: lista.length, x: r.x + r.width / 2, y: r.y + r.height / 2, tag,
           campo: e.isContentEditable || tag === "input" || tag === "textarea" };
}"""
COM_SELETOR = {"click", "double_click", "right_click", "hover", "type", "type_submit", "typesubmit"}


def _sem(v) -> bool:
    return v is None or str(v).strip() == ""


async def resolver_seletor(args, chamar) -> str:
    """click/hover/type with only a selector → the mouse on the element the page itself finds. `chamar(method, *a)` is
    runtime.call. Returns a note for the result ('' when nothing was done)."""
    if not isinstance(args, dict):
        return ""
    acao = str(args.get("action", "")).strip().lower().replace("-", "_")
    seletor = str(args.get("selector") or "").strip()
    if acao not in COM_SELETOR or not seletor or not _sem(args.get("ref")) or args.get("x") or args.get("y"):
        return ""
    bid = args.get("browser_id")
    ponto = await chamar("a0_ponto_do_seletor", bid, seletor)
    if not isinstance(ponto, dict) or "x" not in ponto:
        achados = (ponto or {}).get("achados", 0) if isinstance(ponto, dict) else 0
        return (f"\n↻ O seletor {seletor!r} não achou elemento visível na página ({achados} escondido(s)). Leia a página "
                "(`content`) e use a ref do elemento, ou clique pelas coordenadas do print.")
    args.pop("selector", None)
    if acao in ("click", "double_click", "right_click", "hover"):
        args["x"], args["y"] = ponto["x"], ponto["y"]
        return ""
    # type/type_submit: click into the field, replace what is there, type; Enter for type_submit
    await chamar("mouse", bid, "click", ponto["x"], ponto["y"])
    if ponto.get("campo"):
        await chamar("key_chord", bid, ["Control", "a"])
    if acao == "type":
        args["action"] = "keyboard"
        args["key"] = ""
        return ""
    await chamar("keyboard", bid, key="", text=str(args.get("text") or ""))
    args["action"], args["key"], args["text"] = "keyboard", "Enter", ""
    return ""


# 8 failures "Unknown key: ARROWDOWN" / "ENTER": the agent writes key names in capitals.
TECLAS = {t.lower(): t for t in (
    "Enter", "Escape", "Tab", "Backspace", "Delete", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End",
    "PageUp", "PageDown", "Insert", "Space", "Control", "Shift", "Alt", "Meta", "F1", "F2", "F3", "F4", "F5", "F6",
    "F7", "F8", "F9", "F10", "F11", "F12")}
TECLAS.update({"esc": "Escape", "return": "Enter", "del": "Delete", "up": "ArrowUp", "down": "ArrowDown",
               "left": "ArrowLeft", "right": "ArrowRight", "ctrl": "Control", "cmd": "Meta", "pgup": "PageUp",
               "pgdn": "PageDown", "spacebar": "Space"})


def tecla(nome: str) -> str:
    """'ENTER' → 'Enter', 'ctrl+A' → 'Control+a' (a single letter stays lower case, as typed)."""
    partes = [p.strip() for p in str(nome or "").split("+")] if len(str(nome or "")) > 1 else [str(nome or "")]
    return "+".join(TECLAS.get(p.lower(), p.lower() if len(p) == 1 and len(partes) > 1 else p) for p in partes)


def argumentos_de_teclas(args) -> bool:
    if not isinstance(args, dict):
        return False
    mudou = False
    if isinstance(args.get("key"), str) and args["key"] and tecla(args["key"]) != args["key"]:
        args["key"], mudou = tecla(args["key"]), True
    if isinstance(args.get("keys"), str) and args["keys"].strip():
        # 21/10: keys "Control+a" / "Backspace" as one string were pressed letter by letter (typed "Backspace")
        args["keys"], mudou = [tecla(k) for k in args["keys"].split("+") if k.strip()], True
    if isinstance(args.get("keys"), list):
        novas = [tecla(k) if isinstance(k, str) else k for k in args["keys"]]
        if novas != args["keys"]:
            args["keys"], mudou = novas, True
    return mudou


# 21/10 night report: 25 clicks with ref "button 22" / "editable 64" (the agent copied the label of "[button 22]" from
# the page reading) and 3 key_chord calls with `key` or `text` instead of `keys`.
REF_ESCRITA = re.compile(r"^\[?\s*[A-Za-z][\w -]*?\s+(\d+)\s*\]?$")


def argumentos_de_ref(args) -> bool:
    """ref "button 22" or "[editable 64]" -> "22" / "64"; key_chord with key/text "Control+a" -> keys ["Control", "a"]."""
    if not isinstance(args, dict):
        return False
    mudou = False
    for campo in ("ref", "target_ref"):
        valor = args.get(campo)
        m = REF_ESCRITA.match(valor.strip()) if isinstance(valor, str) else None
        if m:
            args[campo], mudou = m.group(1), True
    acao = str(args.get("action", "")).strip().lower().replace("-", "_")
    if acao in ("key_chord", "keychord") and not args.get("keys"):
        texto = str(args.get("key") or args.get("text") or "").strip()
        if texto:
            args["keys"] = [t.strip() for t in texto.split("+") if t.strip()]
            args.pop("key", None)
            args.pop("text", None)
            mudou = True
    return mudou


# 9 + 3 + 1 failures "ref is required for this browser action": scroll/detail/type_submit without a ref.
def argumentos_de_rolagem(args) -> bool:
    """scroll with no ref → turn the mouse wheel in the middle of the page (down, or up when asked)."""
    if not isinstance(args, dict):
        return False
    acao = str(args.get("action", "")).strip().lower()
    if acao != "scroll" or not _sem(args.get("ref")) or str(args.get("selector") or "").strip():
        return False
    direcao = str(args.get("direction") or args.get("direcao") or "down").lower()
    try:
        quanto = abs(float(args.get("delta_y") or args.get("amount") or args.get("pixels") or 700))
    except (TypeError, ValueError):
        quanto = 700.0
    args.update(action="wheel", x=float(args.get("x") or 640), y=float(args.get("y") or 400), delta_x=0,
                delta_y=-quanto if direcao in ("up", "cima", "acima", "top") else quanto)
    for k in ("direction", "direcao", "amount", "pixels"):
        args.pop(k, None)
    return True


# 6 failures in 3 chats (21-22/10) "Browser 73 is not open.": the agent kept the id of a tab already closed (by itself
# or by the `limpeza` plugin) and the tool only said that. A navigate there is an open of the same address; any other
# action keeps the error (its page is gone: no switching tabs in the dark) with what is open and what to do.
SEM_ABA = {"open", "list", "list_all", "close_all"}
MARK_ABAS = "_navegador_rapido_abas"


def aba_fechada(args, abertas) -> str:
    """args: the browser call; abertas: the ids open in this chat (core.a0_abas). Returns a note for the result."""
    if not isinstance(args, dict) or _sem(args.get("browser_id")):
        return ""
    acao = str(args.get("action", "")).strip().lower()
    valor = str(args["browser_id"]).strip()
    valor = valor.split("-", 1)[1] if valor.startswith("browser-") else valor
    try:
        bid = int(valor)
    except ValueError:
        return ""
    abertas = [int(a) for a in abertas or []]
    if acao in SEM_ABA or bid in abertas:
        return ""
    if acao == "navigate" and str(args.get("url") or "").strip():
        args["action"] = "open"
        args.pop("browser_id")
        return (f"\n↻ A aba {bid} já tinha sido fechada: pedi o endereço numa aba nova (`open`). Se deu certo, use o id "
                "novo deste resultado daqui em diante.")
    return (f"\n↻ A aba {bid} já foi fechada (abas abertas nesta conversa: {', '.join(map(str, abertas)) or 'nenhuma'}). "
            "Abra a página de novo com `open` e a URL, leia (`content`) e refaça a ação com as referências novas.")


def _abas(core) -> None:
    async def a0_abas(self):  # started first: tabs saved before a restart only come back then
        await self.ensure_started()
        return list(self._context_browser_ids())

    core.a0_abas = a0_abas
    setattr(core, MARK_ABAS, True)


# 17 failures "cannot select helper-backed reference": a list drawn by the site (not a <select>). The tool now opens
# it with the mouse and clicks the option by its text, like a person.
OPCAO_JS = """(valor) => {
  const norm = (t) => String(t || "").replace(/\\s+/g, " ").trim().toLowerCase();
  const v = norm(valor);
  const visivel = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none"; };
  const todos = [...document.querySelectorAll('[role=option],[role=menuitem],[role=treeitem],li,[class*=option],[class*=item],div,span')]
    .filter(visivel);
  const iguais = todos.filter((e) => norm(e.innerText) === v);
  const lista = iguais.length ? iguais : todos.filter((e) => norm(e.innerText).startsWith(v));
  lista.sort((a, b) => a.getBoundingClientRect().width * a.getBoundingClientRect().height
                     - b.getBoundingClientRect().width * b.getBoundingClientRect().height);
  const e = lista[0];
  if (!e) return null;
  e.scrollIntoView({ block: "center" });
  const r = e.getBoundingClientRect();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2, texto: norm(e.innerText).slice(0, 60) };
}"""
MARK_LISTA = "_navegador_rapido_lista"
VERSAO_LISTA = 3  # 2: typing into a box drawn by the site replaces its text (21/10); 3: also a ref with no point


def _lista_do_site(core) -> None:
    original_select = _original(core, "select_option", "original_select")
    original_type = _original(core, "type", "original_type")

    async def select_option(self, browser_id, ref, value="", values=None):
        try:
            return await original_select(self, browser_id, ref, value=value, values=values)
        except Exception as exc:
            if "helper-backed" not in str(exc) and "not a <select>" not in str(exc).lower() \
                    and "cannot select" not in str(exc).lower():
                raise
            erro = exc
        alvo = (values or [value])[0] if (values or value) else ""
        resolved_id = self._resolve_browser_id(browser_id)
        page = self._page(resolved_id)
        ponto = await self._point_for(page, ref)
        await page.mouse.click(float(ponto["x"]), float(ponto["y"]))
        opcao = None
        for _ in range(12):  # up to ~3 s for the options to appear
            await page.wait_for_timeout(250)
            opcao = await page.evaluate(OPCAO_JS, str(alvo))
            if opcao:
                break
        if not opcao:
            raise ValueError(f"{erro} — abri a lista, mas não achei a opção {alvo!r}; veja o print e clique na opção "
                             "pelo texto ou pelas coordenadas")
        await page.mouse.click(float(opcao["x"]), float(opcao["y"]))
        await self._settle(page, short=True)
        self._maybe_promote(resolved_id)
        return {"action": {"ok": True, "via": "lista do site aberta com o mouse", "opcao": opcao["texto"]},
                "state": await self._state(resolved_id)}

    # 3 failures "cannot type into <div>": a text box drawn by the site (contenteditable editors, search boxes).
    # 21/10: the Instagram Direct box kept what was there and each `type` added the text again (sent twice would be
    # worse than not sending): typing into a box drawn by the site now replaces what it holds, like a normal field.
    async def type(self, browser_id, reference_id, text):
        try:
            page = self._page(self._resolve_browser_id(browser_id))
            try:
                ponto = await self._point_for(page, reference_id)
            except Exception:
                ponto = None
            if ponto is not None:
                if await page.evaluate(EDITAVEL_CHEIO_JS, [float(ponto["x"]), float(ponto["y"])]):
                    await page.mouse.click(float(ponto["x"]), float(ponto["y"]))
                    await page.keyboard.press("Control+a")
                    await page.keyboard.press("Delete")
            else:
                # 21/10, 2nd time: the Direct box is a "helper-backed" ref (inside a frame) with no point, and the
                # clearing was skipped. The tool's own `scroll` reaches it and focuses it without a click (a wrong ref,
                # e.g. the Send button, is not pressed); only a focused box drawn by the site with text is cleared.
                await self.scroll(browser_id, reference_id)
                cheio = False
                for frame in page.frames:
                    try:
                        cheio = cheio or bool(await frame.evaluate(FOCADO_CHEIO_JS))
                    except Exception:
                        continue
                if cheio:
                    await page.keyboard.press("Control+a")
                    await page.keyboard.press("Delete")
        except Exception as exc:  # the original type decides
            print(f"navegador_rapido: limpar caixa antes de digitar: {exc}", flush=True)
        try:
            return await original_type(self, browser_id, reference_id, text)
        except Exception as exc:
            if "cannot type into" not in str(exc):
                raise
        resolved_id = self._resolve_browser_id(browser_id)
        page = self._page(resolved_id)
        ponto = await self._point_for(page, reference_id)
        await page.mouse.click(float(ponto["x"]), float(ponto["y"]))
        await page.keyboard.press("Control+a")
        await page.keyboard.type(str(text))
        await self._settle(page, short=True)
        lido = await page.evaluate("() => (document.activeElement && (document.activeElement.value ?? "
                                   "document.activeElement.innerText) || '').slice(0, 300)")
        return {"action": {"ok": True, "via": "clique + teclado (caixa de texto feita pelo site)"},
                "conferido": conferir_digitado(text, {"valor": lido}), "state": await self._state(resolved_id)}

    async def a0_ponto_do_seletor(self, browser_id, seletor):
        page = self._page(self._resolve_browser_id(browser_id))
        return await page.evaluate(PONTO_DO_SELETOR_JS, str(seletor))

    core.select_option, core.type, core.a0_ponto_do_seletor = select_option, type, a0_ponto_do_seletor
    setattr(core, MARK_LISTA, VERSAO_LISTA)
    print(f"navegador_rapido: caixa do site v{VERSAO_LISTA} instalada", flush=True)


FOCADO_CHEIO_JS = """() => {
  const a = document.activeElement;
  const caixa = a && a.closest && a.closest('[contenteditable]:not([contenteditable="false"])');
  return !!(caixa && caixa.innerText.trim());
}"""
EDITAVEL_CHEIO_JS = """([x, y]) => {
  const el = document.elementFromPoint(x, y);
  const caixa = el && el.closest('[contenteditable]:not([contenteditable="false"])');
  return !!(caixa && caixa.innerText.trim());
}"""


# 15 + 4 failures "Connection closed while reading from the driver": the browser process died and every later call
# failed the same way until the agent gave up (the context still looks alive to the tool). Now the dead browser is
# dropped and started again; open/navigate/list/state are repeated, other actions say to reopen the page.
CAIU = ("connection closed while reading from the driver", "browser has been closed",
        "target page, context or browser has been closed", "browser.new_context: target closed")
REPETIR_DEPOIS_DE_CAIR = {"open", "navigate", "list", "state"}
MARK_CAIU = "_navegador_rapido_caiu"


def navegador_caiu(exc) -> bool:
    texto = str(exc).lower()
    return any(c in texto for c in CAIU)


def _reinicio_se_cair(runtime_mod) -> None:
    classe = runtime_mod.BrowserRuntime
    original_call_for = _original(classe, "call_for", "original_call_for")

    async def call_for(self, context_id, method, *args, **kwargs):
        try:
            return await original_call_for(self, context_id, method, *args, **kwargs)
        except Exception as exc:
            if method in ("close", "close_context", "a0_reiniciar") or not navegador_caiu(exc):
                raise
            print(f"navegador_rapido: o navegador caiu ({exc}); reiniciando", flush=True)
            await original_call_for(self, context_id, "a0_reiniciar")
            if method in REPETIR_DEPOIS_DE_CAIR:
                return await original_call_for(self, context_id, method, *args, **kwargs)
            raise RuntimeError(f"{exc} — o navegador tinha caído e já foi reiniciado. Abra a página de novo (open ou "
                               "navigate), leia (content) e refaça esta ação.") from exc

    async def a0_reiniciar(self):
        await self._discard_stale_context("navegador_rapido: browser driver died; restarting")

    classe.call_for = call_for
    runtime_mod._BrowserRuntimeCore.a0_reiniciar = a0_reiniciar
    setattr(classe, MARK_CAIU, True)


MARK_PRINT = "_navegador_rapido_print_rotulado"
VERSAO_PRINT = 2  # a version on the class: a server already running gets the newer wrapper (deploys do not restart)
ROTULAR_JS = ("(mostrar) => globalThis.__spaceBrowserPageContent__ && globalThis.__spaceBrowserPageContent__.a0Rotulos ? "
              "globalThis.__spaceBrowserPageContent__.a0Rotulos(mostrar) : -1")


async def _no_mundo_do_ajudante(page, js, arg):
    """The page API lives in patchright's isolated world; plain Playwright (tests) has no such argument."""
    try:
        return await page.evaluate(js, arg, isolated_context=True)
    except TypeError:
        return await page.evaluate(js, arg)


def _print_rotulado(core) -> None:
    """Each screenshot of the visible area: read the page again (the refs the agent gets next are numbered the same way,
    in page order), draw the numbers, take the picture, remove them."""
    original = _original(core, "screenshot_file", "original_print")

    async def screenshot_file(self, browser_id=None, *, quality=80, full_page=False, path=""):
        page = None
        if not full_page:
            try:
                page = self._page(self._resolve_browser_id(browser_id))
                await self.content(browser_id, None)
                n = await _no_mundo_do_ajudante(page, ROTULAR_JS, True)
                if n <= 0:
                    print(f"navegador_rapido: print sem números ({'script antigo na página' if n < 0 else 'nada visível'})",
                          flush=True)
                    page = None
            except Exception as exc:
                print(f"navegador_rapido: print sem números: {type(exc).__name__}: {exc}", flush=True)
                page = None
        try:
            resultado = await original(self, browser_id, quality=quality, full_page=full_page, path=path)
        finally:
            if page is not None:
                try:
                    await _no_mundo_do_ajudante(page, ROTULAR_JS, False)
                except Exception:
                    pass
        if page is not None and isinstance(resultado, dict):
            resultado["rotulos"] = "os números amarelos no print são as refs: clique com action=click e essa ref"
        return resultado

    core.screenshot_file = screenshot_file
    setattr(core, MARK_PRINT, VERSAO_PRINT)
    print(f"navegador_rapido: print com números v{VERSAO_PRINT} instalado", flush=True)


def aplicar() -> None:
    from plugins._browser.helpers import runtime

    core = runtime._BrowserRuntimeCore
    if not getattr(core, MARK_ALVO, False):
        _alvo_visivel(core)
    if not getattr(core, MARK_BAIXADOS, False):
        _baixados(core)
    if getattr(core, MARK_ARQUIVO, False) != VERSAO_ARQUIVO:
        _envio_de_arquivo(core)
    if not getattr(core, MARK_DIGITADO, False):
        _conferir_digitacao(core)
    if not getattr(core, MARK_DIALOGO, False):
        _ouvintes(core)
    if getattr(core, MARK_LISTA, False) != VERSAO_LISTA:
        _lista_do_site(core)
    if getattr(core, MARK_PRINT, False) != VERSAO_PRINT:
        _print_rotulado(core)
    if not getattr(runtime.BrowserRuntime, MARK_CAIU, False):
        _reinicio_se_cair(runtime)
    if not getattr(core, MARK_ABAS, False):
        _abas(core)
    if not getattr(core, MARK_CAMPO, False):
        _campo(core)
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

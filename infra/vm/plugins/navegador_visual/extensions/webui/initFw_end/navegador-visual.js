// Browser, Computer and Phone panels that work on a phone and on a PC: full screen on narrow screens,
// the xpra on-screen keyboard (Browser and Computer) hidden until asked for, and in the Browser zoom
// out/in (bigger remote screen drawn smaller) plus a bar that types with the device's own keyboard.
import { store as browser } from "/plugins/_browser/webui/browser-store.js";
import { getNamespacedClient } from "/js/websocket.js";
import { callJsonApi } from "/js/api.js";

const websocket = getNamespacedClient("/ws");
const ZOOMS = [1, 1.25, 1.5, 2, 2.5];
const CHAVE_ZOOM = "a0-navegador-zoom";
const CSS_ID = "a0-navegador-visual-css";
const CSS_FRAME_ID = "a0-navegador-visual-teclado";
// Chromium does not shrink its window below ~500 px, so on a phone the page came out wider than the
// panel and cut off on the right: below this width the remote screen grows and is drawn smaller.
const LARGURA_MINIMA = 540;

const CSS = `
  .browser-stage { --nv-zoom: 1; }
  .browser-stage .browser-interactive-frame {
    width: calc(100% * var(--nv-zoom)) !important;
    height: calc(100% * var(--nv-zoom)) !important;
    transform: scale(calc(1 / var(--nv-zoom)));
    transform-origin: 0 0;
  }
  .nv-grupo { display: inline-flex; align-items: center; gap: 2px; margin-left: 4px; }
  .nv-grupo .nv-pct { font-size: 12px; min-width: 38px; text-align: center; opacity: .8; font-variant-numeric: tabular-nums; }
  .nv-grupo button.is-active { color: var(--color-primary, #6c8cff); }
  .nv-barra { display: none; gap: 6px; padding: 6px 8px; align-items: center;
    border-top: 1px solid var(--color-border, #333); background: var(--color-background, #111); }
  .browser-panel.nv-digitando .nv-barra { display: flex; }
  .nv-barra input { flex: 1; min-width: 0; font-size: 16px; padding: 8px 10px; border-radius: 8px;
    border: 1px solid var(--color-border, #444); background: var(--color-input, #1b1b1b); color: inherit; }
  .nv-barra button { font-size: 14px; padding: 8px 10px; border-radius: 8px; white-space: nowrap; }
  .nv-teclado-modal.is-active { color: var(--color-primary, #6c8cff); }
  .celular-panel .celular-frame { min-height: 60vh; }
  @media (max-width: 760px) {
    .modal-inner.surface-modal {
      position: fixed !important; left: 0 !important; top: 0 !important;
      width: 100vw !important; height: 100dvh !important;
      max-width: 100vw !important; max-height: 100dvh !important; min-width: 0 !important; min-height: 0 !important;
      border-radius: 0 !important; resize: none !important; transform: none !important; margin: 0 !important;
    }
    .browser-annotate-toggle .surface-control-label, .browser-annotate-toggle span { display: none; }
    .browser-toolbar { flex-wrap: wrap; row-gap: 4px; }
    .celular-panel .celular-frame { min-height: calc(100dvh - 260px); }
  }
`;

let zoom = 1;
let tecladoXpra = false;
try {
  const salvo = Number(localStorage.getItem(CHAVE_ZOOM));
  if (ZOOMS.includes(salvo)) zoom = salvo;
} catch {}

function fator(larguraPainel) {
  return larguraPainel > 0 ? Math.max(zoom, LARGURA_MINIMA / larguraPainel) : zoom;
}

function aplicarZoomNoPainel() {
  for (const stage of document.querySelectorAll(".browser-stage")) {
    const f = fator(stage.getBoundingClientRect().width);
    stage.style.setProperty("--nv-zoom", f.toFixed(4));
    const pct = stage.closest(".browser-panel")?.querySelector(".nv-pct");
    if (pct) pct.textContent = `${Math.round(f * 100)}%`;
  }
}

function mudarZoom(passo) {
  const i = Math.max(0, Math.min(ZOOMS.length - 1, ZOOMS.indexOf(zoom) + passo));
  if (ZOOMS[i] === zoom) return;
  zoom = ZOOMS[i];
  try { localStorage.setItem(CHAVE_ZOOM, String(zoom)); } catch {}
  aplicarZoomNoPainel();
  browser.queueViewportSync?.(true);
}

const FRAMES_XPRA = ".browser-interactive-frame, .office-desktop-frame";

function aplicarTecladoNoFrame() {
  for (const frame of document.querySelectorAll(FRAMES_XPRA)) {
    if (!frame.__nvLoad) {
      frame.__nvLoad = true;
      frame.addEventListener("load", () => setTimeout(() => {
        aplicarTecladoNoFrame();
        if (frame.classList.contains("browser-interactive-frame")) ouvirToques(frame);
      }, 300));
    }
    try {
      const doc = frame.contentDocument;
      if (!doc?.head) continue;
      let style = doc.getElementById(CSS_FRAME_ID);
      if (!style) {
        style = doc.createElement("style");
        style.id = CSS_FRAME_ID;
        doc.head.appendChild(style);
      }
      const css = tecladoXpra ? "" : ".simple-keyboard { display: none !important; }";
      if (style.textContent !== css) style.textContent = css;
    } catch {}
  }
  for (const b of document.querySelectorAll(".nv-teclado, .nv-teclado-modal")) b.classList.toggle("is-active", tecladoXpra);
}

function alternarTeclado() {
  tecladoXpra = !tecladoXpra;
  aplicarTecladoNoFrame();
}

// Computer panel: a keyboard button among the modal's header actions.
function montarComputador(modal) {
  if (modal.__nvMontado) return;
  const acoes = modal.querySelector(".surface-modal-actions");
  if (!acoes) return;
  modal.__nvMontado = true;
  const b = document.createElement("button");
  b.type = "button";
  b.className = "surface-button modal-surface-button nv-teclado-modal";
  b.title = "Mostrar/esconder o teclado na tela";
  b.setAttribute("aria-label", b.title);
  b.innerHTML = '<x-icon name="keyboard"></x-icon>';
  b.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); alternarTeclado(); });
  acoes.prepend(b);
}

async function enviar(payload) {
  const contextId = browser.normalizeContextId?.(browser.activeBrowserContextId || browser.contextId);
  if (!contextId || !browser.activeBrowserId) return;
  await websocket.emit("browser_viewer_input", {
    context_id: contextId,
    browser_id: browser.activeBrowserId,
    viewer_id: browser._viewerToken,
    input_type: "keyboard",
    key: "",
    text: "",
    ...payload,
  });
}

// Phone keyboard: a tap that lands on a text field of the page raises the phone's own keyboard
// (the page itself is only a picture of the agent's browser, so nothing native would open), and what
// is typed goes to that field; a tap elsewhere, or the phone's Back, puts it away. The hidden field
// keeps a one-character sentinel so Backspace still fires when it is "empty", and every change is sent
// as a diff, which also covers word prediction and autocorrect.
const TOQUE = globalThis.matchMedia?.("(pointer: coarse)");
const SENTINELA = "\u00a0";
let nativo = null;
let enviado = "";
let compondo = false;
let fila = Promise.resolve();
let toques = 0;

function mandar(payload) {
  fila = fila.then(() => enviar(payload)).catch(() => {});
}

function zerarCampo() {
  enviado = "";
  nativo.value = SENTINELA;
  try { nativo.setSelectionRange(1, 1); } catch {}
}

function sincronizar() {
  const atual = nativo.value;
  const antes = SENTINELA + enviado;
  let p = 0;
  while (p < antes.length && p < atual.length && antes[p] === atual[p]) p++;
  for (let i = 0; i < antes.length - p; i++) mandar({ key: "Backspace" });
  const novo = atual.slice(p);
  if (novo) mandar({ text: novo });
  if (!atual.startsWith(SENTINELA)) { if (!compondo) zerarCampo(); else enviado = atual; return; }
  enviado = atual.slice(1);
  if (!compondo && enviado.length > 80) zerarCampo();
}

function campoNativo() {
  if (nativo) return nativo;
  nativo = document.createElement("input");
  nativo.id = "nv-teclado-nativo";
  nativo.type = "text";
  for (const [k, v] of Object.entries({ autocomplete: "off", autocorrect: "off", autocapitalize: "none", spellcheck: "false", "aria-hidden": "true" })) nativo.setAttribute(k, v);
  Object.assign(nativo.style, { position: "fixed", left: "0", bottom: "0", width: "1px", height: "1px", opacity: "0",
    border: "0", padding: "0", fontSize: "16px", zIndex: "-1", caretColor: "transparent" });
  nativo.addEventListener("compositionstart", () => { compondo = true; });
  nativo.addEventListener("compositionend", () => { compondo = false; sincronizar(); });
  nativo.addEventListener("input", sincronizar);
  nativo.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      mandar({ key: e.key });
      zerarCampo();
    }
    e.stopPropagation();
  });
  document.body.appendChild(nativo);
  return nativo;
}

async function depoisDoToque(x, y) {
  const meu = ++toques;
  const alturaAntes = globalThis.visualViewport?.height || innerHeight;
  await fila; // the click has reached the page
  await new Promise((r) => setTimeout(r, 200));
  const contextId = browser.normalizeContextId?.(browser.activeBrowserContextId || browser.contextId);
  if (!contextId || !browser.activeBrowserId) return;
  let foco = {};
  try {
    foco = await callJsonApi("/plugins/navegador_visual/foco", { context_id: contextId, browser_id: browser.activeBrowserId });
  } catch {}
  guardarGeo(foco?.tela);
  if (meu !== toques) return;
  if (foco?.editavel) {
    const c = campoNativo();
    const tipo = foco.tipo === "password" ? "password" : "text";
    if (c.type !== tipo) c.type = tipo;
    zerarCampo();
    c.focus({ preventScroll: true });
    setTimeout(() => diag("toque-campo", { x: Math.round(x), y: Math.round(y), tipo: foco.tipo, focado: document.activeElement === c,
      ativacao: !!navigator.userActivation?.isActive, alturaAntes, alturaDepois: globalThis.visualViewport?.height || innerHeight }), 700);
  } else {
    if (nativo && document.activeElement === nativo) nativo.blur();
    diag("toque", { x: Math.round(x), y: Math.round(y), editavel: !!foco?.editavel, erro: foco?.erro || "", geo: [geo.esquerda, geo.topo, geo.dpr] });
  }
}

const VERSAO = "toque-4";

function diag(evento, dados = {}) {
  callJsonApi("/plugins/navegador_visual/diag", { evento, versao: VERSAO, ...dados }).catch(() => {});
}

function alvo() {
  const contextId = browser.normalizeContextId?.(browser.activeBrowserContextId || browser.contextId);
  return contextId && browser.activeBrowserId ? { context_id: contextId, browser_id: browser.activeBrowserId, viewer_id: browser._viewerToken } : null;
}

// The agent's Chromium window sits partly above the screen (its tab and address bars are pushed out of
// view), so a point on the live view is not the same point on the page: page = (screen - viewport
// corner) / devicePixelRatio, with the corner taken from the page's own window metrics.
const geo = { esquerda: 0, topo: 0, dpr: 1 };

function guardarGeo(tela) {
  if (!Array.isArray(tela) || tela.length < 7) return;
  const [iw, ih, dpr, ow, oh, sx, sy] = tela.map(Number);
  geo.dpr = dpr || 1;
  geo.esquerda = sx + Math.max(0, ow - iw * geo.dpr);
  geo.topo = sy + Math.max(0, oh - ih * geo.dpr);
}

async function atualizarGeo() {
  const a = alvo();
  if (!a) return;
  try { guardarGeo((await callJsonApi("/plugins/navegador_visual/foco", { context_id: a.context_id, browser_id: a.browser_id }))?.tela); } catch {}
}

const naPagina = (x, y) => ({ x: (x - geo.esquerda) / geo.dpr, y: (y - geo.topo) / geo.dpr });

function mouse(event_type, x, y) {
  const a = alvo();
  if (!a) return;
  const p = naPagina(x, y);
  fila = fila.then(() => websocket.emit("browser_viewer_input", { ...a, input_type: "mouse", event_type, x: p.x, y: p.y, button: "left" })).catch(() => {});
}

let rolagem = { dx: 0, dy: 0, x: 0, y: 0, timer: null };
function rolar(x, y, dx, dy) {
  rolagem.dx += dx; rolagem.dy += dy; rolagem.x = x; rolagem.y = y;
  if (rolagem.timer) return;
  rolagem.timer = setTimeout(() => {
    const { dx: ddx, dy: ddy, x: rx, y: ry } = rolagem;
    rolagem = { dx: 0, dy: 0, x: 0, y: 0, timer: null };
    const a = alvo();
    if (!a || (!ddx && !ddy)) return;
    const p = naPagina(rx, ry);
    fila = fila.then(() => websocket.emit("browser_viewer_input", { ...a, input_type: "wheel", x: p.x, y: p.y, delta_x: ddx, delta_y: ddy })).catch(() => {});
  }, 40);
}

// Phone gestures in the Browser panel's live view, the way a phone page behaves: a tap clicks (and
// raises the keyboard on a text field), a one-finger drag scrolls the page (or moves the magnified
// view), press-and-hold then drag drags (sliders, captcha pieces), two fingers zoom (lupa.js). The
// viewer's own touch handling is skipped, since it turned every touch into a mouse press.
function ouvirToques(frame) {
  if (!TOQUE?.matches) return;
  let win;
  try { win = frame.contentWindow; if (!win?.document) return; } catch { return; }
  if (win.__nvToque) return;
  win.__nvToque = true;
  diag("ligado", { largura: innerWidth, altura: innerHeight });
  atualizarGeo();
  win.addEventListener("resize", () => setTimeout(atualizarGeo, 600));
  let g = null; // { x0, y0, x, y, t0, modo: "?" | "rolar" | "arrastar", timer }
  const parar = (e) => { e.preventDefault(); e.stopImmediatePropagation(); };
  const op = { capture: true, passive: false };
  for (const tipo of ["pointerdown", "pointermove", "pointerup", "pointercancel", "mousedown", "mousemove", "mouseup", "click"]) {
    win.addEventListener(tipo, (e) => { if (e.pointerType === "touch" || (g && !e.pointerType)) e.stopImmediatePropagation(); }, true);
  }
  win.addEventListener("touchstart", (e) => {
    if (e.touches.length !== 1) { if (g?.timer) clearTimeout(g.timer); g = null; return; } // two fingers: lupa.js
    parar(e);
    const t = e.touches[0];
    g = { x0: t.clientX, y0: t.clientY, x: t.clientX, y: t.clientY, t0: Date.now(), modo: "?" };
    g.timer = setTimeout(() => {
      if (g && g.modo === "?") {
        g.modo = "arrastar";
        navigator.vibrate?.(15);
        mouse("move", g.x0, g.y0);
        mouse("down", g.x0, g.y0);
      }
    }, 450);
  }, op);
  win.addEventListener("touchmove", (e) => {
    if (!g || e.touches.length !== 1) return;
    parar(e);
    const t = e.touches[0];
    const dx = t.clientX - g.x, dy = t.clientY - g.y;
    if (g.modo === "?" && Math.hypot(t.clientX - g.x0, t.clientY - g.y0) > 8) { g.modo = "rolar"; clearTimeout(g.timer); }
    if (g.modo === "rolar") {
      if (globalThis.nvLupa?.ampliado(frame)) {
        const s = globalThis.nvLupa.escala(frame);
        globalThis.nvLupa.mover(frame, dx * s, dy * s);
      } else {
        rolar(g.x0, g.y0, -dx, -dy);
      }
    } else if (g.modo === "arrastar") {
      mouse("move", t.clientX, t.clientY);
    }
    g.x = t.clientX; g.y = t.clientY;
  }, op);
  const fim = (e) => {
    if (!g) return;
    parar(e);
    clearTimeout(g.timer);
    const modo = g.modo, x = g.x, y = g.y;
    g = null;
    if (modo === "arrastar") { mouse("up", x, y); return; }
    if (modo !== "?") return;
    mouse("click", x, y);
    depoisDoToque(x, y);
  };
  win.addEventListener("touchend", fim, op);
  win.addEventListener("touchcancel", (e) => { if (g?.timer) clearTimeout(g.timer); if (g?.modo === "arrastar") mouse("up", g.x, g.y); g = null; }, op);
}

function botao(icone, titulo, onClick, classe = "") {
  const b = document.createElement("button");
  b.type = "button";
  b.className = `btn btn-icon-action surface-control ${classe}`.trim();
  b.title = titulo;
  b.setAttribute("aria-label", titulo);
  b.innerHTML = `<x-icon name="${icone}"></x-icon>`;
  b.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); onClick(); });
  return b;
}

function montar(panel) {
  if (panel.__nvMontado) return;
  const toolbar = panel.querySelector(".browser-toolbar");
  const stage = panel.querySelector(".browser-stage");
  if (!toolbar || !stage) return;
  panel.__nvMontado = true;

  const grupo = document.createElement("div");
  grupo.className = "nv-grupo";
  const pct = document.createElement("span");
  pct.className = "nv-pct";
  grupo.append(
    botao("zoom_out", "Página menor (mostra mais da página)", () => mudarZoom(+1)),
    pct,
    botao("zoom_in", "Página maior", () => mudarZoom(-1)),
    botao("edit", "Digitar com o teclado do aparelho", () => {
      const ativo = panel.classList.toggle("nv-digitando");
      if (ativo) campo.focus();
    }, "nv-digitar"),
    botao("keyboard", "Mostrar/esconder o teclado do visualizador", alternarTeclado, "nv-teclado"),
  );
  const nav = toolbar.querySelector(".browser-navigation");
  (nav || toolbar).appendChild(grupo);

  const barra = document.createElement("form");
  barra.className = "nv-barra";
  const campo = document.createElement("input");
  campo.type = "text";
  campo.placeholder = "Digite aqui e toque em Enviar";
  campo.autocomplete = "off";
  campo.setAttribute("autocapitalize", "off");
  const mandar = document.createElement("button");
  mandar.type = "submit";
  mandar.className = "btn btn-ok";
  mandar.textContent = "Enviar";
  const tecla = (rotulo, key) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn btn-field";
    b.textContent = rotulo;
    b.addEventListener("click", () => enviar({ key }));
    return b;
  };
  barra.append(campo, mandar, tecla("⏎", "Enter"), tecla("⌫", "Backspace"), tecla("Tab", "Tab"));
  barra.addEventListener("submit", async (e) => {
    e.preventDefault();
    const texto = campo.value;
    if (!texto) return;
    campo.value = "";
    await enviar({ text: texto });
  });
  for (const ev of ["keydown", "keyup", "keypress"]) barra.addEventListener(ev, (e) => e.stopPropagation());
  stage.insertAdjacentElement("afterend", barra);

  aplicarZoomNoPainel();
  aplicarTecladoNoFrame();
}

function envolver() {
  if (browser.__nvEnvolvido) return;
  browser.__nvEnvolvido = true;

  const medir = browser.surfaceViewportMeasurement;
  browser.surfaceViewportMeasurement = function (...args) {
    const m = medir.apply(this, args);
    if (!m) return m;
    const f = fator(m.rawWidth);
    aplicarZoomNoPainel();
    if (f === 1) return m;
    return { ...m, width: Math.round(m.rawWidth * f), height: Math.round(m.rawHeight * f) };
  };

  const preparar = browser.prepareInteractiveViewFrame;
  browser.prepareInteractiveViewFrame = function (...args) {
    const r = preparar.apply(this, args);
    aplicarTecladoNoFrame();
    return r;
  };

  const aplicar = browser.applyViewer;
  browser.applyViewer = function (...args) {
    const r = aplicar.apply(this, args);
    const url = this.interactiveViewUrl;
    if (url && !/[?&]keyboard=/.test(url)) {
      this.interactiveViewUrl = url + (url.includes("?") ? "&" : "?") + "keyboard=false";
    }
    return r;
  };
}

export default async function navegadorVisual() {
  if (!document.getElementById(CSS_ID)) {
    const style = document.createElement("style");
    style.id = CSS_ID;
    style.textContent = CSS;
    document.head.appendChild(style);
  }
  envolver();
  let agendado = false;
  const varrer = () => {
    agendado = false;
    for (const panel of document.querySelectorAll(".browser-panel")) montar(panel);
    for (const frame of document.querySelectorAll(".browser-interactive-frame")) ouvirToques(frame);
    for (const modal of document.querySelectorAll(".modal-inner.office-modal")) montarComputador(modal);
    aplicarZoomNoPainel();
    aplicarTecladoNoFrame();
  };
  new MutationObserver(() => {
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(varrer);
  }).observe(document.body, { childList: true, subtree: true });
  varrer();
}

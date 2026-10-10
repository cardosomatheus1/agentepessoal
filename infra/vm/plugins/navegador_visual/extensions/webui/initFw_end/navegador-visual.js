// Browser, Computer and Phone panels that work on a phone and on a PC: full screen on narrow screens,
// the xpra on-screen keyboard (Browser and Computer) hidden until asked for, and in the Browser zoom
// out/in (bigger remote screen drawn smaller) plus a bar that types with the device's own keyboard.
import { store as browser } from "/plugins/_browser/webui/browser-store.js";
import { getNamespacedClient } from "/js/websocket.js";

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
      frame.addEventListener("load", () => setTimeout(aplicarTecladoNoFrame, 300));
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

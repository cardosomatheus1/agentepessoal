// Finger zoom: the phone's own pinch zoom is turned back on for the whole page, and inside the Browser,
// Computer and Phone panels a magnifier takes two fingers (or Ctrl + mouse wheel) to zoom in on the
// remote screen and move around; the "100%" chip goes back. Browser and Computer are xpra
// pages on our own origin, so the gesture is read inside them and a one-finger tap still clicks. The
// Phone screen comes from another origin: its "Zoom" button lays a layer over it that takes the
// gestures until it is turned off.
const FRAMES = ".browser-interactive-frame, .office-desktop-frame, .celular-frame";
const MAX = 6;

const CSS = `
  .browser-stage .browser-interactive-frame {
    transform: translate(var(--nv-tx, 0px), var(--nv-ty, 0px)) scale(calc(var(--nv-vz, 1) / var(--nv-zoom, 1))) !important;
    clip-path: var(--nv-clip, none);
  }
  .office-desktop-frame, .celular-frame {
    transform-origin: 0 0;
    transform: translate(var(--nv-tx, 0px), var(--nv-ty, 0px)) scale(var(--nv-vz, 1));
    clip-path: var(--nv-clip, none);
  }
  .nv-lupa-chip { position: absolute; z-index: 30; right: 10px; bottom: 10px; display: none; align-items: center; gap: 2px;
    background: rgba(20, 20, 24, .88); color: #fff; border: 1px solid rgba(255, 255, 255, .18); border-radius: 999px;
    padding: 3px; font: 600 13px/1 system-ui, sans-serif; box-shadow: 0 4px 16px rgba(0, 0, 0, .4); }
  .nv-lupa-chip.visivel { display: inline-flex; }
  .nv-lupa-chip button { all: unset; cursor: pointer; padding: 7px 10px; border-radius: 999px; }
  .nv-lupa-chip button:hover { background: rgba(255, 255, 255, .12); }
  .nv-lupa-chip .nv-lupa-pct { min-width: 44px; text-align: center; font-variant-numeric: tabular-nums; }
  .nv-lupa-camada { position: absolute; z-index: 20; display: none; touch-action: none; cursor: grab;
    outline: 2px dashed rgba(108, 140, 255, .7); outline-offset: -2px; }
  .celular-panel.nv-lupa-ativa .nv-lupa-camada { display: block; }
  .celular-panel { position: relative; overflow: hidden; }
  .celular-toolbar button.nv-lupa-botao.is-active { color: #fff !important; background: #4f6bff !important; border-color: #4f6bff !important; }
`;

const limitar = (v, a, b) => Math.min(b, Math.max(a, v));

// Base scale: how big the frame's own pixels are drawn before the magnifier (the Browser draws a
// larger remote screen smaller; the others are 1:1).
function escalaBase(frame) {
  if (!frame.classList.contains("browser-interactive-frame")) return 1;
  const z = parseFloat(getComputedStyle(frame).getPropertyValue("--nv-zoom")) || 1;
  return 1 / z;
}

function estado(frame) {
  if (!frame.__nvLupa) frame.__nvLupa = { vz: 1, tx: 0, ty: 0 };
  return frame.__nvLupa;
}

function caixa(frame) {
  const b = escalaBase(frame);
  return { w: frame.offsetWidth * b, h: frame.offsetHeight * b, b };
}

function aplicar(frame) {
  const e = estado(frame);
  const { w, h, b } = caixa(frame);
  e.vz = limitar(e.vz, 1, MAX);
  e.tx = limitar(e.tx, w * (1 - e.vz), 0);
  e.ty = limitar(e.ty, h * (1 - e.vz), 0);
  frame.style.setProperty("--nv-vz", e.vz.toFixed(4));
  frame.style.setProperty("--nv-tx", `${e.tx.toFixed(1)}px`);
  frame.style.setProperty("--nv-ty", `${e.ty.toFixed(1)}px`);
  if (e.vz > 1.001) {
    // keep the enlarged screen inside its own box (clip-path is in the frame's untransformed pixels)
    const s = b * e.vz;
    const lw = frame.offsetWidth, lh = frame.offsetHeight;
    const l = -e.tx / s, t = -e.ty / s, r = lw - (w - e.tx) / s, bo = lh - (h - e.ty) / s;
    frame.style.setProperty("--nv-clip", `inset(${t.toFixed(1)}px ${r.toFixed(1)}px ${bo.toFixed(1)}px ${l.toFixed(1)}px)`);
  } else {
    frame.style.removeProperty("--nv-clip");
  }
  const chip = frame.__nvChip;
  if (chip) {
    chip.classList.toggle("visivel", e.vz > 1.001 || chip.__sempre);
    chip.querySelector(".nv-lupa-pct").textContent = `${Math.round(e.vz * 100)}%`;
  }
}

// Zoom by `fator` keeping the point (x, y) — in box pixels — under the finger/cursor.
function zoomEm(frame, fator, x, y) {
  const e = estado(frame);
  const u = (x - e.tx) / e.vz, v = (y - e.ty) / e.vz;
  e.vz = limitar(e.vz * fator, 1, MAX);
  e.tx = x - u * e.vz;
  e.ty = y - v * e.vz;
  aplicar(frame);
}

function zoomNoCentro(frame, fator) {
  const { w, h } = caixa(frame);
  zoomEm(frame, fator, w / 2, h / 2);
}

function voltar(frame) {
  Object.assign(estado(frame), { vz: 1, tx: 0, ty: 0 });
  aplicar(frame);
}

// Pinch/pan from a list of points already in box pixels.
function gesto(frame) {
  let ini = null;
  return {
    comecar(p) {
      const e = estado(frame);
      const m = { x: (p[0].x + p[1].x) / 2, y: (p[0].y + p[1].y) / 2 };
      ini = { d: Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) || 1, m, vz: e.vz, u: (m.x - e.tx) / e.vz, v: (m.y - e.ty) / e.vz };
    },
    mover(p) {
      if (!ini) return this.comecar(p);
      const e = estado(frame);
      const d = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) || 1;
      const m = { x: (p[0].x + p[1].x) / 2, y: (p[0].y + p[1].y) / 2 };
      e.vz = limitar(ini.vz * d / ini.d, 1, MAX);
      e.tx = m.x - ini.u * e.vz;
      e.ty = m.y - ini.v * e.vz;
      aplicar(frame);
    },
    arrastar(dx, dy) {
      const e = estado(frame);
      e.tx += dx; e.ty += dy;
      aplicar(frame);
    },
    fim() { ini = null; },
  };
}

// Browser and Computer: listen inside the xpra page (same origin). Only two-finger moves and
// Ctrl+wheel are taken; one finger still clicks and drags, and touchend still reaches xpra.
function ligarNoFrame(frame) {
  let win;
  try { win = frame.contentWindow; if (!win?.document) return; } catch { return; }
  if (win.__nvLupa) return;
  win.__nvLupa = true;
  const g = gesto(frame);
  const pontos = (ev) => {
    const e = estado(frame), s = escalaBase(frame) * e.vz;
    return [...ev.touches].slice(0, 2).map((t) => ({ x: e.tx + t.clientX * s, y: e.ty + t.clientY * s }));
  };
  const op = { capture: true, passive: false };
  win.addEventListener("touchstart", (ev) => {
    if (ev.touches.length < 2) return;
    ev.preventDefault(); ev.stopImmediatePropagation();
    g.comecar(pontos(ev));
  }, op);
  win.addEventListener("touchmove", (ev) => {
    if (ev.touches.length < 2) return;
    ev.preventDefault(); ev.stopImmediatePropagation();
    g.mover(pontos(ev));
  }, op);
  win.addEventListener("touchend", (ev) => { if (ev.touches.length < 2) g.fim(); }, { capture: true });
  win.addEventListener("touchcancel", () => g.fim(), { capture: true });
  win.addEventListener("wheel", (ev) => {
    if (!ev.ctrlKey) return;
    ev.preventDefault(); ev.stopImmediatePropagation();
    const e = estado(frame), s = escalaBase(frame) * e.vz;
    zoomEm(frame, Math.exp(-ev.deltaY * 0.0025), e.tx + ev.clientX * s, e.ty + ev.clientY * s);
  }, op);
}

// Phone: a layer over the frame that takes the gestures while "Zoom" is on (one finger moves).
function camadaCelular(frame) {
  const panel = frame.closest(".celular-panel");
  if (!panel || panel.__nvLupa) return;
  panel.__nvLupa = true;
  const camada = document.createElement("div");
  camada.className = "nv-lupa-camada";
  panel.appendChild(camada);
  const posicionar = () => {
    const f = panel.querySelector(".celular-frame");
    if (!f) return;
    Object.assign(camada.style, { left: `${f.offsetLeft}px`, top: `${f.offsetTop}px`, width: `${f.offsetWidth}px`, height: `${f.offsetHeight}px` });
    // the panel runs below the modal's visible edge on a phone: pin the chip to the frame's top corner
    const c = f.__nvChip;
    if (c) Object.assign(c.style, { right: "auto", bottom: "auto", left: `${f.offsetLeft + f.offsetWidth - 10}px`,
      top: `${f.offsetTop + 10}px`, transform: "translateX(-100%)" });
  };
  new ResizeObserver(posicionar).observe(panel);
  posicionar();
  const atual = () => panel.querySelector(".celular-frame");
  const g = { ref: null, de: null };
  const ativos = new Map();
  const local = (ev) => { const r = camada.getBoundingClientRect(); return { x: ev.clientX - r.left, y: ev.clientY - r.top }; };
  camada.addEventListener("pointerdown", (ev) => {
    const f = atual(); if (!f) return;
    camada.setPointerCapture(ev.pointerId);
    ativos.set(ev.pointerId, local(ev));
    if (!g.ref || g.ref.f !== f) g.ref = Object.assign(gesto(f), { f });
    if (ativos.size === 2) g.ref.comecar([...ativos.values()]);
    g.de = local(ev);
  });
  camada.addEventListener("pointermove", (ev) => {
    if (!ativos.has(ev.pointerId) || !g.ref) return;
    const p = local(ev);
    ativos.set(ev.pointerId, p);
    if (ativos.size >= 2) g.ref.mover([...ativos.values()].slice(0, 2));
    else if (g.de) { g.ref.arrastar(p.x - g.de.x, p.y - g.de.y); g.de = p; }
  });
  const soltar = (ev) => { ativos.delete(ev.pointerId); g.ref?.fim(); g.de = ativos.size === 1 ? [...ativos.values()][0] : null; };
  camada.addEventListener("pointerup", soltar);
  camada.addEventListener("pointercancel", soltar);
  camada.addEventListener("wheel", (ev) => {
    const f = atual(); if (!f) return;
    ev.preventDefault();
    const p = local(ev);
    zoomEm(f, Math.exp(-ev.deltaY * 0.0025), p.x, p.y);
  }, { passive: false });

  const barra = panel.querySelector(".celular-toolbar");
  if (barra) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "nv-lupa-botao";
    b.textContent = "🔍 Zoom";
    b.title = "Ligado: dois dedos ampliam, um dedo move a tela. Desligue para tocar no celular.";
    b.addEventListener("click", () => {
      const on = panel.classList.toggle("nv-lupa-ativa");
      b.classList.toggle("is-active", on);
      const f = atual();
      posicionar();
      if (f?.__nvChip) { f.__nvChip.__sempre = on; aplicar(f); }
    });
    barra.appendChild(b);
  }
}

function chip(frame) {
  if (frame.__nvChip?.isConnected) return;
  const host = frame.parentElement;
  if (!host) return;
  if (getComputedStyle(host).position === "static") host.style.position = "relative";
  const c = document.createElement("div");
  c.className = "nv-lupa-chip";
  c.innerHTML = '<button type="button" data-a="-">−</button><span class="nv-lupa-pct">100%</span>'
    + '<button type="button" data-a="+">+</button><button type="button" data-a="0" title="Voltar ao tamanho normal">⟲</button>';
  c.addEventListener("click", (ev) => {
    const a = ev.target.closest("button")?.dataset.a;
    if (a === "+") zoomNoCentro(frame, 1.4);
    else if (a === "-") zoomNoCentro(frame, 1 / 1.4);
    else if (a === "0") voltar(frame);
  });
  for (const t of ["pointerdown", "touchstart", "wheel"]) c.addEventListener(t, (ev) => ev.stopPropagation());
  host.appendChild(c);
  frame.__nvChip = c;
}

// The UI ships with maximum-scale=1, which turns off the phone's own pinch zoom everywhere.
function liberarZoomDaPagina() {
  const meta = document.querySelector('meta[name="viewport"]');
  const conteudo = "width=device-width, initial-scale=1, maximum-scale=5, user-scalable=yes";
  if (meta && meta.content !== conteudo) meta.content = conteudo;
}

export default async function lupaPaineis() {
  liberarZoomDaPagina();
  if (!document.getElementById("a0-nv-lupa-css")) {
    const s = document.createElement("style");
    s.id = "a0-nv-lupa-css";
    s.textContent = CSS;
    document.head.appendChild(s);
  }
  let agendado = false;
  const varrer = () => {
    agendado = false;
    for (const frame of document.querySelectorAll(FRAMES)) {
      chip(frame);
      if (frame.classList.contains("celular-frame")) camadaCelular(frame);
      else {
        ligarNoFrame(frame);
        if (!frame.__nvLupaLoad) {
          frame.__nvLupaLoad = true;
          frame.addEventListener("load", () => setTimeout(() => ligarNoFrame(frame), 300));
        }
      }
      aplicar(frame);
    }
  };
  new MutationObserver(() => {
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(varrer);
  }).observe(document.body, { childList: true, subtree: true });
  globalThis.addEventListener("resize", () => requestAnimationFrame(varrer));
  varrer();
}

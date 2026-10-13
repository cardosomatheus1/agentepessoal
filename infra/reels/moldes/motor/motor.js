// Shared engine of every template (molde). A template only builds its scenes from the ficha and animates them; the
// engine applies the brand (marca) and style (estilo), draws background, watermark and final scene, keeps the
// timeline, fits text, and measures the checks render.py runs. Text from the ficha goes in with textContent only.
(() => {
const W = 1080;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const cl = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const p = (t, a, d) => cl((t - a) / d);
const eo = x => 1 - Math.pow(1 - x, 3);
const eo5 = x => 1 - Math.pow(1 - x, 5);
const eio = x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
const eb = x => { const c = 1.70158, c3 = c + 1; return 1 + c3 * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
const el = x => x === 0 ? 0 : x === 1 ? 1 : Math.pow(2, -10 * x) * Math.sin((x * 10 - .75) * 2 * Math.PI / 3) + 1;
const lerp = (a, b, x) => a + (b - a) * x;
const rnd = i => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
const brl = (v, casas = 2) => (v < 0 ? '-' : '') + 'R$ ' + Math.abs(v).toFixed(casas).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, '.');
const num = (v, casas = 0) => v.toFixed(casas).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, '.');

// ---------- colors ----------
const rgb = c => { c = c.replace('#', ''); if (c.length === 3) c = [...c].map(x => x + x).join(''); return [0, 2, 4].map(i => parseInt(c.slice(i, i + 2), 16)); };
const hex = a => '#' + a.map(x => Math.round(cl(x, 0, 255)).toString(16).padStart(2, '0')).join('');
const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }); return .2126 * r + .7152 * g + .0722 * b; };
const contraste = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
const mix = (a, b, t) => { const x = rgb(a), y = rgb(b); return hex(x.map((v, i) => lerp(v, y[i], t))); };
// move a color toward black or white until it reaches the contrast target against the background
function contrastar(cor, fundo, alvo) {
  if (contraste(cor, fundo) >= alvo) return cor;
  const ir = lum(fundo) > .35 ? '#000000' : '#ffffff';
  for (let k = .05; k <= 1; k += .05) { const c = mix(cor, ir, k); if (contraste(c, fundo) >= alvo) return c; }
  return ir;
}
const sobre = c => contraste('#ffffff', c) >= contraste('#111114', c) ? '#ffffff' : '#111114';

function tokens(M, estilo) {
  const c1 = (M.cores && M.cores[0]) || '#47b346';
  const c2 = (M.cores && M.cores[1]) || mix(c1, '#ffffff', .45);
  let T;
  if (estilo === 'claro') {
    const f = mix('#f7f5f1', c1, .05);
    T = { fundo: f, fundo2: mix('#ffffff', c1, .12), texto: '#17151a', texto2: '#57525e', cartao: '#ffffff', borda: 'rgba(0,0,0,.08)', sombra: '0 24px 60px rgba(30,20,40,.13)' };
  } else if (estilo === 'pop') {
    const f = c1, tx = sobre(f);
    T = { fundo: f, fundo2: mix(f, tx === '#ffffff' ? '#000000' : '#ffffff', .22), texto: tx, texto2: tx === '#ffffff' ? 'rgba(255,255,255,.82)' : 'rgba(17,17,20,.75)', borda: tx, sombra: 'none' };
    T.cartao = T.fundo2;
  } else if (estilo === 'papel') {
    T = { fundo: '#f2e8d5', fundo2: '#e7d8bd', texto: '#2a2018', texto2: '#6b5a48', cartao: '#fffaf0', borda: 'rgba(60,40,20,.16)', sombra: '0 14px 30px rgba(60,40,20,.22)' };
  } else if (estilo === 'noite') {
    T = { fundo: '#06060a', fundo2: mix('#06060a', c1, .22), texto: '#ffffff', texto2: 'rgba(255,255,255,.72)', cartao: 'rgba(255,255,255,.05)', borda: 'rgba(255,255,255,.18)', sombra: 'none' };
  } else {
    const f = mix('#0b0b10', c1, .14);
    T = { fundo: f, fundo2: mix('#0b0b10', c1, .32), texto: '#ffffff', texto2: 'rgba(255,255,255,.74)', cartao: 'rgba(255,255,255,.1)', borda: 'rgba(255,255,255,.2)', sombra: '0 30px 80px rgba(0,0,0,.45)' };
  }
  const base = estilo === 'pop' ? T.fundo : T.fundo;
  T.c1 = c1; T.c2 = estilo === 'pop' ? contrastar(c2, base, 1.6) : c2;
  T.destaque = estilo === 'pop' ? contrastar(c2, base, 3) : contrastar(c1, base, estilo === 'noite' ? 4.5 : 3.2);
  T['sobre-destaque'] = sobre(T.destaque);
  T.bom = contrastar('#2fbf5b', base, 3); T.ruim = contrastar('#ff4d4d', base, 3);
  T['sobre-bom'] = sobre(T.bom); T['sobre-ruim'] = sobre(T.ruim);
  return T;
}

// ---------- icons (own simple strokes; no emoji font in the renderer) ----------
const P = {
  check: '<path d="M4 12.5l5 5L20 6.5"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>',
  estrela: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z" fill="currentColor"/>',
  relogio: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>', calendario: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  local: '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0114 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
  telefone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2z"/>',
  chat: '<path d="M4 5h16v11H9l-5 4z"/>', carrinho: '<circle cx="9" cy="20" r="1.5"/><circle cx="17" cy="20" r="1.5"/><path d="M3 4h2.5l2.2 11h10.6L20 7.5H6.4"/>',
  moto: '<circle cx="6" cy="17" r="3"/><circle cx="18" cy="17" r="3"/><path d="M6 17l4-7h5l3 7M14 6h3l1 4"/>',
  cartao: '<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10.5h18M7 15h4"/>', dinheiro: '<rect x="3" y="6.5" width="18" height="11" rx="2"/><circle cx="12" cy="12" r="2.6"/>',
  presente: '<rect x="4" y="9" width="16" height="11" rx="1.5"/><path d="M3 9h18v-2.5H3zM12 6.5V20M12 6.5C10 3 7 4 8 6.5M12 6.5c2-3.5 5-2.5 4 0"/>',
  coracao: '<path d="M12 20s-8-5-8-11a4.5 4.5 0 018-2.8A4.5 4.5 0 0120 9c0 6-8 11-8 11z" fill="currentColor"/>',
  fogo: '<path d="M12 21c-4 0-6.5-2.8-6.5-6.2 0-3.4 2.6-5.3 3.8-8.8 1.4 2.3 2.4 3 3.4 3.2.3-1.7.1-3.4-.7-5.2 4 2 6.5 6 6.5 10.6 0 3.6-2.6 6.4-6.5 6.4z"/>',
  etiqueta: '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1.4"/>', caixa: '<path d="M3 7.5L12 3l9 4.5v9L12 21l-9-4.5z"/><path d="M3 7.5L12 12l9-4.5M12 12v9"/>',
  camera: '<rect x="3" y="7" width="18" height="13" rx="2"/><circle cx="12" cy="13.5" r="3.6"/><path d="M8.5 7l1.5-3h4l1.5 3"/>',
  tesoura: '<circle cx="6" cy="7" r="2.6"/><circle cx="6" cy="17" r="2.6"/><path d="M8.2 8.4L20 18M8.2 15.6L20 6"/>',
  chave: '<path d="M14.5 4.5a5 5 0 00-6.3 6.3L3 16v4h4l5.2-5.2a5 5 0 006.3-6.3l-3 3-3-3z"/>',
  bolo: '<path d="M4 20h16v-7H4zM4 15.5c2.6 1.6 5.4 1.6 8 0s5.4-1.6 8 0M12 13V9M12 6.5v.01"/>', xicara: '<path d="M4 9h13v5a6 6 0 01-6 6h-1a6 6 0 01-6-6zM17 10.5h1.5a2.5 2.5 0 010 5H17M8 3v3M12 3v3"/>',
  pata: '<circle cx="7" cy="9" r="1.8"/><circle cx="12" cy="6.5" r="1.8"/><circle cx="17" cy="9" r="1.8"/><path d="M8 16.5c0-2.6 1.8-4.5 4-4.5s4 1.9 4 4.5c0 2-1.8 3-4 3s-4-1-4-3z"/>',
  casa: '<path d="M3.5 11L12 4l8.5 7M6 9.5V20h12V9.5M10 20v-5h4v5"/>', pessoa: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c1-4 4-6 7.5-6s6.5 2 7.5 6"/>',
  pessoas: '<circle cx="9" cy="8.5" r="3.4"/><path d="M2.5 20c.8-3.6 3.3-5.4 6.5-5.4s5.7 1.8 6.5 5.4"/><circle cx="17" cy="9" r="2.8"/><path d="M17 14.6c2.3.3 4 1.9 4.6 4.9"/>',
  megafone: '<path d="M3 10v4h3l9 5V5L6 10zM18 9.5a3.5 3.5 0 010 5M6 14l1.5 5h3L9 14.7"/>', brilho: '<path d="M12 3l1.8 5.4L19 10l-5.2 1.6L12 17l-1.8-5.4L5 10l5.2-1.6zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/>',
  seta: '<path d="M4 12h15M13 6l6 6-6 6"/>', info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.01"/>', alerta: '<path d="M12 3.5L2.5 20h19zM12 10v4.5M12 17.5v.01"/>',
  cadeado: '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 018 0v3"/>', folha: '<path d="M5 19C5 10 10 5 20 4c0 10-5 15-14 15zM5 19l7-7"/>',
  link: '<path d="M10 14a4.5 4.5 0 006.4 0l3-3a4.5 4.5 0 00-6.4-6.4l-1 1M14 10a4.5 4.5 0 00-6.4 0l-3 3a4.5 4.5 0 006.4 6.4l1-1"/>',
  grafico: '<path d="M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6"/>', percentual: '<path d="M19 5L5 19"/><circle cx="7" cy="7" r="2.4"/><circle cx="17" cy="17" r="2.4"/>',
  trofeu: '<path d="M8 4h8v5a4 4 0 01-8 0zM8 6H4.5a3 3 0 003.5 4M16 6h3.5a3 3 0 01-3.5 4M12 13v4M8.5 20.5h7M10 17h4v3.5h-4z"/>',
  balao: '<path d="M12 4c4.4 0 8 2.8 8 6.4s-3.6 6.4-8 6.4c-.9 0-1.8-.1-2.6-.3L5 18.5l1.1-3.4C4.8 13.9 4 12.2 4 10.4 4 6.8 7.6 4 12 4z"/>',
  lupa: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5.5 5.5"/>', mais: '<path d="M12 5v14M5 12h14"/>', menos: '<path d="M5 12h14"/>',
  carro: '<path d="M4 16v-4l2-5h12l2 5v4zM4 16v2.5h3V16M17 16v2.5h3V16M4 12h16"/><circle cx="7.5" cy="13.8" r=".6"/><circle cx="16.5" cy="13.8" r=".6"/>',
  haltere: '<path d="M3 9.5v5M6 7.5v9M18 7.5v9M21 9.5v5M6 12h12"/>', dente: '<path d="M7 4c-2.5 0-3.5 2.4-3 5 .5 3 1.5 4 2 7.5.3 2.3 1.3 3.5 2.2 3.5 1.4 0 1.3-3.5 2.3-5.5.5-1 1.5-1 2 0 1 2 .9 5.5 2.3 5.5.9 0 1.9-1.2 2.2-3.5.5-3.5 1.5-4.5 2-7.5.5-2.6-.5-5-3-5-2 0-3 1-5 1S9 4 7 4z"/>',
  vestido: '<path d="M9 3l-1 4 2 2-4 12h12L14 9l2-2-1-4"/>', garfo: '<path d="M7 3v7a2 2 0 004 0V3M9 10v11M16 3c-2 1.5-2.5 4.5-2.5 7h2.5v11"/>',
};
const icone = (nome, extra = '') => `<span class="ico ${extra}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${P[nome] || P.info}</svg></span>`;

// ---------- engine ----------
// safe area per format; in a Reel the like/comment/share buttons cover the right strip only from y=900 down
const SEGURO = { reel: { x0: 60, x1: 1020, y0: 240, y1: 1500, fora: [{ x0: 920, y0: 900, x1: 1080, y1: 1920 }] },
  story: { x0: 60, x1: 1020, y0: 250, y1: 1580, fora: [] }, carrossel: { x0: 74, x1: 1006, y0: 56, y1: 1294, fora: [] } };
const MIN_FONTE = { reel: 30, story: 30, carrossel: 26 };
const TRANS = { vidro: 'circulo', claro: 'fade', pop: 'corte', papel: 'deslize', noite: 'fade' };

const Motor = {
  $, $$, cl, p, eo, eo5, eio, eb, el, lerp, rnd, brl, num, icone, contraste, mix, sobre,
  F: null, M: null, FORMATO: 'reel', ESTILO: 'vidro', W, H: 1920, S: [0], N: 0, DUR: 0, erros: [], avisos: [], def: null,
  _espera: [], _slides: [],

  molde(def) { Motor.def = def; if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', Motor._iniciar); else Motor._iniciar(); },
  erro(msg) { Motor.erros.push(msg); },
  midia(caminho) { if (!caminho) return ''; if (/^(https?:|file:|data:|\/)/.test(caminho)) return caminho; return (window.MIDIA || '../midia/') + caminho; },
  logoSrc(caminho) { if (!caminho) return ''; if (/^(https?:|file:|data:|\/)/.test(caminho)) return caminho; return (window.MARCA_BASE || '') + caminho; },

  async _iniciar() {
    try {
      const F = Motor.F = window.FICHA || {};
      const M = Motor.M = window.MARCA || { nome: 'Sua Marca', cores: ['#47b346'] };
      const def = Motor.def;
      Motor.FORMATO = window.FORMATO || F._formato || (def.formatos || ['reel'])[0];
      Motor.ESTILO = F._estilo || M.estilo || 'vidro';
      Motor.H = Motor.FORMATO === 'carrossel' ? 1350 : 1920;
      document.body.classList.add('f-' + Motor.FORMATO, 'e-' + Motor.ESTILO);
      Motor.T = tokens(M, Motor.ESTILO);
      const r = document.documentElement.style;
      for (const [k, v] of Object.entries(Motor.T)) r.setProperty('--' + k, v);
      r.setProperty('--ft', { bricolage: 'B', anton: 'A', inter: 'D' }[M.fonte] || 'D');
      Motor._conferirCores();
      const palco = $('#palco');
      palco.insertAdjacentHTML('afterbegin', '<div id="fundo"></div>');
      Motor._fundo();
      if (!def.semGrao) palco.insertAdjacentHTML('beforeend', '<div id="vinheta"></div><div id="grao"></div>');
      palco.insertAdjacentHTML('beforeend', '<div id="area"></div>');
      if (Motor.FORMATO === 'carrossel') {
        if (!def.slides) throw new Error('este molde não faz carrossel');
        def.slides(F, M, Motor);
        if (def.slideFinal !== false) Motor._slideFinal();
        Motor._slides = $$('.slide', palco);
        for (let i = 0; i < Motor._slides.length; i++) if (!Motor._slides[i].classList.contains('slide-final')) Motor._marca(Motor._slides[i]);
        Motor.slide(0);
      } else {
        if (!def.montar) throw new Error('este molde não faz vídeo');
        const r2 = def.montar(F, M, Motor) || {};
        Motor._marca(palco);
        Motor._linha(r2.duracoes);
        if (def.final !== false) Motor._final(palco);
      }
      await document.fonts.ready;
      await Promise.all($$('img').map(i => i.complete ? (i.decode ? i.decode().catch(() => {}) : 0) : new Promise(ok => { i.onload = i.onerror = ok; })));
      $$('.rv').forEach(Motor.palavras);
      Motor._caberTudo();
      if (Motor.FORMATO !== 'carrossel') await window.render(0);
      window.MOTOR_PRONTO = true;
    } catch (e) { Motor.erros.push('erro no molde: ' + (e && e.stack || e)); window.MOTOR_PRONTO = true; }
  },

  _conferirCores() {
    const T = Motor.T;
    if (contraste(T.texto, T.fundo) < 4.5) Motor.avisos.push('contraste do texto baixo');
    if (contraste(T.destaque, T.fundo) < 3) Motor.avisos.push('contraste do destaque baixo');
  },

  // timeline: with narration the scenes follow the voice (TEMPOS), otherwise the template's durations
  _linha(duracoes) {
    const def = Motor.def;
    if (window.TEMPOS && window.TEMPOS.length > 1) Motor.S = window.TEMPOS.slice();
    else {
      const d = (duracoes || def.duracoes || [3]).slice();
      if (def.final !== false) d.push(def.duracaoFinal || 3);
      Motor.S = [0]; for (const x of d) Motor.S.push(+(Motor.S[Motor.S.length - 1] + x).toFixed(3));
    }
    Motor.N = Motor.S.length - 1; Motor.DUR = Motor.S[Motor.N];
  },
  ini(i) { return Motor.S[Math.max(0, Math.min(i, Motor.N))]; },
  fim(i) { return Motor.S[Math.max(0, Math.min(i + 1, Motor.N))]; },
  // shows scene element `id` during scene i (or i..j), with the style's transition; returns entry progress 0..1
  cena(sel, t, i, j = i, o = {}) {
    const e = typeof sel === 'string' ? $(sel) : sel; if (!e) return 0;
    const a = Motor.ini(i), b = Motor.fim(j);
    const trans = o.trans || TRANS[Motor.ESTILO] || 'fade', ent = o.ent ?? (trans === 'corte' ? 0.001 : 0.5);
    const on = t >= a && t < b + (o.sobra ?? 0.45);
    e.style.opacity = on ? 1 : 0; if (!on) { e.style.visibility = 'hidden'; return 0; } e.style.visibility = 'visible';
    const q = eio(p(t, a, ent));
    e.style.clipPath = 'none';
    if (trans === 'circulo') e.style.clipPath = q < 1 ? `circle(${q * 2300}px at ${o.x ?? 540}px ${o.y ?? Motor.H / 2}px)` : 'none';
    else if (trans === 'fade') e.style.opacity = q;
    else if (trans === 'deslize') e.style.transform = `translateX(${(1 - q) * 1080}px) rotate(${(1 - q) * 3}deg)`;
    else if (trans === 'corte') e.style.transform = `scale(${1 + 0.08 * (1 - eo(p(t, a, 0.35)))})`;
    const c = e.querySelector('.cam'); if (c) c.style.transform = `scale(${1 + (o.push ?? 0.05) * p(t, a, b - a + 0.5) + 0.05 * (1 - eo(p(t, a, ent + 0.3)))})`;
    return trans === 'corte' ? 1 : q;
  },

  // word-by-word reveal
  palavras(e) {
    if (e.dataset.pal) return; e.dataset.pal = 1;
    const walk = n => [...n.childNodes].forEach(c => {
      if (c.nodeType === 3) {
        const f = document.createDocumentFragment();
        c.textContent.split(/(\s+)/).forEach(w => { if (!w) return; if (/^\s+$/.test(w)) { f.appendChild(document.createTextNode(w)); return; }
          const a = document.createElement('span'); a.className = 'ww'; const b = document.createElement('span'); b.className = 'wi'; b.textContent = w; a.appendChild(b); f.appendChild(a); });
        c.replaceWith(f);
      } else if (c.nodeType === 1 && c.tagName !== 'BR') walk(c);
    });
    walk(e);
  },
  revela(e, t, t0, passo = 0.07, dur = 0.55) {
    if (typeof e === 'string') e = $(e); if (!e) return;
    if (!e.dataset.pal) Motor.palavras(e);
    $$('.wi', e).forEach((w, i) => { const q = eo5(p(t, t0 + i * passo, dur)); w.style.transform = `translateY(${(1 - q) * 115}%) rotate(${(1 - q) * 7}deg)`; });
  },
  // fade/slide in: returns progress
  entra(e, t, t0, dur = 0.5, dy = 60, escala = 0) {
    if (typeof e === 'string') e = $(e); if (!e) return 0;
    const q = eo5(p(t, t0, dur)); e.style.opacity = q; e.style.transform = `translateY(${(1 - q) * dy}px) scale(${1 - escala * (1 - q)})`; return q;
  },
  // number counting up to `valor`, formatted by fmt
  conta(e, t, t0, dur, valor, fmt = v => num(v), de = 0) {
    if (typeof e === 'string') e = $(e); if (!e) return;
    e.textContent = fmt(lerp(de, valor, eo5(p(t, t0, dur))));
  },
  // stamp hitting the screen
  carimbo(e, t, t0) {
    if (typeof e === 'string') e = $(e); if (!e) return 0;
    const q = p(t, t0, 0.35); const s = q === 0 ? 0 : 1 + 1.4 * Math.pow(1 - eo(q), 2);
    e.style.opacity = q > 0 ? 1 : 0; e.style.transform = `scale(${s}) rotate(-8deg)`; return q;
  },
  // highlight marker under a .mk word
  marcador(e, t, t0, dur = 0.45) { if (typeof e === 'string') e = $(e); if (e) e.style.setProperty('--k', eo(p(t, t0, dur))); },
  brilho(btn, t, t0) { const i = btn && btn.querySelector('i'); if (!i) return; const k = ((t - t0) % 2.2) / 2.2; i.style.left = (-20 + k * 140) + '%'; },

  // footage frames: midia/filmagem/<nome>/q0001.jpg…, ping-pong loop
  filmagem(img, nome, t, fps = 30) {
    const n = (window.FILMAGENS || {})[nome] || 0; if (!n) { Motor.erro('filmagem não encontrada: ' + nome); return; }
    const k = Math.floor(t * fps), per = 2 * (n - 1); let i = k % per; if (i >= n) i = per - i;
    const src = Motor.midia(`filmagem/${nome}/q${String(i + 1).padStart(4, '0')}.jpg`);
    if (img.getAttribute('src') !== src) { img.setAttribute('src', src); Motor._espera.push(img.decode().catch(() => {})); }
  },

  // text fitting: every .t shrinks until it fits its box (down to data-min or the format minimum)
  caber(e) {
    const min = +(e.dataset.min || MIN_FONTE[Motor.FORMATO]);
    let fs = parseFloat(getComputedStyle(e).fontSize), guard = 80;
    const sobra = () => e.scrollHeight > e.clientHeight + 2 || e.scrollWidth > e.clientWidth + 2;
    while (sobra() && fs > min && guard--) { fs = Math.max(min, fs - 2); e.style.fontSize = fs + 'px'; }
  },
  _caberTudo() {
    if (Motor.FORMATO === 'carrossel') { Motor._slides.forEach((s, i) => { Motor.slide(i); $$('.t', s).forEach(Motor.caber); }); Motor.slide(0); }
    else $$('.t').forEach(Motor.caber);
  },

  // background per style
  _fundo() {
    const f = $('#fundo'), T = Motor.T, est = Motor.ESTILO; let h = '';
    if (est === 'vidro') { f.style.background = `radial-gradient(1200px 1100px at 50% 28%, ${T.fundo2} 0%, ${T.fundo} 60%)`;
      for (let i = 0; i < 16; i++) { const s = 40 + rnd(i) * 180; h += `<div class="bok" data-i="${i}" style="width:${s}px;height:${s}px;background:${[T.c1, T.c2, '#ffffff'][i % 3]};filter:blur(${8 + rnd(i * 3) * 26}px);opacity:${.06 + rnd(i * 7) * .2}"></div>`; } }
    else if (est === 'claro') { f.style.background = `radial-gradient(900px 700px at 85% 10%, ${mix(T.fundo, T.c1, .12)} 0%, transparent 70%), radial-gradient(800px 800px at 10% 95%, ${mix(T.fundo, T.c2, .14)} 0%, transparent 70%), ${T.fundo}`; }
    else if (est === 'pop') { f.style.background = T.fundo;
      h = `<div class="forma" data-r="1" style="left:-160px;top:180px;width:520px;height:520px;border-radius:50%;background:${T.c2};opacity:.55"></div>
           <div class="forma" data-r="-1" style="right:-120px;bottom:${Motor.H * .18}px;width:420px;height:420px;border-radius:60px;background:${T.texto};opacity:.08"></div>
           <div class="forma" data-r=".5" style="right:120px;top:120px;width:160px;height:160px;border:22px solid ${T.c2};border-radius:50%;opacity:.7"></div>`; }
    else if (est === 'papel') { f.style.background = `repeating-linear-gradient(0deg, rgba(90,60,30,.035) 0 2px, transparent 2px 6px), radial-gradient(1000px 900px at 50% 40%, #f8f0e1, ${T.fundo})`;
      h = `<div class="forma" style="left:70px;top:150px;width:210px;height:58px;background:${mix(T.c1, '#ffffff', .5)};opacity:.6;transform:rotate(-6deg)"></div>`; }
    else if (est === 'noite') { f.style.background = T.fundo;
      h = `<div class="forma" style="left:-200px;top:${Motor.H * .1}px;width:900px;height:900px;border-radius:50%;background:${T.c1};filter:blur(160px);opacity:.35"></div>
           <div class="forma" style="right:-260px;bottom:${Motor.H * .05}px;width:900px;height:900px;border-radius:50%;background:${T.c2};filter:blur(170px);opacity:.25"></div>`; }
    f.innerHTML = h;
  },
  _fundoMove(t) {
    if (Motor.ESTILO === 'vidro') $$('#fundo .bok').forEach(b => { const i = +b.dataset.i; const x = rnd(i * 5) * 1180 - 50 + Math.sin(t * .3 + i) * 40, y = rnd(i * 11) * (Motor.H + 80) - 40 - t * (10 + rnd(i) * 30); b.style.transform = `translate(${x}px,${((y % (Motor.H + 180)) + Motor.H + 180) % (Motor.H + 180) - 100}px)`; });
    else if (Motor.ESTILO === 'pop') $$('#fundo .forma').forEach(f => { f.style.transform = `rotate(${t * 12 * (+f.dataset.r || 0)}deg)`; });
    const g = $('#grao'); if (g) { const i = Math.floor(t * 24); g.style.transform = `translate(${(rnd(i) * 320) | 0}px,${(rnd(i + 9) * 320) | 0}px)`; }
  },

  // logo choice: version made for this background, else the other one on a contrasting pill, else the name
  _logo(grande) {
    const M = Motor.M, escuro = lum(Motor.ESTILO === 'pop' ? Motor.T.fundo : Motor.T.fundo) < .35;
    const certo = escuro ? M.logo_escuro : M.logo_claro, outro = escuro ? M.logo_claro : M.logo_escuro;
    const d = document.createElement('div'); d.className = 'logo';
    // a photo instead of a logo (profile photo, storefront, the owner): round photo + name
    if (M.foto && (M.assinatura === 'foto' || !(M.logo_claro || M.logo_escuro))) {
      d.classList.add('com-foto'); const img = document.createElement('img'); img.className = 'avatar'; img.src = Motor.logoSrc(M.foto); img.alt = M.nome || '';
      const n = document.createElement('div'); n.className = 'nome'; n.textContent = M.nome || ''; d.append(img, n); return d;
    }
    if (certo || outro) { const img = document.createElement('img'); img.src = Motor.logoSrc(certo || outro); img.alt = M.nome || ''; d.appendChild(img);
      if (!certo) { d.classList.add('selo'); d.style.setProperty('--selo', escuro ? '#ffffff' : '#111114'); } }
    else { const n = document.createElement('div'); n.className = 'nome'; n.textContent = M.nome || ''; d.appendChild(n); }
    return d;
  },
  _marca(onde) {
    if (Motor.def.semMarca) return;
    const m = Motor._logo(false); m.id = Motor.FORMATO === 'carrossel' ? '' : 'marca';
    if (Motor.FORMATO === 'carrossel') { m.className += ' marca-slide'; Object.assign(m.style, { position: 'absolute', left: '84px', top: '64px', zIndex: 80 }); const im = m.querySelector('img:not(.avatar)'); if (im) im.style.height = '46px'; if (m.classList.contains('selo')) Object.assign(m.style, { padding: '10px 20px', borderRadius: '999px', background: m.style.getPropertyValue('--selo') }); const nm = m.querySelector('.nome'); if (nm && !m.classList.contains('com-foto')) Object.assign(nm.style, { fontFamily: 'var(--ft)', fontWeight: 900, fontSize: '30px' }); }
    else { const im = m.querySelector('img:not(.avatar)'); if (im) { im.style.height = '72px'; im.style.maxWidth = '380px'; im.style.objectFit = 'contain'; } if (m.classList.contains('selo')) Object.assign(m.style, { padding: '12px 24px', borderRadius: '999px', background: m.style.getPropertyValue('--selo') }); }
    if (Motor.FORMATO !== 'carrossel') m.id = 'marca';
    m.classList.add('seg');
    onde.appendChild(m);
  },
  // final scene: big logo, @ and call to action
  _final(onde) {
    const F = Motor.F, M = Motor.M, f = document.createElement('div'); f.className = 'final';
    const lg = Motor._logo(true); lg.classList.add('seg'); f.appendChild(lg);
    if (F.final_extra) { const x = document.createElement('div'); x.className = 'extra t seg'; x.textContent = F.final_extra; f.appendChild(x); }
    const ch = document.createElement('div'); ch.className = 'chamada'; const cht = document.createElement('span'); cht.className = 't seg'; cht.textContent = F.chamada || M.chamada || 'Link na bio'; ch.append(cht, document.createElement('i')); f.appendChild(ch);
    if (M.perfil) { const pe = document.createElement('div'); pe.className = 'perfil t seg'; pe.textContent = M.perfil; f.appendChild(pe); }
    onde.appendChild(f); Motor._fin = f;
  },
  _finalQuadro(t) {
    const f = Motor._fin; if (!f) return; const a = Motor.ini(Motor.N - 1);
    const q = eo5(p(t, a + 0.1, 0.7)); f.style.opacity = q; f.style.transform = `translateY(${(1 - q) * 80}px)`;
    const mk = $('#marca'); if (mk) mk.style.opacity = 1 - p(t, a, 0.3);
    Motor.brilho(f.querySelector('.chamada'), t, a + 0.9);
  },
  _slideFinal() {
    const s = document.createElement('div'); s.className = 'slide slide-final'; Motor._final(s); s.querySelector('.final').style.opacity = 1;
    $('#palco').appendChild(s);
  },
  slide(i) { Motor._slides.forEach((s, k) => { s.style.display = k === i ? 'block' : 'none'; }); const mk = $$('.marca-slide'); },

  // ---------- checks (render.py calls this at sample times) ----------
  _visivel(e) {
    if (!e.isConnected) return false; let o = 1, n = e;
    while (n && n !== document.body) { const cs = getComputedStyle(n); if (cs.display === 'none' || cs.visibility === 'hidden') return false; o *= +cs.opacity; n = n.parentElement; }
    return o > 0.5;
  },
  // what the eye sees: the glyphs of a text element (not its whole box), or the element itself for images
  _caixa(e) {
    if (e.querySelector('img') || e.tagName === 'IMG' || !e.textContent.trim()) return e.getBoundingClientRect();
    // revealed words: the clipping box of each word is what can show, wherever the word is in its animation
    const ws = $$('.ww', e); let rs;
    if (ws.length) rs = ws.map(w => w.getBoundingClientRect());
    else { const rg = document.createRange(); rg.selectNodeContents(e); rs = [...rg.getClientRects()]; }
    rs = rs.filter(x => x.width > 0.5 && x.height > 0.5);
    if (!rs.length) return e.getBoundingClientRect();
    const c = { left: Math.min(...rs.map(x => x.left)), top: Math.min(...rs.map(x => x.top)), right: Math.max(...rs.map(x => x.right)), bottom: Math.max(...rs.map(x => x.bottom)) };
    c.width = c.right - c.left; return c;
  },
  conferir() {
    const prob = [], seg = SEGURO[Motor.FORMATO], minf = MIN_FONTE[Motor.FORMATO];
    const nome = e => e.id ? '#' + e.id : (e.textContent || e.className).trim().slice(0, 40);
    for (const e of $$('.t')) {
      if (!Motor._visivel(e)) continue;
      if (e.scrollHeight > e.clientHeight + 2 || e.scrollWidth > e.clientWidth + 2) prob.push('texto não cabe: ' + nome(e));
      const fs = parseFloat(getComputedStyle(e).fontSize); if (fs < (+e.dataset.min || minf) - 0.5) prob.push(`letra pequena (${fs}px): ` + nome(e));
      const r = e.getBoundingClientRect(); if (r.left < -1 || r.top < -1 || r.right > W + 1 || r.bottom > Motor.H + 1) prob.push('texto fora da tela: ' + nome(e));
    }
    for (const e of $$('.seg')) {
      if (!Motor._visivel(e)) continue; const r = Motor._caixa(e); if (!r.width) continue;
      const caixa = `(${Math.round(r.left)},${Math.round(r.top)},${Math.round(r.right)},${Math.round(r.bottom)})`;
      if (r.left < seg.x0 - 1 || r.right > seg.x1 + 1 || r.top < seg.y0 - 1 || r.bottom > seg.y1 + 1) prob.push(`fora da área livre do Instagram ${caixa}: ` + nome(e));
      else if (seg.fora.some(z => r.right > z.x0 + 1 && r.left < z.x1 && r.bottom > z.y0 + 1 && r.top < z.y1)) prob.push(`embaixo dos botões do Instagram ${caixa}: ` + nome(e));
    }
    return prob;
  },
  mostrarArea() { const s = SEGURO[Motor.FORMATO], a = $('#area'); Object.assign(a.style, { display: 'block', left: s.x0 + 'px', top: s.y0 + 'px', width: (s.x1 - s.x0) + 'px', height: (s.y1 - s.y0) + 'px' });
    for (const z of s.fora) $('#palco').insertAdjacentHTML('beforeend', `<div style="position:absolute;z-index:999;left:${z.x0}px;top:${z.y0}px;width:${z.x1 - z.x0}px;height:${z.y1 - z.y0}px;background:rgba(255,0,170,.25)"></div>`); },
};

// one frame of video
window.render = async function (t) {
  Motor._espera = [];
  Motor._fundoMove(t);
  if (Motor.def && Motor.def.quadro) Motor.def.quadro(t, Motor.F, Motor);
  Motor._finalQuadro(t);
  await Promise.all(Motor._espera);
};
window.Motor = Motor;
})();

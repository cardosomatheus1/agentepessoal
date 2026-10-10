// Chat that reads like Claude/ChatGPT: a "working" line with a spinning mark at the bottom while the
// agent runs (with what it is doing and for how long), each finished block of steps folded into one
// quiet line ("Etapas (7) · 1m 01s") instead of a header full of badges and counters, and the
// memory-housekeeping blocks hidden.
import { store as chats } from "/components/sidebar/chats/chats-store.js";

const CSS = `
  .process-group.utility-only { display: none !important; }
  .process-group-header .step-badge,
  .process-group-header .group-metrics { display: none !important; }
  .process-group-header { font-size: 13px !important; font-weight: 500 !important; opacity: .72; gap: 6px; }
  .process-group-header:hover { opacity: 1; }
  .process-group-header .group-title { font-weight: 500 !important; }
  .process-group-header.ec-feito .group-title { display: none !important; }
  .process-group-header.ec-feito::after { content: attr(data-ec-label); }
  #ec-trabalhando { display: none; align-items: center; gap: 10px; margin: 14px 0 22px; padding: 0 4px;
    font-size: 15px; color: var(--color-text, #ddd); }
  #ec-trabalhando.visivel { display: flex; }
  #ec-trabalhando .ec-marca { width: 20px; height: 20px; flex: none; color: #d97757; animation: ec-gira 1.6s linear infinite; }
  #ec-trabalhando .ec-texto { background: linear-gradient(90deg, var(--color-text, #ddd) 30%, rgba(255,255,255,.35) 50%, var(--color-text, #ddd) 70%);
    background-size: 200% auto; -webkit-background-clip: text; background-clip: text; color: transparent;
    animation: ec-brilho 1.8s linear infinite; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 70vw; }
  #ec-trabalhando .ec-tempo { opacity: .55; font-variant-numeric: tabular-nums; white-space: nowrap; }
  @keyframes ec-gira { to { transform: rotate(360deg); } }
  @keyframes ec-brilho { to { background-position: -200% center; } }
`;

const MARCA = `<svg class="ec-marca" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
  ${[0, 45, 90, 135].map((g) => `<rect x="11" y="2" width="2" height="20" rx="1" transform="rotate(${g} 12 12)"/>`).join("")}
</svg>`;

let inicio = { id: "", t: 0 };

function tempo(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

function arrumarGrupos(raiz) {
  for (const header of raiz.querySelectorAll(".process-group:not(.utility-only) > .process-group-header")) {
    // running blocks get the same quiet line; the live status is the "working" line at the bottom
    const feito = !!header.querySelector(".step-badge.END");
    header.classList.add("ec-feito");
    const passos = Number(header.querySelector(".metric-steps .metric-value")?.textContent || 0);
    const dur = header.querySelector(".metric-duration:not(.display-none) .metric-value")?.textContent?.trim();
    const rotulo = `Etapas${passos > 0 ? ` (${passos})` : ""}${feito && dur && dur !== "--" ? ` · ${dur}` : ""}`;
    if (header.dataset.ecLabel !== rotulo) header.dataset.ecLabel = rotulo;
  }
}

// "A0: Using tool 'search_engine'" -> "Pesquisando na web"
const FERRAMENTAS = [
  [/search_engine|pesquisar|busca_modelo|web_search/i, "Pesquisando na web"],
  [/browser/i, "Usando o navegador"],
  [/code_execution|terminal|shell/i, "Rodando comandos"],
  [/call_subordinate|parallel|delegat/i, "Pedindo ajuda a ajudantes"],
  [/assistir|video/i, "Assistindo ao vídeo"],
  [/memory|memoriz|remember/i, "Consultando a memória"],
  [/whatsapp|telegram|enviar/i, "Enviando mensagem"],
  [/document_query|document|pdf|planilha|sheet|docs/i, "Lendo documentos"],
  [/response/i, "Escrevendo a resposta"],
  [/calling llm|thinking|generating/i, "Pensando"],
];

function amigavel(titulo) {
  const t = String(titulo || "").replace(/^A\d+:\s*/i, "").replace(/[.…\s]+$/, "").trim();
  if (!t || /^processing/i.test(t)) return "Trabalhando";
  for (const [re, nome] of FERRAMENTAS) if (re.test(t)) return nome;
  return t.replace(/^Using (tool )?/i, "Usando ").replace(/['"]/g, "");
}

function oQueFaz(historico) {
  const grupos = historico.querySelectorAll(".process-group:not(.utility-only)");
  const ultimo = grupos[grupos.length - 1];
  if (ultimo && !ultimo.querySelector(".step-badge.END")) {
    const titulos = ultimo.querySelectorAll(".process-step .step-title");
    const atual = titulos[titulos.length - 1]?.textContent || ultimo.querySelector(".group-title")?.textContent;
    return amigavel(atual);
  }
  const barra = document.getElementById("progress-bar")?.textContent || "";
  return /aguardando|waiting/i.test(barra) ? "Trabalhando" : amigavel(barra);
}

function atualizarIndicador() {
  const historico = document.getElementById("chat-history");
  if (!historico) return;
  let el = document.getElementById("ec-trabalhando");
  if (!el) {
    el = document.createElement("div");
    el.id = "ec-trabalhando";
    el.setAttribute("role", "status");
    el.innerHTML = `${MARCA}<span class="ec-texto"></span><span class="ec-tempo"></span>`;
  }
  if (el.parentElement !== historico || el.nextElementSibling) historico.appendChild(el);

  const ctx = chats.selectedContext;
  const ativo = !!ctx?.running && !ctx?.paused;
  if (ativo && inicio.id !== ctx.id) inicio = { id: ctx.id, t: Date.now() };
  if (!ativo && inicio.id === ctx?.id) inicio = { id: "", t: 0 };
  el.classList.toggle("visivel", ativo);
  if (!ativo) return;
  const texto = `${oQueFaz(historico)}…`;
  const tx = el.querySelector(".ec-texto");
  if (tx.textContent !== texto) tx.textContent = texto;
  const tp = el.querySelector(".ec-tempo"), t = `· ${tempo(Date.now() - inicio.t)}`;
  if (tp.textContent !== t) tp.textContent = t;
}

export default async function estiloClaude() {
  if (!document.getElementById("a0-estilo-claude-css")) {
    const s = document.createElement("style");
    s.id = "a0-estilo-claude-css";
    s.textContent = CSS;
    document.head.appendChild(s);
  }
  let agendado = false;
  const varrer = () => {
    agendado = false;
    const historico = document.getElementById("chat-history");
    if (historico) arrumarGrupos(historico);
    atualizarIndicador();
  };
  new MutationObserver((muts) => {
    if (agendado) return;
    if (muts.every((m) => (m.target?.parentElement || m.target)?.closest?.("#ec-trabalhando"))) return;
    agendado = true;
    requestAnimationFrame(varrer);
  }).observe(document.body, { childList: true, subtree: true, characterData: true });
  setInterval(atualizarIndicador, 1000);
  varrer();
}

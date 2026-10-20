// Grafo do Segundo Cérebro: projeção pura (navegador ou Node) da carga do servidor (a Pasta).
// Nó = item da Pasta ou fonte. Aresta = só ligação gravada: `liga`, [[link]] no texto, substituição de decisão, texto de
// ligação da pendência. Agrupamento = cor/posição por um campo explícito (fonte, área, estado); nunca é aresta e nunca vem
// de palavras parecidas.
import { MultiDirectedGraph } from "graphology";

export const TIPOS = Object.freeze({
  fonte: { rotulo: "Fonte", cor: "#f2f5ec", forma: "square", tamanho: 13 },
  projeto: { rotulo: "Projeto", cor: "#ffd84a", forma: "square", tamanho: 11 },
  contexto: { rotulo: "Contexto", cor: "#ff7eb6", forma: "square", tamanho: 9 },
  documento: { rotulo: "Documento", cor: "#a594ff", forma: "square", tamanho: 9 },
  reuniao: { rotulo: "Reunião", cor: "#5ce08a", forma: "square", tamanho: 9 },
  nota: { rotulo: "Nota do dia", cor: "#9ad0ff", forma: "square", tamanho: 8 },
  decisao: { rotulo: "Decisão", cor: "#c6f432", forma: "diamond", tamanho: 7 },
  assunto: { rotulo: "Assunto", cor: "#ff9a5c", forma: "diamond", tamanho: 8 },
  fato: { rotulo: "Fato do perfil", cor: "#ffb454", forma: "triangle", tamanho: 7 },
  pendencia: { rotulo: "Pendência", cor: "#3fe0e6", forma: "circle", tamanho: 7 },
  referencia: { rotulo: "Referência textual", cor: "#8e9a84", forma: "circle", tamanho: 4 },
});

// classe: "proveniencia" (item → fonte de onde veio), "comprovada" (campo gravado aponta para outro item que existe),
// "referencia" (campo gravado aponta para um texto que não é item da Pasta).
export const RELACOES = Object.freeze({
  proveniencia: { rotulo: "Veio da fonte", classe: "proveniencia" },
  substitui: { rotulo: "Substitui (decisão)", classe: "comprovada" },
  liga: { rotulo: "Ligação registrada (liga)", classe: "comprovada" },
  wiki: { rotulo: "Link [[…]] no texto", classe: "comprovada" },
  ligacao_texto: { rotulo: "Ligação escrita na pendência", classe: "referencia" },
  link_sem_destino: { rotulo: "Link para nota fora da Pasta", classe: "referencia" },
  fonte_citada: { rotulo: "Fonte citada na pendência", classe: "referencia" },
});

export const AGRUPAMENTOS = Object.freeze({
  fonte: "Fonte de origem",
  area: "Área",
  meta: "Metadado explícito (tema da decisão, estado)",
  tipo: "Tipo de registro",
});

const curto = (s, n = 60) => {
  const t = String(s ?? "").replace(/\s+/g, " ").trim();
  return t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t;
};
export const normalizar = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLocaleLowerCase("pt-BR");
const textoSecoes = (secoes) => (secoes ?? []).flatMap((s) => [s.titulo ?? "", ...s.itens]).join(" ");

export function buildBrainGraph(brain) {
  const nodes = new Map();
  const edges = [];
  const add = (n) => { if (!nodes.has(n.id)) nodes.set(n.id, n); return nodes.get(n.id); };
  const edge = (de, para, relacao, evidencia, rotulo = null) => {
    if (!nodes.has(de) || !nodes.has(para)) return;
    edges.push({ id: `e${edges.length}`, de, para, relacao, classe: RELACOES[relacao].classe, rotulo, evidencia });
  };
  for (const s of brain.sources ?? []) {
    add({ id: `fonte:${s.id}`, tipo: "fonte", rotulo: s.rotulo, fonte: s.id, meta: s.estado, area: null, texto: `${s.rotulo} ${s.estado}`, registro: { fonte: s.id } });
  }
  const registro = (tipo, id, fonte, rotulo, textoBusca, meta, extra = {}) => {
    const n = add({ id: `${tipo}:${id}`, tipo, rotulo: curto(rotulo || id), rotuloCompleto: rotulo || id, fonte, meta, texto: textoBusca, registro: { fonte, id }, area: null, ...extra });
    edge(n.id, `fonte:${fonte}`, "proveniencia", { fonte, registro: id, campo: "arquivo", localizador: extra.localizador ?? null });
    return n;
  };
  for (const d of brain.decisions ?? []) {
    registro("decisao", d.id, "decisoes", d.tema ?? `decisão ${d.id}`, [d.tema, d.valor, d.citacao].join(" "), `tema: ${(d.tema ?? "sem tema").split(".")[0]}`, { estado: d.estadoEfetivo, area: d.area, localizador: d.proveniencia?.localizador });
  }
  for (const f of brain.profile ?? []) registro("fato", f.id, "perfil", f.texto, f.texto, "perfil", { area: f.area ?? null, localizador: f.proveniencia?.localizador });
  for (const t of brain.threads ?? []) registro("pendencia", t.id, "pendencias", t.titulo ?? t.id, [t.titulo, t.detalhe, t.proximo_passo].join(" "), `estado: ${t.estado ?? "aberto"}`, { estado: t.estado, area: t.area, localizador: t.proveniencia?.localizador });
  for (const a of brain.subjects ?? []) registro("assunto", a.id, "assuntos", a.titulo ?? a.id, [a.titulo, a.onde_parou].join(" "), `estado: ${a.estado}`, { estado: a.estado, area: a.area, localizador: a.proveniencia?.localizador });
  for (const c of brain.contexts ?? []) registro("contexto", c.id, "contexto", c.titulo, [c.titulo, textoSecoes(c.secoes)].join(" "), `contexto ${c.estado}`, { estado: c.estado, area: c.area, localizador: c.proveniencia?.localizador });
  for (const m of brain.meetings ?? []) registro("reuniao", m.id, "reunioes", m.titulo, [m.titulo, textoSecoes(m.secoes)].join(" "), "reunião", { area: m.area, localizador: m.proveniencia?.localizador });
  for (const n of brain.daily ?? []) registro("nota", n.id, "notas", n.titulo, [n.titulo, textoSecoes(n.secoes)].join(" "), "nota do dia", { area: n.area, localizador: n.proveniencia?.localizador });
  for (const d of brain.documents ?? []) registro("documento", d.id, "documentos", d.titulo, [d.titulo, textoSecoes(d.secoes)].join(" "), "documento", { area: d.area, localizador: d.proveniencia?.localizador });
  for (const p of brain.projects ?? []) registro("projeto", p.id, "projetos", p.titulo, [p.titulo, textoSecoes(p.secoes)].join(" "), "projeto", { area: p.area, localizador: p.proveniencia?.localizador });

  for (const d of brain.decisions ?? []) {
    if (d.substitui) edge(`decisao:${d.id}`, `decisao:${d.substitui}`, "substitui", { fonte: "decisoes", registro: d.id, campo: "substitui", localizador: d.proveniencia?.localizador });
  }
  const fonteDoRef = (ref) => ({ decisao: "decisoes", pendencia: "pendencias", assunto: "assuntos", contexto: "contexto", reuniao: "reunioes", nota: "notas", documento: "documentos", projeto: "projetos" })[ref.split(":")[0]] ?? null;
  for (const l of brain.links ?? []) {
    let relacao;
    if (l.resolvido) relacao = l.vias.includes("liga") || l.vias.includes("ligacoes") ? "liga" : "wiki";
    else {
      relacao = l.vias.includes("ligacoes") ? "ligacao_texto" : "link_sem_destino";
      add({ id: l.para, tipo: "referencia", rotulo: curto(l.alvo, 48), rotuloCompleto: l.alvo, fonte: fonteDoRef(l.de), meta: "referência", area: null, texto: l.alvo, registro: null });
    }
    edge(l.de, l.para, relacao, { ...l.evidencia, vias: l.vias });
  }
  for (const t of brain.threads ?? []) {
    for (const fonteCitada of t.fontes ?? []) {
      const ref = add({ id: `referencia:${fonteCitada}`, tipo: "referencia", rotulo: curto(fonteCitada, 48), rotuloCompleto: fonteCitada, fonte: "pendencias", meta: "referência", area: null, texto: fonteCitada, registro: null });
      edge(`pendencia:${t.id}`, ref.id, "fonte_citada", { fonte: "pendencias", registro: t.id, campo: "fontes", localizador: t.proveniencia?.localizador });
    }
  }
  return { nodes: [...nodes.values()], edges };
}

export function grupoDe(node, modo = "fonte") {
  if (modo === "tipo") return TIPOS[node.tipo]?.rotulo ?? node.tipo;
  if (modo === "meta") return node.tipo === "fonte" ? `fonte: ${node.fonte}` : node.meta ?? node.fonte;
  if (modo === "area") return node.tipo === "fonte" ? "fontes" : node.area ? `área: ${node.area}` : "sem área";
  return node.fonte ?? "sem fonte";
}

// Filtros por tipo, fonte, área e relação + busca. Nó isolado continua visível; vizinhos só entram se pedidos, e
// só pelas relações ligadas, marcados como contexto (não como resultado). Área só filtra itens (fonte e referência
// não têm área).
export function filterBrainGraph(graph, { termo = "", tipos, fontes, areas, relacoes, vizinhos = false } = {}) {
  const t = normalizar(termo.trim());
  const areaOk = (n) => !areas || n.tipo === "fonte" || n.tipo === "referencia" || areas.has(n.area ?? "geral");
  const ok = (n) => (!tipos || tipos.has(n.tipo)) && (!fontes || fontes.has(n.fonte)) && areaOk(n);
  const casa = (n) => !t || normalizar(`${n.rotuloCompleto ?? n.rotulo} ${n.texto ?? ""} ${n.id}`).includes(t);
  const relOk = (e) => !relacoes || relacoes.has(e.relacao);
  const matches = new Set(graph.nodes.filter((n) => ok(n) && casa(n)).map((n) => n.id));
  const visiveis = new Set(matches);
  const contexto = new Set();
  if (vizinhos && t) {
    for (const e of graph.edges) {
      if (!relOk(e)) continue;
      if (matches.has(e.de) && !visiveis.has(e.para)) { contexto.add(e.para); }
      if (matches.has(e.para) && !visiveis.has(e.de)) { contexto.add(e.de); }
    }
    for (const id of contexto) visiveis.add(id);
  }
  const nodes = graph.nodes.filter((n) => visiveis.has(n.id));
  const edges = graph.edges.filter((e) => relOk(e) && visiveis.has(e.de) && visiveis.has(e.para));
  return { nodes, edges, matches, contexto };
}

// Posições determinísticas: grupos em círculo, nós de cada grupo em espiral (filotaxia) em volta da fonte.
export function layoutBrainGraph(graph, modo = "fonte") {
  const grupos = new Map();
  for (const n of [...graph.nodes].sort((a, b) => (a.tipo === "fonte" ? -1 : 0) - (b.tipo === "fonte" ? -1 : 0) || a.id.localeCompare(b.id))) {
    const g = grupoDe(n, modo);
    if (!grupos.has(g)) grupos.set(g, []);
    grupos.get(g).push(n.id);
  }
  const nomes = [...grupos.keys()].sort((a, b) => grupos.get(b).length - grupos.get(a).length || a.localeCompare(b));
  // Grupos empacotados em prateleiras (maior primeiro), com folga fixa: a visão ampla usa a tela inteira e o
  // espaçamento entre nós de um grupo continua legível depois que o Sigma ajusta o zoom.
  const passo = 40;
  const raio = (k) => passo * Math.sqrt(k) + 50;
  const folga = 90;
  const diametros = nomes.map((g) => 2 * raio(grupos.get(g).length));
  const largura = Math.max(...diametros, Math.sqrt(diametros.reduce((s, d) => s + (d + folga) ** 2, 0)) * 1.35);
  const positions = new Map();
  const centros = new Map();
  let x = 0, y = 0, alturaLinha = 0;
  nomes.forEach((g, gi) => {
    const d = diametros[gi];
    if (x > 0 && x + d > largura) { x = 0; y += alturaLinha + folga; alturaLinha = 0; }
    const cx = x + d / 2;
    const cy = y + d / 2;
    x += d + folga;
    alturaLinha = Math.max(alturaLinha, d);
    centros.set(g, { x: cx, y: cy, raio: d / 2 });
    grupos.get(g).forEach((id, i) => {
      const r = i === 0 ? 0 : passo * Math.sqrt(i + 0.5);
      const a = i * 2.39996323;
      positions.set(id, { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });
    });
  });
  return { positions, centros };
}

export function nodeStyle(node, degree = 0) {
  const t = TIPOS[node.tipo] ?? TIPOS.referencia;
  return { color: t.cor, shape: t.forma, size: t.tamanho + Math.min(6, Math.sqrt(degree)) };
}

export function buildSigmaGraph(view, positions) {
  const g = new MultiDirectedGraph({ allowSelfLoops: true });
  const grau = new Map(view.nodes.map((n) => [n.id, 0]));
  for (const e of view.edges) { grau.set(e.de, (grau.get(e.de) ?? 0) + 1); grau.set(e.para, (grau.get(e.para) ?? 0) + 1); }
  for (const n of view.nodes) {
    const p = positions.get(n.id) ?? { x: 0, y: 0 };
    g.addNode(n.id, { x: p.x, y: p.y, label: n.rotulo, tipo: n.tipo, ...nodeStyle(n, grau.get(n.id)) });
  }
  for (const e of view.edges) {
    if (g.hasNode(e.de) && g.hasNode(e.para)) g.addDirectedEdgeWithKey(e.id, e.de, e.para, { relacao: e.relacao, classe: e.classe, label: e.rotulo ?? "" });
  }
  return g;
}

export function neighborsOf(graph, id) {
  const out = [];
  for (const e of graph.edges) {
    if (e.de === id) out.push({ edge: e, outro: e.para, direcao: "saida" });
    else if (e.para === id) out.push({ edge: e, outro: e.de, direcao: "entrada" });
  }
  return out;
}

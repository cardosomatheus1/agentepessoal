// Grafo do Segundo Cérebro: projeção pura (navegador ou Node) da carga do servidor.
// Nó = registro canônico ou fonte. Aresta = só metadado explícito com destino válido. Agrupamento = cor/posição por
// um campo explícito (fonte, prefixo do tema, estado do fio); nunca é aresta e nunca vem de palavras parecidas.
import { MultiDirectedGraph } from "graphology";

export const TIPOS = Object.freeze({
  fonte: { rotulo: "Fonte", cor: "#f2f5ec", forma: "square", tamanho: 13 },
  projeto: { rotulo: "Projeto", cor: "#ffd84a", forma: "square", tamanho: 11 },
  contexto: { rotulo: "Contexto", cor: "#ff7eb6", forma: "square", tamanho: 9 },
  documento: { rotulo: "Documento", cor: "#a594ff", forma: "square", tamanho: 9 },
  rotina: { rotulo: "Rotina", cor: "#5ce08a", forma: "diamond", tamanho: 10 },
  decisao: { rotulo: "Decisão", cor: "#c6f432", forma: "diamond", tamanho: 7 },
  fato: { rotulo: "Fato da ficha", cor: "#ffb454", forma: "triangle", tamanho: 7 },
  fio: { rotulo: "Fio", cor: "#3fe0e6", forma: "circle", tamanho: 7 },
  referencia: { rotulo: "Referência textual", cor: "#8e9a84", forma: "circle", tamanho: 4 },
});

// classe: "proveniencia" (registro → arquivo de onde veio), "comprovada" (metadado aponta para outro registro que
// existe), "referencia" (metadado aponta para um texto que não é registro).
export const RELACOES = Object.freeze({
  proveniencia: { rotulo: "Veio da fonte", classe: "proveniencia" },
  substitui: { rotulo: "Substitui (decisão)", classe: "comprovada" },
  ligacao_fio: { rotulo: "Ligação entre fios", classe: "comprovada" },
  cita_documento: { rotulo: "Cita documento (caminho)", classe: "comprovada" },
  ligacao_texto: { rotulo: "Ligação escrita no fio", classe: "referencia" },
  fonte_citada: { rotulo: "Fonte citada no fio", classe: "referencia" },
});

export const AGRUPAMENTOS = Object.freeze({
  fonte: "Fonte de origem",
  meta: "Metadado explícito (tema da decisão, estado do fio)",
  tipo: "Tipo de registro",
});

const curto = (s, n = 60) => {
  const t = String(s ?? "").replace(/\s+/g, " ").trim();
  return t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t;
};
export const normalizar = (s) => String(s ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR");

export function buildBrainGraph(brain) {
  const nodes = new Map();
  const edges = [];
  const add = (n) => { if (!nodes.has(n.id)) nodes.set(n.id, n); return nodes.get(n.id); };
  const edge = (de, para, relacao, evidencia, rotulo = null) => {
    if (!nodes.has(de) || !nodes.has(para)) return;
    edges.push({ id: `e${edges.length}`, de, para, relacao, classe: RELACOES[relacao].classe, rotulo, evidencia });
  };
  for (const s of brain.sources ?? []) {
    add({ id: `fonte:${s.id}`, tipo: "fonte", rotulo: s.rotulo, fonte: s.id, meta: s.estado, texto: `${s.rotulo} ${s.estado}`, registro: { fonte: s.id } });
  }
  const registro = (tipo, id, fonte, rotulo, textoBusca, meta, extra = {}) => {
    const n = add({ id: `${tipo}:${id}`, tipo, rotulo: curto(rotulo || id), rotuloCompleto: rotulo || id, fonte, meta, texto: textoBusca, registro: { fonte, id }, ...extra });
    edge(n.id, `fonte:${fonte}`, "proveniencia", { fonte, registro: id, campo: "arquivo", localizador: extra.localizador ?? null });
    return n;
  };
  for (const d of brain.decisions ?? []) {
    registro("decisao", d.id, "decisoes", d.tema ?? `decisão ${d.id}`, [d.tema, d.valor, d.citacao].join(" "), `tema: ${(d.tema ?? "sem tema").split(".")[0]}`, { estado: d.estadoEfetivo, localizador: d.proveniencia?.localizador });
  }
  for (const f of brain.profile ?? []) registro("fato", f.id, "perfil", f.texto, f.texto, "ficha", { localizador: f.proveniencia?.localizador });
  for (const t of brain.threads ?? []) registro("fio", t.id, "fios", t.titulo ?? t.id, [t.titulo, t.detalhe, t.proximo_passo].join(" "), `estado: ${t.estado ?? "aberto"}`, { estado: t.estado, localizador: t.proveniencia?.localizador });
  for (const c of brain.contexts ?? []) registro("contexto", c.id, "contexto", c.titulo, [c.titulo, ...c.itens.map((i) => i.texto)].join(" "), "contexto", { localizador: c.proveniencia?.localizador });
  for (const d of brain.documents ?? []) registro("documento", d.id, "documentos", d.titulo, [d.titulo, ...d.secoes.map((s) => s.titulo)].join(" "), `dono: ${d.dono}`, { localizador: d.proveniencia?.localizador });
  for (const r of brain.routines ?? []) registro("rotina", r.id, "rotinas", r.nome, [r.nome, r.descricao, ...r.passos].join(" "), r.dono ? "dono: matheus" : "compartilhada", { localizador: r.proveniencia?.localizador });
  for (const p of brain.projects ?? []) registro("projeto", p.id, "projetos", p.titulo, [p.titulo, p.descricao].join(" "), "projeto", { localizador: p.proveniencia?.localizador });

  for (const d of brain.decisions ?? []) {
    if (d.substitui) edge(`decisao:${d.id}`, `decisao:${d.substitui}`, "substitui", { fonte: "decisoes", registro: d.id, campo: "substitui", localizador: d.proveniencia?.localizador });
  }
  const fios = new Set((brain.threads ?? []).map((t) => t.id));
  for (const t of brain.threads ?? []) {
    for (const l of t.ligacoes ?? []) {
      if (fios.has(l.alvo)) {
        edge(`fio:${t.id}`, `fio:${l.alvo}`, "ligacao_fio", { fonte: "fios", registro: t.id, campo: "ligacoes", localizador: t.proveniencia?.localizador }, l.rotulo);
      } else {
        const ref = add({ id: `referencia:${l.alvo}`, tipo: "referencia", rotulo: curto(l.alvo, 48), rotuloCompleto: l.alvo, fonte: "fios", meta: "referência", texto: l.alvo, registro: null });
        edge(`fio:${t.id}`, ref.id, "ligacao_texto", { fonte: "fios", registro: t.id, campo: "ligacoes", localizador: t.proveniencia?.localizador }, l.rotulo);
      }
    }
    for (const fonteCitada of t.fontes ?? []) {
      const ref = add({ id: `referencia:${fonteCitada}`, tipo: "referencia", rotulo: curto(fonteCitada, 48), rotuloCompleto: fonteCitada, fonte: "fios", meta: "referência", texto: fonteCitada, registro: null });
      edge(`fio:${t.id}`, ref.id, "fonte_citada", { fonte: "fios", registro: t.id, campo: "fontes", localizador: t.proveniencia?.localizador });
    }
  }
  for (const d of brain.documents ?? []) {
    for (const alvo of d.citaDocumentos ?? []) edge(`documento:${d.id}`, `documento:${alvo}`, "cita_documento", { fonte: "documentos", registro: d.id, campo: "caminho citado no texto", localizador: d.proveniencia?.localizador });
  }
  return { nodes: [...nodes.values()], edges };
}

export function grupoDe(node, modo = "fonte") {
  if (modo === "tipo") return TIPOS[node.tipo]?.rotulo ?? node.tipo;
  if (modo === "meta") return node.tipo === "fonte" ? `fonte: ${node.fonte}` : node.meta ?? node.fonte;
  return node.fonte;
}

// Filtros por tipo, fonte e relação + busca. Nó isolado continua visível; vizinhos só entram se pedidos, e
// só pelas relações ligadas, marcados como contexto (não como resultado).
export function filterBrainGraph(graph, { termo = "", tipos, fontes, relacoes, vizinhos = false } = {}) {
  const t = normalizar(termo.trim());
  const ok = (n) => (!tipos || tipos.has(n.tipo)) && (!fontes || fontes.has(n.fonte));
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

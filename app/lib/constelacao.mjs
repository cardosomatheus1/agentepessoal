// Constelação do Segundo Cérebro (23/10, Matheus: "Gostei desse modelo de front desse 2 cérebro, o nosso podia ser
// assim"): três visões do mesmo grafo da Pasta (brain-graph.mjs), em coordenadas de unidade (o centro é 0,0 e o disco
// cabe no raio 1). Puro: roda no navegador e no Node, sem sorteio (mesma Pasta, mesmo desenho).
//   disco: cada tipo de registro é um setor de anéis de pontos em volta do centro; as fontes orbitam como hexágonos.
//   forca: as ligações gravadas puxam, todos os pontos se afastam, cada um é atraído para a sua fonte.
//   aneis: cada tipo é um anel inclinado no espaço; a tela gira a cena e projeta em perspectiva.
import { TIPOS } from "./brain-graph.mjs";

export const MODOS = Object.freeze({ disco: "Disco", forca: "Força", aneis: "Anéis" });
export const ORDEM_TIPOS = Object.freeze(["decisao", "pendencia", "assunto", "nota", "reuniao", "documento", "contexto", "projeto", "fato", "referencia"]);
export const RAIO_ORBITA = 0.94;
const R_DENTRO = 0.2, R_FORA = 0.76, FOLGA = 0.07;

const itens = (graph) => graph.nodes.filter((n) => n.tipo !== "fonte");
const fontes = (graph) => graph.nodes.filter((n) => n.tipo === "fonte");
const porTipo = (graph) => {
  const grupos = new Map(ORDEM_TIPOS.map((t) => [t, []]));
  for (const n of itens(graph)) (grupos.get(n.tipo) ?? grupos.set(n.tipo, []).get(n.tipo)).push(n);
  for (const lista of grupos.values()) lista.sort((a, b) => a.id.localeCompare(b.id));
  return [...grupos.entries()].filter(([, l]) => l.length);
};
export const rotuloTipo = (tipo, n) => `${(TIPOS[tipo]?.rotulo ?? tipo).toLocaleUpperCase("pt-BR")} · ${n}`;

// Disco: setores proporcionais ao número de itens (com um mínimo, para um tipo pequeno não sumir), e dentro de cada
// setor os pontos em fileiras de arco, das de dentro para as de fora.
export function layoutDisco(graph) {
  const grupos = porTipo(graph);
  const total = grupos.reduce((s, [, l]) => s + l.length, 0) || 1;
  const livre = 2 * Math.PI - FOLGA * grupos.length;
  const minimo = Math.min(0.18, livre / Math.max(1, grupos.length));
  const brutos = grupos.map(([, l]) => Math.max(minimo, (livre * l.length) / total));
  const escala = livre / brutos.reduce((s, x) => s + x, 0);
  const posicoes = new Map();
  const setores = [];
  let angulo = -Math.PI / 2 + FOLGA / 2;
  grupos.forEach(([tipo, lista], gi) => {
    const largura = brutos[gi] * escala;
    const meio = (R_DENTRO + R_FORA) / 2;
    const fileiras = Math.max(1, Math.min(14, Math.round(Math.sqrt((lista.length * (R_FORA - R_DENTRO)) / (largura * meio)))));
    const porFileira = Math.ceil(lista.length / fileiras);
    lista.forEach((n, i) => {
      const f = i % fileiras, c = Math.floor(i / fileiras);
      const r = R_DENTRO + ((f + 0.5) * (R_FORA - R_DENTRO)) / fileiras;
      const a = angulo + ((c + 0.5) * largura) / porFileira;
      posicoes.set(n.id, { x: r * Math.cos(a), y: r * Math.sin(a) });
    });
    setores.push({ tipo, n: lista.length, inicio: angulo, fim: angulo + largura, rotulo: rotuloTipo(tipo, lista.length) });
    angulo += largura + FOLGA;
  });
  const fs = fontes(graph).sort((a, b) => a.id.localeCompare(b.id));
  const orbita = fs.map((n, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(1, fs.length);
    const p = { x: RAIO_ORBITA * Math.cos(a), y: RAIO_ORBITA * Math.sin(a) };
    posicoes.set(n.id, p);
    return { id: n.id, rotulo: n.rotulo, ...p };
  });
  return { posicoes, setores, orbita };
}

// Força: começa do disco (determinístico), repulsão entre todos em grade, mola nas ligações, atração para a fonte
// de origem e para o centro. Normaliza para caber no raio 1.
export function layoutForca(graph, { passos = 120 } = {}) {
  const { posicoes: inicio } = layoutDisco(graph);
  const ids = graph.nodes.map((n) => n.id);
  const idx = new Map(ids.map((id, i) => [id, i]));
  const x = new Float64Array(ids.length), y = new Float64Array(ids.length);
  ids.forEach((id, i) => { const p = inicio.get(id) ?? { x: 0, y: 0 }; x[i] = p.x; y[i] = p.y; });
  const arestas = graph.edges.map((e) => [idx.get(e.de), idx.get(e.para)]).filter(([a, b]) => a !== undefined && b !== undefined && a !== b);
  const fonteDe = graph.nodes.map((n) => (n.tipo === "fonte" ? -1 : idx.get(`fonte:${n.fonte}`) ?? -1));
  const k = 0.9 / Math.sqrt(Math.max(1, ids.length));
  const celula = k * 3;
  for (let passo = 0; passo < passos; passo++) {
    const t = 0.05 * (1 - passo / passos) + 0.004;
    const dx = new Float64Array(ids.length), dy = new Float64Array(ids.length);
    const grade = new Map();
    for (let i = 0; i < ids.length; i++) {
      const ch = `${Math.floor(x[i] / celula)},${Math.floor(y[i] / celula)}`;
      (grade.get(ch) ?? grade.set(ch, []).get(ch)).push(i);
    }
    for (let i = 0; i < ids.length; i++) {
      const cx = Math.floor(x[i] / celula), cy = Math.floor(y[i] / celula);
      for (let ox = -1; ox <= 1; ox++) for (let oy = -1; oy <= 1; oy++) {
        for (const j of grade.get(`${cx + ox},${cy + oy}`) ?? []) {
          if (j <= i) continue;
          let vx = x[i] - x[j], vy = y[i] - y[j];
          let d2 = vx * vx + vy * vy;
          if (d2 < 1e-9) { vx = ((i * 7919) % 13) / 1e4 - 6e-4; vy = ((j * 104729) % 11) / 1e4 - 5e-4; d2 = vx * vx + vy * vy + 1e-9; }
          const f = (k * k) / d2;
          dx[i] += vx * f; dy[i] += vy * f; dx[j] -= vx * f; dy[j] -= vy * f;
        }
      }
    }
    for (const [a, b] of arestas) {
      const vx = x[a] - x[b], vy = y[a] - y[b];
      const d = Math.sqrt(vx * vx + vy * vy) || 1e-6;
      const f = (d * d) / k / d * 0.5;
      dx[a] -= vx * f; dy[a] -= vy * f; dx[b] += vx * f; dy[b] += vy * f;
    }
    for (let i = 0; i < ids.length; i++) {
      const s = fonteDe[i];
      if (s >= 0) { dx[i] += (x[s] - x[i]) * 0.6; dy[i] += (y[s] - y[i]) * 0.6; }
      dx[i] -= x[i] * 0.08; dy[i] -= y[i] * 0.08;
      const d = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) || 1;
      const passoMax = Math.min(d, t);
      x[i] += (dx[i] / d) * passoMax; y[i] += (dy[i] / d) * passoMax;
    }
  }
  let maior = 1e-9;
  for (let i = 0; i < ids.length; i++) maior = Math.max(maior, Math.hypot(x[i], y[i]));
  const posicoes = new Map(ids.map((id, i) => [id, { x: (x[i] / maior) * 0.95, y: (y[i] / maior) * 0.95 }]));
  return { posicoes };
}

// Anéis: cada tipo é um anel (com algumas voltas paralelas, se for grande) inclinado num ângulo próprio; as fontes
// ficam numa órbita larga no plano do chão.
export function layoutAneis(graph) {
  const grupos = porTipo(graph).sort((a, b) => a[1].length - b[1].length); // os grandes por fora, onde há espaço
  const pontos = new Map();
  grupos.forEach(([, lista], gi) => {
    const raio = 0.28 + 0.66 * ((gi + 1) / grupos.length);
    const incl = -0.9 + (1.8 * gi) / Math.max(1, grupos.length - 1 || 1);
    const giro = gi * 0.85;
    const voltas = Math.max(1, Math.ceil(lista.length / 90));
    lista.forEach((n, i) => {
      const v = i % voltas;
      const a = (Math.floor(i / voltas) / Math.ceil(lista.length / voltas)) * 2 * Math.PI + v * 0.04;
      const r = raio + v * 0.018;
      const px = r * Math.cos(a), pz = r * Math.sin(a);
      const y1 = -pz * Math.sin(incl), z1 = pz * Math.cos(incl);
      pontos.set(n.id, { x: px * Math.cos(giro) - z1 * Math.sin(giro), y: y1, z: px * Math.sin(giro) + z1 * Math.cos(giro) });
    });
  });
  const fs = fontes(graph).sort((a, b) => a.id.localeCompare(b.id));
  fs.forEach((n, i) => {
    const a = (i * 2 * Math.PI) / Math.max(1, fs.length);
    pontos.set(n.id, { x: 1.05 * Math.cos(a), y: 0, z: 1.05 * Math.sin(a) });
  });
  return { pontos };
}

// Gira em volta do eixo vertical (giro) e inclina para a câmera (inclinacao); perspectiva com a câmera a `dist`.
export function projetar(p, giro, inclinacao = 0.35, dist = 3.2) {
  const x1 = p.x * Math.cos(giro) + p.z * Math.sin(giro);
  const z1 = -p.x * Math.sin(giro) + p.z * Math.cos(giro);
  const y2 = p.y * Math.cos(inclinacao) - z1 * Math.sin(inclinacao);
  const z2 = p.y * Math.sin(inclinacao) + z1 * Math.cos(inclinacao);
  const escala = dist / (dist + z2);
  return { x: x1 * escala, y: y2 * escala, escala, profundidade: z2 };
}

// O painel do lado: para onde o item aponta e quem aponta para ele, só pelas ligações gravadas (sem a proveniência,
// que já aparece como "Fonte").
export function ligacoesDoItem(graph, id) {
  const porId = new Map(graph.nodes.map((n) => [n.id, n]));
  const aponta = [], referenciado = [];
  for (const e of graph.edges) {
    if (e.relacao === "proveniencia") continue;
    if (e.de === id && porId.has(e.para)) aponta.push({ relacao: e.relacao, no: porId.get(e.para) });
    else if (e.para === id && porId.has(e.de)) referenciado.push({ relacao: e.relacao, no: porId.get(e.de) });
  }
  return { aponta, referenciado };
}

// O item mais perto de um ponto da tela (em pixels), dentro de `raio`; null se nenhum.
export function maisPerto(pontosTela, px, py, raio = 12) {
  let melhor = null, d2min = raio * raio;
  for (const [id, p] of pontosTela) {
    const d2 = (p.x - px) ** 2 + (p.y - py) ** 2;
    if (d2 <= d2min) { d2min = d2; melhor = id; }
  }
  return melhor;
}

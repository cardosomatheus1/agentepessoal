// Constelação do Segundo Cérebro (23/10, Matheus: "Gostei desse modelo de front desse 2 cérebro, o nosso podia ser
// assim" e "precisa ser tão bonito quanto"). Três poses do mesmo grafo da Pasta (brain-graph.mjs), no espaço da cena
// (centro 0,0,0; o disco cabe no raio ~1). Puro, sem sorteio: roda no navegador (Three.js desenha) e no Node (testes).
//   disco: o núcleo é um girassol de decisões; os outros registros são traços em faixas de anéis por tipo; os arquivos
//          (fontes, contexto, projetos, documentos, reuniões, notas) orbitam como hexágonos.
//   forca: cada fonte é um hexágono-polo com os seus registros em anéis em volta; os polos se afastam entre si.
//   aneis: cada tipo é uma órbita inclinada no espaço em volta do núcleo; a câmera gira.
// Cada item tem uma pose {x, y, z, ang, sx, sy}: posição, giro do traço e tamanho (sx = sy é ponto; sx > sy é traço).
import { TIPOS } from "./brain-graph.mjs";

export const MODOS = Object.freeze({ disco: "Disco", forca: "Força", aneis: "Anéis" });
// Paleta do vídeo de referência: verde-limão, verde-água, laranja, âmbar, azul-aço, lavanda.
export const CORES = Object.freeze({
  decisao: "#b8f26a", pendencia: "#52e3c2", assunto: "#f5a25d", referencia: "#7db9d8", fato: "#ffd36e",
  contexto: "#c4a8ff", projeto: "#ffd36e", documento: "#9db3ff", reuniao: "#7fe39a", nota: "#8fd6ff", fonte: "#6fe7e0",
});
export const NUCLEO = "decisao"; // o girassol do centro: o que ele decidiu
export const TIPOS_HEX = Object.freeze(["fonte", "contexto", "projeto", "documento", "reuniao", "nota"]);
export const ORDEM_FAIXAS = Object.freeze(["pendencia", "assunto", "fato", "referencia"]);
export const RAIO_ORBITA = 1.0;
export const RAIO_LINHA = 0.82;
const R_SOL = 0.3, R_FAIXA_DENTRO = 0.37, R_FAIXA_FORA = 0.72, FOLGA = 0.06, OURO = 2.39996323;

export const ehHex = (n) => TIPOS_HEX.includes(n.tipo);
export const corDoTipo = (tipo) => CORES[tipo] ?? TIPOS[tipo]?.cor ?? "#8e9a84";
export const rotuloTipo = (tipo, n) => `${(TIPOS[tipo]?.rotulo ?? tipo).toLocaleUpperCase("pt-BR")} · ${n}`;
const porNome = (a, b) => a.id.localeCompare(b.id);
const ponto = (x, y, z = 0, tam = 1) => ({ x, y, z, ang: 0, sx: tam, sy: tam });

function separar(graph) {
  const hex = graph.nodes.filter(ehHex).sort((a, b) => (a.tipo === "fonte" ? 0 : 1) - (b.tipo === "fonte" ? 0 : 1) || porNome(a, b));
  const itens = graph.nodes.filter((n) => !ehHex(n));
  const grupos = new Map();
  for (const n of itens) (grupos.get(n.tipo) ?? grupos.set(n.tipo, []).get(n.tipo)).push(n);
  for (const l of grupos.values()) l.sort(porNome);
  return { hex, itens, grupos };
}
function graus(graph) {
  const g = new Map(graph.nodes.map((n) => [n.id, 0]));
  for (const e of graph.edges) { g.set(e.de, (g.get(e.de) ?? 0) + 1); g.set(e.para, (g.get(e.para) ?? 0) + 1); }
  return g;
}
// Girassol (filotaxia): n pontos num disco de raio r, espaçados por igual.
export function girassol(n, r) {
  return Array.from({ length: n }, (_, i) => {
    const rr = r * Math.sqrt((i + 0.5) / Math.max(1, n));
    return { x: rr * Math.cos(i * OURO), y: rr * Math.sin(i * OURO) };
  });
}

export function poseDisco(graph) {
  const { hex, grupos } = separar(graph);
  const grau = graus(graph);
  const itens = new Map();
  const rotulos = [];
  const sol = grupos.get(NUCLEO) ?? [];
  girassol(sol.length, R_SOL).forEach((p, i) => itens.set(sol[i].id, ponto(p.x, p.y, 0, 1)));
  if (sol.length) rotulos.push({ texto: rotuloTipo(NUCLEO, sol.length), x: 0, y: R_SOL + 0.035, z: 0, cor: corDoTipo(NUCLEO), estilo: "texto" });
  // Faixas: os outros tipos (e qualquer tipo novo) em setores, cada item um traço tangente ao anel.
  const faixas = [...ORDEM_FAIXAS, ...[...grupos.keys()].filter((t) => t !== NUCLEO && !ORDEM_FAIXAS.includes(t)).sort()]
    .filter((t) => grupos.get(t)?.length);
  const total = faixas.reduce((s, t) => s + grupos.get(t).length, 0) || 1;
  const livre = 2 * Math.PI - FOLGA * faixas.length;
  const minimo = Math.min(0.35, livre / Math.max(1, faixas.length));
  const brutos = faixas.map((t) => Math.max(minimo, (livre * grupos.get(t).length) / total));
  const escala = livre / brutos.reduce((s, x) => s + x, 0);
  const setores = [];
  let a0 = Math.PI / 2 + FOLGA / 2;
  faixas.forEach((tipo, k) => {
    const lista = grupos.get(tipo);
    const largura = brutos[k] * escala;
    // Anéis tracejados (como no vídeo): cada fileira é um arco; cada traço ocupa ~78% do seu pedaço de arco, e as
    // fileiras se alternam meio passo para os traços não formarem colunas.
    const meio = (R_FAIXA_DENTRO + R_FAIXA_FORA) / 2;
    const fileiras = Math.max(2, Math.min(12, Math.round(Math.sqrt(lista.length * 0.55)), Math.ceil(lista.length / 3)));
    const porFileira = Math.ceil(lista.length / fileiras);
    const faixa = Math.min(R_FAIXA_FORA - R_FAIXA_DENTRO, fileiras * 0.034);
    const base = R_FAIXA_DENTRO + (R_FAIXA_FORA - R_FAIXA_DENTRO - faixa) / 2;
    lista.forEach((n, i) => {
      const f = Math.floor(i / porFileira), c = i % porFileira;
      const naFileira = Math.min(porFileira, lista.length - f * porFileira);
      const r = base + ((f + 0.5) * faixa) / fileiras;
      const passo = largura / naFileira;
      const ang = a0 + (c + 0.5 + (f % 2) * 0.35) * passo; // fileira ímpar desliza um pouco: sem colunas
      const comprimento = Math.min(0.032, Math.max(0.01, r * passo * 0.7)) / 0.0105;
      itens.set(n.id, { x: r * Math.cos(ang), y: r * Math.sin(ang), z: 0, ang: ang + Math.PI / 2, sx: comprimento, sy: 0.5 });
    });
    const meioAng = a0 + largura / 2;
    setores.push({ tipo, n: lista.length, inicio: a0, fim: a0 + largura });
    rotulos.push({ texto: rotuloTipo(tipo, lista.length), x: (R_FAIXA_FORA + 0.05) * Math.cos(meioAng), y: (R_FAIXA_FORA + 0.05) * Math.sin(meioAng), z: 0, cor: corDoTipo(tipo), estilo: "pilula" });
    a0 += largura + FOLGA;
  });
  // Órbita de hexágonos: tamanho pelo número de ligações.
  const hexes = new Map();
  hex.forEach((n, i) => {
    const a = Math.PI / 2 - (i * 2 * Math.PI) / Math.max(1, hex.length);
    const tam = 1 + Math.min(1.2, Math.sqrt(grau.get(n.id) ?? 0) / 6);
    hexes.set(n.id, { x: RAIO_ORBITA * Math.cos(a), y: RAIO_ORBITA * Math.sin(a), z: 0, tam });
  });
  return { itens, hexes, rotulos, setores, linhas: [{ r: RAIO_LINHA, cor: "#e3c56a" }, { r: RAIO_ORBITA, cor: "#3d5a4f" }] };
}

// Força: polos (fontes) espalhados por repulsão entre eles e uma mola fraca para o centro; os registros de cada fonte
// em anéis em volta do polo (6, 12, 18… por anel); os outros hexágonos ficam no primeiro anel, maiores.
export function poseForca(graph) {
  const { hex, itens: soltos } = separar(graph);
  const polos = hex.filter((n) => n.tipo === "fonte");
  const filhos = new Map(polos.map((p) => [p.id, []]));
  const semPolo = [];
  for (const n of [...hex.filter((h) => h.tipo !== "fonte"), ...soltos].sort(porNome)) {
    const lista = filhos.get(`fonte:${n.fonte}`);
    (lista ?? semPolo).push(n);
  }
  const raioDe = (k) => 0.05 + 0.028 * Math.ceil((Math.sqrt(1 + (4 * k) / 3) - 1) / 2) * 1.6;
  const pos = polos.map((p, i) => {
    const a = (i * 2 * Math.PI) / Math.max(1, polos.length);
    return { id: p.id, x: 0.55 * Math.cos(a), y: 0.55 * Math.sin(a), r: raioDe(filhos.get(p.id).length) };
  });
  for (let passo = 0; passo < 300; passo++) {
    for (let i = 0; i < pos.length; i++) {
      let fx = -pos[i].x * 0.02, fy = -pos[i].y * 0.02;
      for (let j = 0; j < pos.length; j++) {
        if (i === j) continue;
        const dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y;
        const d = Math.hypot(dx, dy) || 1e-6;
        const min = pos[i].r + pos[j].r + 0.08;
        if (d < min) { fx += (dx / d) * (min - d) * 0.5; fy += (dy / d) * (min - d) * 0.5; }
        else { fx += (dx / d) * 0.0008 / d; fy += (dy / d) * 0.0008 / d; }
      }
      pos[i].x += fx; pos[i].y += fy;
    }
  }
  let maior = 1e-6;
  for (const p of pos) maior = Math.max(maior, Math.hypot(p.x, p.y) + p.r);
  const k = maior > 0.98 ? 0.98 / maior : 1;
  const itens = new Map(), hexes = new Map(), rotulos = [];
  for (const p of pos) {
    const cx = p.x * k, cy = p.y * k;
    hexes.set(p.id, { x: cx, y: cy, z: 0, tam: 1.5 });
    const lista = filhos.get(p.id);
    const aneisDoPolo = Math.ceil((Math.sqrt(1 + (4 * lista.length) / 3) - 1) / 2);
    if (lista.length) rotulos.push({ texto: `${graph.nodes.find((n) => n.id === p.id)?.rotulo ?? p.id} · ${lista.length}`, x: cx, y: cy + (0.035 + 0.028 * aneisDoPolo) * k + 0.035, z: 0, cor: "#cfeee6", estilo: "texto" });
    let i = 0, anel = 1;
    while (i < lista.length) {
      const nesse = 6 * anel;
      const r = (0.035 + 0.028 * anel) * k;
      for (let j = 0; j < nesse && i < lista.length; j++, i++) {
        const a = (j / nesse) * 2 * Math.PI + anel * 0.4;
        const n = lista[i];
        const q = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a), z: 0 };
        if (ehHex(n)) hexes.set(n.id, { ...q, tam: 0.8 });
        else itens.set(n.id, { ...q, ang: 0, sx: 1, sy: 1 });
      }
      anel++;
    }
  }
  semPolo.forEach((n, i) => {
    const p = girassol(semPolo.length, 0.15)[i];
    if (ehHex(n)) hexes.set(n.id, { x: p.x, y: p.y, z: 0, tam: 0.8 });
    else itens.set(n.id, ponto(p.x, p.y));
  });
  return { itens, hexes, rotulos, setores: [], linhas: [] };
}

// Anéis: cada tipo uma órbita inclinada (os grandes por fora); os hexágonos numa órbita larga quase no plano.
export function poseAneis(graph) {
  const { hex, grupos } = separar(graph);
  const ordem = [...grupos.entries()].sort((a, b) => a[1].length - b[1].length || a[0].localeCompare(b[0]));
  const itens = new Map(), rotulos = [];
  ordem.forEach(([tipo, lista], gi) => {
    const raio = 0.3 + 0.62 * ((gi + 1) / ordem.length);
    const incl = 0.5 * Math.sin(gi * 1.7) + 0.15;
    const giro = gi * 0.9;
    const voltas = Math.max(1, Math.ceil(lista.length / 80));
    const pontoNoAnel = (a, r) => {
      const px = r * Math.cos(a), pz = r * Math.sin(a);
      const y1 = pz * Math.sin(incl), z1 = pz * Math.cos(incl);
      return { x: px * Math.cos(giro) - z1 * Math.sin(giro), y: y1, z: px * Math.sin(giro) + z1 * Math.cos(giro) };
    };
    lista.forEach((n, i) => {
      const v = i % voltas;
      const a = (Math.floor(i / voltas) / Math.ceil(lista.length / voltas)) * 2 * Math.PI;
      itens.set(n.id, { ...pontoNoAnel(a, raio + v * 0.022), ang: 0, sx: 1, sy: 1 });
    });
    rotulos.push({ texto: rotuloTipo(tipo, lista.length), ...pontoNoAnel(Math.PI * 0.25, raio + 0.04), cor: corDoTipo(tipo), estilo: "pilula" });
  });
  const hexes = new Map();
  hex.forEach((n, i) => {
    const a = (i * 2 * Math.PI) / Math.max(1, hex.length);
    hexes.set(n.id, { x: 1.08 * Math.cos(a), y: 0.06 * Math.sin(a * 3), z: 1.08 * Math.sin(a), tam: n.tipo === "fonte" ? 1.2 : 0.9 });
  });
  return { itens, hexes, rotulos, setores: [], linhas: [] };
}

export const POSES = Object.freeze({ disco: poseDisco, forca: poseForca, aneis: poseAneis });

// Transição entre poses: suave na entrada e na saída.
export const suavizar = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
export function misturar(a, b, t) {
  const k = suavizar(t);
  const m = (x, y) => x + (y - x) * k;
  let da = (b.ang ?? 0) - (a.ang ?? 0);
  da = Math.atan2(Math.sin(da), Math.cos(da));
  return { x: m(a.x, b.x), y: m(a.y, b.y), z: m(a.z ?? 0, b.z ?? 0), ang: (a.ang ?? 0) + da * k, sx: m(a.sx ?? 1, b.sx ?? 1), sy: m(a.sy ?? 1, b.sy ?? 1) };
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

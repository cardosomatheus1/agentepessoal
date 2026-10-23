// node --test tests/constelacao.test.mjs — a Constelação (23/10): as três visões põem todo item da Pasta na tela, dentro
// do disco, sem sorteio; os setores do disco não se sobrepõem; o painel só mostra ligações gravadas.
import test from "node:test";
import assert from "node:assert/strict";
import { rmSync } from "node:fs";
import { loadSecondBrain } from "../lib/second-brain.mjs";
import { buildBrainGraph } from "../lib/brain-graph.mjs";
import { layoutAneis, layoutDisco, layoutForca, ligacoesDoItem, maisPerto, projetar, RAIO_ORBITA } from "../lib/constelacao.mjs";
import { criarFixture } from "./fixture-brain.mjs";

const NOW = new Date("2026-10-20T12:00:00Z");
async function grafo() {
  const root = criarFixture();
  try { return buildBrainGraph(await loadSecondBrain({ root, now: NOW })); } finally { rmSync(root, { recursive: true, force: true }); }
}
const finito = (p) => Number.isFinite(p.x) && Number.isFinite(p.y);

// Uma Pasta grande sintética (do tamanho da dele: ~900 itens), para medir sobreposição e tempo.
function grande() {
  const tipos = ["decisao", "pendencia", "assunto", "nota", "documento", "fato"];
  const nodes = ["decisoes", "pendencias", "notas"].map((f) => ({ id: `fonte:${f}`, tipo: "fonte", rotulo: f, fonte: f, registro: null }));
  const edges = [];
  for (let i = 0; i < 900; i++) {
    const tipo = tipos[i % tipos.length];
    nodes.push({ id: `${tipo}:${i}`, tipo, rotulo: `item ${i}`, fonte: ["decisoes", "pendencias", "notas"][i % 3], registro: { fonte: "x" } });
    edges.push({ id: `p${i}`, de: `${tipo}:${i}`, para: `fonte:${["decisoes", "pendencias", "notas"][i % 3]}`, relacao: "proveniencia", classe: "proveniencia" });
    if (i > 10 && i % 4 === 0) edges.push({ id: `w${i}`, de: `${tipo}:${i}`, para: `${tipos[(i - 7) % tipos.length]}:${i - 7}`, relacao: "wiki", classe: "comprovada" });
  }
  return { nodes, edges };
}

test("disco: todo nó tem posição dentro do disco; fontes na órbita; setores em ordem e sem sobreposição", async () => {
  const g = await grafo();
  const { posicoes, setores, orbita } = layoutDisco(g);
  assert.equal(posicoes.size, g.nodes.length);
  for (const [id, p] of posicoes) assert.ok(finito(p) && Math.hypot(p.x, p.y) <= RAIO_ORBITA + 1e-9, id);
  assert.equal(orbita.length, g.nodes.filter((n) => n.tipo === "fonte").length);
  for (const o of orbita) assert.ok(Math.abs(Math.hypot(o.x, o.y) - RAIO_ORBITA) < 1e-9);
  for (let i = 1; i < setores.length; i++) assert.ok(setores[i].inicio >= setores[i - 1].fim, "setores não se sobrepõem");
  assert.ok(setores.at(-1).fim <= -Math.PI / 2 + 2 * Math.PI + 1e-9, "cabem numa volta");
  assert.deepEqual(layoutDisco(g).posicoes, posicoes, "mesma Pasta, mesmo desenho");
});

test("disco numa Pasta do tamanho real: os pontos não se amontoam", () => {
  const { posicoes } = layoutDisco(grande());
  const pts = [...posicoes.values()];
  let perto = 0;
  for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) if (Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y) < 0.004) perto++;
  assert.ok(perto < pts.length * 0.01, `pares colados: ${perto}`);
});

test("força: posições finitas, no disco, determinísticas e ligados mais perto que a média", () => {
  const g = grande();
  const t0 = Date.now();
  const { posicoes } = layoutForca(g);
  assert.ok(Date.now() - t0 < 8000, "calcula em tempo de tela");
  assert.equal(posicoes.size, g.nodes.length);
  for (const p of posicoes.values()) assert.ok(finito(p) && Math.hypot(p.x, p.y) <= 0.95 + 1e-9);
  assert.deepEqual(layoutForca(g).posicoes, posicoes);
  const d = (a, b) => Math.hypot(posicoes.get(a).x - posicoes.get(b).x, posicoes.get(a).y - posicoes.get(b).y);
  const ligadas = g.edges.filter((e) => e.relacao === "proveniencia");
  const mediaLigada = ligadas.reduce((s, e) => s + d(e.de, e.para), 0) / ligadas.length;
  const ids = g.nodes.map((n) => n.id);
  let soma = 0;
  for (let i = 0; i < 2000; i++) soma += d(ids[(i * 37) % ids.length], ids[(i * 101 + 5) % ids.length]);
  assert.ok(mediaLigada < soma / 2000, `cada item perto da sua fonte (${mediaLigada.toFixed(3)} < ${(soma / 2000).toFixed(3)})`);
});

test("anéis e projeção: todo nó tem ponto 3D; girar meia volta espelha; perto da câmera fica maior", async () => {
  const g = await grafo();
  const { pontos } = layoutAneis(g);
  assert.equal(pontos.size, g.nodes.length);
  for (const p of pontos.values()) assert.ok(Number.isFinite(p.z) && Math.hypot(p.x, p.y, p.z) < 1.2);
  const a = projetar({ x: 0.5, y: 0, z: 0 }, 0, 0), b = projetar({ x: 0.5, y: 0, z: 0 }, Math.PI, 0);
  assert.ok(Math.abs(a.x + b.x) < 1e-9);
  assert.ok(projetar({ x: 0, y: 0, z: -0.5 }, 0, 0).escala > projetar({ x: 0, y: 0, z: 0.5 }, 0, 0).escala);
});

test("painel: só ligações gravadas, nos dois sentidos; clique acha o ponto mais perto dentro do raio", async () => {
  const g = await grafo();
  const com = g.edges.find((e) => e.relacao !== "proveniencia");
  const { aponta } = ligacoesDoItem(g, com.de);
  const { referenciado } = ligacoesDoItem(g, com.para);
  assert.ok(aponta.some((l) => l.no.id === com.para) && referenciado.some((l) => l.no.id === com.de));
  assert.ok(!aponta.concat(referenciado).some((l) => l.relacao === "proveniencia"));
  const tela = new Map([["a", { x: 10, y: 10 }], ["b", { x: 30, y: 10 }]]);
  assert.equal(maisPerto(tela, 12, 11), "a");
  assert.equal(maisPerto(tela, 100, 100), null);
});

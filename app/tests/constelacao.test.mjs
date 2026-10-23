// node --test tests/constelacao.test.mjs — a Constelação (23/10): as três poses põem todo item da Pasta na cena, sem
// sorteio; no disco o girassol fica no centro, os traços nas faixas, os arquivos na órbita; a transição vai e volta;
// o painel só mostra ligações gravadas.
import test from "node:test";
import assert from "node:assert/strict";
import { rmSync } from "node:fs";
import { loadSecondBrain } from "../lib/second-brain.mjs";
import { buildBrainGraph } from "../lib/brain-graph.mjs";
import { NUCLEO, POSES, RAIO_ORBITA, ehHex, girassol, ligacoesDoItem, maisPerto, misturar, poseDisco, poseForca } from "../lib/constelacao.mjs";
import { criarFixture } from "./fixture-brain.mjs";

const NOW = new Date("2026-10-20T12:00:00Z");
async function grafo() {
  const root = criarFixture();
  try { return buildBrainGraph(await loadSecondBrain({ root, now: NOW })); } finally { rmSync(root, { recursive: true, force: true }); }
}
const finita = (p) => [p.x, p.y, p.z].every(Number.isFinite);

// Uma Pasta sintética do tamanho da dele (~900 itens).
function grande() {
  const tipos = ["decisao", "pendencia", "assunto", "referencia", "fato", "nota", "contexto"];
  const fontes = ["decisoes", "pendencias", "assuntos", "notas", "contexto"];
  const nodes = fontes.map((f) => ({ id: `fonte:${f}`, tipo: "fonte", rotulo: f, fonte: f, registro: null }));
  const edges = [];
  for (let i = 0; i < 900; i++) {
    const tipo = tipos[i % tipos.length], fonte = fontes[i % fontes.length];
    nodes.push({ id: `${tipo}:${i}`, tipo, rotulo: `item ${i}`, fonte, registro: { fonte } });
    edges.push({ id: `p${i}`, de: `${tipo}:${i}`, para: `fonte:${fonte}`, relacao: "proveniencia", classe: "proveniencia" });
  }
  return { nodes, edges };
}

test("toda pose cobre todo nó uma vez (item ou hexágono), com números finitos, e é determinística", async () => {
  for (const g of [await grafo(), grande()]) {
    for (const [modo, f] of Object.entries(POSES)) {
      const c = f(g);
      for (const n of g.nodes) {
        const em = (ehHex(n) ? c.hexes : c.itens).get(n.id);
        assert.ok(em && finita(em), `${modo}: ${n.id}`);
        assert.ok(!(ehHex(n) ? c.itens : c.hexes).has(n.id), `${modo}: ${n.id} em um lugar só`);
      }
      assert.equal(c.itens.size + c.hexes.size, g.nodes.length);
      assert.deepEqual(f(g).itens, c.itens, `${modo} determinística`);
    }
  }
});

test("disco: girassol no centro, traços nas faixas, arquivos na órbita, setores sem sobreposição", () => {
  const g = grande();
  const c = poseDisco(g);
  for (const n of g.nodes) {
    if (ehHex(n)) { assert.ok(Math.abs(Math.hypot(c.hexes.get(n.id).x, c.hexes.get(n.id).y) - RAIO_ORBITA) < 1e-9); continue; }
    const p = c.itens.get(n.id), r = Math.hypot(p.x, p.y);
    if (n.tipo === NUCLEO) assert.ok(r <= 0.3 + 1e-9 && p.sx === p.sy, "ponto do girassol");
    else assert.ok(r >= 0.37 && r <= 0.72 && p.sx > p.sy, `traço na faixa: ${n.id} r=${r}`);
  }
  for (let i = 1; i < c.setores.length; i++) assert.ok(c.setores[i].inicio >= c.setores[i - 1].fim);
  const pts = [...c.itens.values()];
  let colados = 0;
  for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) if (Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y) < 0.003) colados++;
  assert.ok(colados < pts.length * 0.01, `pontos colados: ${colados}`);
  const sol = girassol(100, 0.3);
  assert.ok(sol.every((p) => Math.hypot(p.x, p.y) <= 0.3 + 1e-9));
});

test("força: cada registro perto da sua fonte, polos sem se encostar, tudo dentro da tela", () => {
  const g = grande();
  const c = poseForca(g);
  for (const n of g.nodes.filter((x) => !ehHex(x))) {
    const p = c.itens.get(n.id), polo = c.hexes.get(`fonte:${n.fonte}`);
    assert.ok(Math.hypot(p.x - polo.x, p.y - polo.y) < 0.6, `${n.id} perto do polo`);
  }
  const polos = g.nodes.filter((n) => n.tipo === "fonte").map((n) => c.hexes.get(n.id));
  for (let i = 0; i < polos.length; i++) for (let j = i + 1; j < polos.length; j++) assert.ok(Math.hypot(polos[i].x - polos[j].x, polos[i].y - polos[j].y) > 0.1);
  for (const p of [...c.itens.values(), ...c.hexes.values()]) assert.ok(Math.hypot(p.x, p.y) <= 1.05);
});

test("transição: começa na pose de saída, termina na de chegada, gira pelo lado curto", () => {
  const a = { x: 0, y: 0, z: 0, ang: 3.0, sx: 4, sy: 0.5 }, b = { x: 1, y: -1, z: 0.5, ang: -3.0, sx: 1, sy: 1 };
  assert.deepEqual(misturar(a, b, 0), a);
  const fim = misturar(a, b, 1);
  assert.ok(Math.abs(fim.x - 1) < 1e-12 && Math.abs(fim.z - 0.5) < 1e-12 && Math.abs(Math.cos(fim.ang) - Math.cos(-3)) < 1e-9);
  const meio = misturar(a, b, 0.5);
  assert.ok(Math.abs(meio.ang - Math.PI) < 0.01 || Math.abs(meio.ang + Math.PI) < 0.01, `pelo lado curto: ${meio.ang}`);
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

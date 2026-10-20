// node --test tests/brain-graph.test.mjs — grafo completo: todos os registros, só arestas explícitas, filtros e grupos.
import test from "node:test";
import assert from "node:assert/strict";
import { rmSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { loadSecondBrain } from "../lib/second-brain.mjs";
import { filterConnections } from "../lib/connection-map.mjs";
import { RELACOES, TIPOS, buildBrainGraph, buildSigmaGraph, filterBrainGraph, layoutBrainGraph, neighborsOf } from "../lib/brain-graph.mjs";
import { criarFixture } from "./fixture-brain.mjs";

const NOW = new Date("2026-10-18T12:00:00Z");
async function carga(mutar) {
  const root = criarFixture();
  try { if (mutar) mutar(root); return await loadSecondBrain({ root, now: NOW }); } finally { rmSync(root, { recursive: true, force: true }); }
}
const semProveniencia = new Set(Object.keys(RELACOES).filter((r) => r !== "proveniencia"));

test("reproduz o defeito antigo: o mapa de ligações escondia registros sem ligação; o novo mostra todos", async () => {
  const b = await carga();
  const antigo = filterConnections(b.connections);
  assert.ok(!antigo.nodes.some((n) => n.id === "fio:c3"), "mapa antigo: fio sem ligação some");
  assert.ok(!antigo.nodes.some((n) => n.id.startsWith("decisao:") || n.id.startsWith("rotina:")), "mapa antigo: só fios");
  const g = buildBrainGraph(b);
  const registros = b.decisions.length + b.threads.length + b.profile.length + b.contexts.length + b.documents.length + b.routines.length + b.projects.length;
  assert.equal(g.nodes.filter((n) => !["fonte", "referencia"].includes(n.tipo)).length, registros, "todo registro é nó");
  assert.equal(g.nodes.filter((n) => n.tipo === "fonte").length, b.sources.length, "toda fonte é nó, inclusive as sem contrato");
  assert.ok(g.nodes.some((n) => n.id === "fonte:reunioes") && g.nodes.some((n) => n.id === "fonte:daily"));
  const v = filterBrainGraph(g, { relacoes: semProveniencia });
  assert.ok(v.nodes.some((n) => n.id === "fio:c3"), "isolado continua visível mesmo sem arestas no recorte");
  assert.ok(!v.edges.some((e) => e.de === "fio:c3" || e.para === "fio:c3"));
});

test("só arestas de metadado explícito com destino válido; palavra parecida não liga", async () => {
  const b = await carga((root) => {
    const f = path.join(root, "memoria/decisoes/matheus.json");
    const d = JSON.parse(readFileSync(f, "utf8"));
    d.decisoes.push({ id: 8, tema: "teste.y", tipo: "decisao", valor: "Substitui uma que não existe", estado: "ativa", substitui: 99 });
    writeFileSync(f, JSON.stringify(d));
  });
  const g = buildBrainGraph(b);
  const sem = g.edges.filter((e) => e.relacao !== "proveniencia").map((e) => [e.de, e.para, e.relacao, e.classe]);
  assert.deepEqual(sem.filter(([, , r]) => r !== "fonte_citada"), [
    ["decisao:4", "decisao:3", "substitui", "comprovada"],
    ["fio:a1", "referencia:Depende do catálogo sintético", "ligacao_texto", "referencia"],
    ["fio:b2", "fio:a1", "ligacao_fio", "comprovada"],
    ["documento:requisitos", "documento:setup", "cita_documento", "comprovada"],
  ]);
  assert.ok(!g.edges.some((e) => e.para === "decisao:99"), "destino inexistente não vira aresta");
  assert.ok(!g.edges.some((e) => (e.de === "fio:a1" && e.para === "fio:c3") || (e.de === "fio:c3" && e.para === "fio:a1")), "'Lançamento' nos dois títulos não é ligação");
  for (const e of g.edges) {
    assert.ok(g.nodes.some((n) => n.id === e.de) && g.nodes.some((n) => n.id === e.para));
    assert.ok(e.evidencia.fonte && e.evidencia.campo, JSON.stringify(e));
  }
  const ref = g.nodes.find((n) => n.id === "referencia:Depende do catálogo sintético");
  assert.equal(ref.tipo, "referencia");
  assert.equal(ref.registro, null, "referência textual não é registro");
});

test("filtros por tipo, fonte e relação; busca sem vizinhos não puxa o grafo inteiro pela fonte", async () => {
  const g = buildBrainGraph(await carga());
  const soDecisoes = filterBrainGraph(g, { tipos: new Set(["decisao"]) });
  assert.ok(soDecisoes.nodes.every((n) => n.tipo === "decisao"));
  assert.equal(soDecisoes.nodes.length, 5);
  const fonteFios = filterBrainGraph(g, { fontes: new Set(["fios"]) });
  assert.ok(fonteFios.nodes.every((n) => n.fonte === "fios"));
  const busca = filterBrainGraph(g, { termo: "catalogo" });
  assert.deepEqual([...busca.matches].sort(), ["fio:b2", "referencia:Depende do catálogo sintético"], "sem acento também encontra");
  assert.equal(busca.contexto.size, 0);
  assert.deepEqual(busca.nodes.map((n) => n.id).sort(), [...busca.matches].sort(), "sem vizinhos: só o que casou");
  const comVizinhos = filterBrainGraph(g, { termo: "catalogo", vizinhos: true, relacoes: semProveniencia });
  assert.deepEqual([...comVizinhos.contexto].sort(), ["fio:a1"], "vizinho direto entra como contexto, sem passar pela fonte");
  const comFonte = filterBrainGraph(g, { termo: "catalogo", vizinhos: true });
  assert.ok(comFonte.contexto.has("fonte:fios") && !comFonte.nodes.some((n) => n.tipo === "decisao"), "um salto só: a fonte entra, os irmãos dela não");
  const nenhum = filterBrainGraph(g, { termo: "nao-existe-xyz" });
  assert.deepEqual([nenhum.nodes.length, nenhum.edges.length], [0, 0]);
});

test("agrupamento é só posição: não cria aresta, é determinístico e finito", async () => {
  const g = buildBrainGraph(await carga());
  const arestas = g.edges.length;
  for (const modo of ["fonte", "meta", "tipo"]) {
    const a = layoutBrainGraph(g, modo);
    const b2 = layoutBrainGraph(structuredClone(g), modo);
    assert.deepEqual([...a.positions], [...b2.positions]);
    assert.equal(a.positions.size, g.nodes.length);
    const pts = [...a.positions.values()];
    assert.ok(pts.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y)));
    assert.equal(new Set(pts.map((p) => `${p.x.toFixed(3)},${p.y.toFixed(3)}`)).size, pts.length, "sem nós sobrepostos");
    assert.equal(buildSigmaGraph(g, a.positions).size, arestas, `agrupar por ${modo} não muda as arestas`);
  }
  const meta = layoutBrainGraph(g, "meta");
  assert.ok(meta.centros.has("tema: teste") && meta.centros.has("estado: aberto"), "grupo vem de campo explícito (tema, estado)");
});

test("grafo do renderer tem exatamente o recorte e formas/cores por tipo", async () => {
  const g = buildBrainGraph(await carga());
  const v = filterBrainGraph(g, { relacoes: semProveniencia });
  const sg = buildSigmaGraph(v, layoutBrainGraph(g).positions);
  assert.equal(sg.order, v.nodes.length);
  assert.equal(sg.size, v.edges.length);
  for (const n of v.nodes) {
    assert.equal(sg.getNodeAttribute(n.id, "shape"), TIPOS[n.tipo].forma);
    assert.equal(sg.getNodeAttribute(n.id, "color"), TIPOS[n.tipo].cor);
  }
  assert.ok(new Set(v.nodes.map((n) => TIPOS[n.tipo].forma)).size >= 3, "tipos distintos também na forma");
  assert.deepEqual(neighborsOf(v, "fio:b2").map((x) => [x.outro, x.direcao]), [["fio:a1", "saida"]]);
});

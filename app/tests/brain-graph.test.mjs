// node --test tests/brain-graph.test.mjs — grafo da Pasta: todos os itens, só ligações gravadas, filtros (área) e grupos.
import test from "node:test";
import assert from "node:assert/strict";
import { rmSync } from "node:fs";
import { loadSecondBrain } from "../lib/second-brain.mjs";
import { filterConnections } from "../lib/connection-map.mjs";
import { RELACOES, TIPOS, buildBrainGraph, buildSigmaGraph, filterBrainGraph, layoutBrainGraph, neighborsOf } from "../lib/brain-graph.mjs";
import { criarFixture, naPasta, frontmatter } from "./fixture-brain.mjs";

const NOW = new Date("2026-10-20T12:00:00Z");
async function carga(mutar) {
  const root = criarFixture();
  try { if (mutar) mutar(root); return await loadSecondBrain({ root, now: NOW }); } finally { rmSync(root, { recursive: true, force: true }); }
}
const semProveniencia = new Set(Object.keys(RELACOES).filter((r) => r !== "proveniencia"));

test("todo item da Pasta é nó (mesmo sem ligação); o mapa simples de conexões só tem as ligações", async () => {
  const b = await carga();
  const simples = filterConnections(b.connections);
  assert.ok(!simples.nodes.some((n) => n.id === "pendencia:c3"), "mapa simples: item sem ligação some");
  const g = buildBrainGraph(b);
  const itens = b.decisions.length + b.threads.length + b.subjects.length + b.profile.length + b.contexts.length + b.meetings.length + b.daily.length + b.documents.length + b.projects.length;
  assert.equal(g.nodes.filter((n) => !["fonte", "referencia"].includes(n.tipo)).length, itens, "todo item é nó");
  assert.equal(g.nodes.filter((n) => n.tipo === "fonte").length, b.sources.length);
  const v = filterBrainGraph(g, { relacoes: semProveniencia });
  assert.ok(v.nodes.some((n) => n.id === "pendencia:c3"), "isolado continua visível mesmo sem arestas no recorte");
  assert.ok(!v.edges.some((e) => e.de === "pendencia:c3" || e.para === "pendencia:c3"));
  assert.ok(g.nodes.filter((n) => n.registro && n.tipo !== "fonte").every((n) => n.area), "todo item tem área");
});

test("só arestas de ligação gravada com destino válido (liga, [[link]], substitui); palavra parecida não liga", async () => {
  const b = await carga((root) => naPasta(root, "Decisoes/0008-y.md", frontmatter({ id: 8, tema: "teste.y", valor: "Substitui uma que não existe", estado: "ativa", substitui: 99 }) + "# y\n"));
  const g = buildBrainGraph(b);
  const sem = g.edges.filter((e) => !["proveniencia", "fonte_citada"].includes(e.relacao)).map((e) => [e.de, e.para, e.relacao, e.classe]);
  assert.deepEqual(sem, [
    ["decisao:4", "decisao:3", "substitui", "comprovada"],
    ["decisao:1", "pendencia:a1", "liga", "comprovada"],
    ["pendencia:a1", "assunto:s1", "liga", "comprovada"],
    ["pendencia:a1", "referencia:Depende do catálogo sintético", "ligacao_texto", "referencia"],
    ["pendencia:b2", "pendencia:a1", "liga", "comprovada"],
    ["assunto:s1", "decisao:1", "liga", "comprovada"],
    ["contexto:organizacao", "decisao:1", "wiki", "comprovada"],
    ["reuniao:2026-10-15-reuniao-raiz", "pendencia:a1", "wiki", "comprovada"],
    ["nota:2026-10-19", "assunto:s1", "wiki", "comprovada"],
    ["nota:2026-10-18", "decisao:4", "wiki", "comprovada"],
    ["documento:auditoria-2026-10-20", "contexto:organizacao", "wiki", "comprovada"],
    ["documento:auditoria-2026-10-20", "referencia:Documentos/inexistente", "link_sem_destino", "referencia"],
  ]);
  assert.ok(!g.edges.some((e) => e.para === "decisao:99"), "destino inexistente não vira aresta");
  assert.ok(!g.edges.some((e) => [e.de, e.para].includes("pendencia:c3") && e.relacao !== "proveniencia"), "'Lançamento' nos dois títulos não é ligação");
  for (const e of g.edges) {
    assert.ok(g.nodes.some((n) => n.id === e.de) && g.nodes.some((n) => n.id === e.para));
    assert.ok(e.evidencia.fonte && e.evidencia.campo, JSON.stringify(e));
  }
  const ref = g.nodes.find((n) => n.id === "referencia:Depende do catálogo sintético");
  assert.equal(ref.tipo, "referencia");
  assert.equal(ref.registro, null, "referência textual não é registro");
});

test("filtros por tipo, fonte, área e relação; busca sem vizinhos não puxa o grafo inteiro pela fonte", async () => {
  const g = buildBrainGraph(await carga());
  const soDecisoes = filterBrainGraph(g, { tipos: new Set(["decisao"]) });
  assert.ok(soDecisoes.nodes.every((n) => n.tipo === "decisao"));
  assert.equal(soDecisoes.nodes.length, 5);
  const raiz = filterBrainGraph(g, { areas: new Set(["Raiz"]) });
  const itensRaiz = raiz.nodes.filter((n) => n.registro && n.tipo !== "fonte").map((n) => n.id).sort();
  assert.deepEqual(itensRaiz, ["assunto:s1", "decisao:1", "decisao:3", "decisao:4", "pendencia:a1", "pendencia:c3", "reuniao:2026-10-15-reuniao-raiz"]);
  assert.ok(!raiz.edges.some((e) => e.de === "pendencia:b2"), "b2 é Orbyte: a ligação dela sai do recorte da Raiz");
  const fontePend = filterBrainGraph(g, { fontes: new Set(["pendencias"]) });
  assert.ok(fontePend.nodes.every((n) => n.fonte === "pendencias"));
  const busca = filterBrainGraph(g, { termo: "catalogo" });
  assert.deepEqual([...busca.matches].sort(), ["pendencia:b2", "referencia:Depende do catálogo sintético"], "sem acento também encontra");
  assert.equal(busca.contexto.size, 0);
  const comVizinhos = filterBrainGraph(g, { termo: "catalogo", vizinhos: true, relacoes: semProveniencia });
  assert.deepEqual([...comVizinhos.contexto].sort(), ["pendencia:a1"], "vizinho direto entra como contexto, sem passar pela fonte");
  const nenhum = filterBrainGraph(g, { termo: "nao-existe-xyz" });
  assert.deepEqual([nenhum.nodes.length, nenhum.edges.length], [0, 0]);
});

test("agrupamento é só posição: não cria aresta, é determinístico e finito", async () => {
  const g = buildBrainGraph(await carga());
  const arestas = g.edges.length;
  for (const modo of ["fonte", "area", "meta", "tipo"]) {
    const a = layoutBrainGraph(g, modo);
    const b2 = layoutBrainGraph(structuredClone(g), modo);
    assert.deepEqual([...a.positions], [...b2.positions]);
    assert.equal(a.positions.size, g.nodes.length);
    const pts = [...a.positions.values()];
    assert.ok(pts.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y)));
    assert.equal(new Set(pts.map((p) => `${p.x.toFixed(3)},${p.y.toFixed(3)}`)).size, pts.length, "sem nós sobrepostos");
    assert.equal(buildSigmaGraph(g, a.positions).size, arestas, `agrupar por ${modo} não muda as arestas`);
  }
  assert.ok(layoutBrainGraph(g, "meta").centros.has("tema: teste") && layoutBrainGraph(g, "meta").centros.has("estado: aberto"));
  assert.ok(layoutBrainGraph(g, "area").centros.has("área: Raiz"), "grupo por área vem do campo area");
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
  assert.ok(new Set(v.nodes.map((n) => TIPOS[n.tipo].forma)).size >= 3);
  assert.deepEqual(neighborsOf(v, "pendencia:b2").map((x) => [x.outro, x.direcao]), [["pendencia:a1", "saida"]]);
});

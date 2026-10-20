import test from 'node:test';
import assert from 'node:assert/strict';
import { buildConnectionGraph, filterConnections, forceLayoutConnections, layoutConnections } from '../lib/connection-map.mjs';
const node = (id, rotulo = id, tipo = 'fio') => ({ id, rotulo, tipo });
const edge = (de, para) => ({ de, para, rotulo: null, evidencia: { fonte: 'fios', fioId: de, em: null } });
const graph = { nodes: [node('a', 'Planejamento'), node('b', 'Reunião'), node('c', 'Contrato', 'texto'), node('d', 'Reunião sem vínculo')], edges: [edge('a', 'b'), edge('b', 'c')] };
test('shows only explicit edges and their endpoints; no same-label inference', () => {
  const result = filterConnections(graph);
  assert.deepEqual(result.nodes.map(n => n.id), ['a', 'b', 'c']);
  assert.deepEqual(result.edges, graph.edges);
  assert.ok(!result.nodes.some(n => n.id === 'd'));
});
test('accent-insensitive search preserves only immediate recorded neighbors', () => {
  const result = filterConnections(graph, 'planej');
  assert.deepEqual(result.nodes.map(n => n.id), ['a', 'b']);
  assert.deepEqual(result.edges, [graph.edges[0]]);
  assert.deepEqual([...filterConnections(graph, 'REUNIAO').matches], ['b', 'd']);
});
test('type filter preserves adjacent context, not a fabricated link', () => {
  const result = filterConnections(graph, '', 'texto');
  assert.deepEqual([...result.matches], ['c']);
  assert.deepEqual(result.nodes.map(n => n.id), ['b', 'c']);
  assert.deepEqual(result.edges, [graph.edges[1]]);
});
test('empty/no matches, dangling edges, duplicate and self-links are safe', () => {
  assert.deepEqual(filterConnections(graph, 'not found').nodes, []);
  assert.deepEqual(layoutConnections({ nodes: [], edges: [] }).nodes, []);
  const result = filterConnections({ nodes: [node('a')], edges: [edge('a', 'a'), edge('a', 'a'), edge('a', 'missing')] });
  assert.equal(result.edges.length, 2);
  assert.equal(layoutConnections(result).nodes.length, 1);
});
test('layout is deterministic, finite, separated, bounded and never mutates data', () => {
  const input = structuredClone(graph);
  const first = layoutConnections(graph);
  assert.deepEqual(first, layoutConnections(graph));
  assert.deepEqual(graph, input);
  assert.equal(new Set(first.nodes.map(n => `${n.x},${n.y}`)).size, graph.nodes.length);
  for (const n of first.nodes) {
    assert.ok(Number.isFinite(n.x) && Number.isFinite(n.y));
    assert.ok(n.x >= 100 && n.x <= first.width - 100 && n.y >= 100 && n.y <= first.height - 100);
  }
});
test('large synthetic graph remains finite and preserves every explicit edge', () => {
  const large = { nodes: Array.from({ length: 500 }, (_, i) => node(String(i))), edges: Array.from({ length: 499 }, (_, i) => edge('0', String(i + 1))) };
  const result = filterConnections(large);
  assert.equal(result.edges.length, 499);
  const layout = layoutConnections(result);
  assert.equal(layout.nodes.length, 500);
  assert.ok(layout.nodes.every(n => Number.isFinite(n.x) && Number.isFinite(n.y)));
});
test('node cards never overlap in common radial groups or between components', () => {
  for (const count of [2, 3, 5, 9, 20, 60]) {
    const graph = { nodes: Array.from({ length: count }, (_, i) => node(String(i))), edges: Array.from({ length: count - 1 }, (_, i) => edge('0', String(i + 1))) };
    graph.nodes.push(node('separate'));
    const { nodes } = layoutConnections(graph);
    for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
      // Actual SVG cards are 176 x 72. Keep at least 12 units between boxes.
      assert.ok(Math.abs(nodes[i].x - nodes[j].x) >= 188 || Math.abs(nodes[i].y - nodes[j].y) >= 84, `${count}: ${i}/${j}`);
    }
  }
});
const multi = { nodes: [node('a', 'Planejamento'), node('b', 'Reunião'), node('c', 'Contrato', 'texto'), node('x'), node('y'), node('z', 'Isolado')], edges: [edge('a', 'b'), edge('b', 'c'), edge('a', 'b'), edge('a', 'a'), edge('x', 'y'), edge('c', 'missing')] };
test('force layout is deterministic, finite, distinct and never mutates data', () => {
  for (const input of [graph, multi, filterConnections(multi)]) {
    const copy = structuredClone(input);
    const first = forceLayoutConnections(input);
    assert.deepEqual(first, forceLayoutConnections(structuredClone(input)));
    assert.deepEqual(input, copy);
    assert.deepEqual(first.nodes.map(n => n.id), input.nodes.map(n => n.id));
    assert.equal(new Set(first.nodes.map(n => `${n.x},${n.y}`)).size, input.nodes.length);
    assert.ok(first.nodes.every(n => Number.isFinite(n.x) && Number.isFinite(n.y)));
    // Physics actually ran: positions differ from the radial seed.
    const seed = layoutConnections(input);
    assert.ok(first.nodes.some((n, i) => n.x !== seed.nodes[i].x || n.y !== seed.nodes[i].y));
  }
  assert.deepEqual(forceLayoutConnections({ nodes: [], edges: [] }).nodes, []);
  assert.ok(forceLayoutConnections({ nodes: [node('solo')], edges: [] }).nodes.every(n => Number.isFinite(n.x) && Number.isFinite(n.y)));
});
test('force layout keeps connected nodes closer than unrelated components', () => {
  const { positions } = forceLayoutConnections(filterConnections(multi));
  const d = (p, q) => Math.hypot(positions.get(p).x - positions.get(q).x, positions.get(p).y - positions.get(q).y);
  assert.ok(d('x', 'y') < d('x', 'a') && d('a', 'b') < d('a', 'y'));
});
test('renderer graph has exactly the recorded edges: duplicates and self-links kept, none invented', () => {
  const visible = filterConnections(multi);
  const { positions } = forceLayoutConnections(visible);
  const g = buildConnectionGraph(visible, positions);
  assert.equal(g.order, visible.nodes.length);
  assert.equal(g.size, visible.edges.length);
  assert.deepEqual(g.edges(), visible.edges.map((_, i) => `e${i}`));
  visible.edges.forEach((e, i) => { assert.equal(g.source(`e${i}`), e.de); assert.equal(g.target(`e${i}`), e.para); });
  assert.ok(!g.hasNode('z') && !g.hasNode('missing'));
  for (const n of visible.nodes) assert.deepEqual([g.getNodeAttribute(n.id, 'x'), g.getNodeAttribute(n.id, 'y')], [positions.get(n.id).x, positions.get(n.id).y]);
  const raw = buildConnectionGraph(multi);
  assert.equal(raw.size, multi.edges.length - 1, 'dangling edge is skipped, not re-targeted');
  assert.ok(!raw.hasNode('missing'));
});
test('large synthetic force layout stays bounded in time and finite', () => {
  const large = { nodes: Array.from({ length: 500 }, (_, i) => node(String(i))), edges: Array.from({ length: 499 }, (_, i) => edge(String(Math.floor(i / 3)), String(i + 1))) };
  const started = performance.now();
  const { nodes } = forceLayoutConnections(filterConnections(large));
  assert.ok(performance.now() - started < 5000);
  assert.equal(nodes.length, 500);
  assert.ok(nodes.every(n => Number.isFinite(n.x) && Number.isFinite(n.y)));
});

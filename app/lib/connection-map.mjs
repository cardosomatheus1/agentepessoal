// Presentation only: never infer a relationship from labels, positions or types.
import { MultiDirectedGraph } from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";

const normalize = (text) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR");

export function filterConnections(connections, query = "", type = "todos") {
  const ids = new Set(connections.nodes.map((node) => node.id));
  const validEdges = connections.edges.filter((edge) => ids.has(edge.de) && ids.has(edge.para));
  const term = normalize(query.trim());
  const matches = new Set(connections.nodes.filter((node) =>
    (type === "todos" || node.tipo === type) && normalize(node.rotulo).includes(term),
  ).map((node) => node.id));
  // Keep immediate neighbors as context, but only edges touching a matching node.
  const edges = validEdges.filter((edge) => matches.has(edge.de) || matches.has(edge.para));
  const visible = new Set(edges.flatMap((edge) => [edge.de, edge.para]));
  return { nodes: connections.nodes.filter((node) => visible.has(node.id)), edges, matches };
}

export function layoutConnections(connections) {
  const adjacency = new Map(connections.nodes.map((node) => [node.id, new Set()]));
  for (const edge of connections.edges) {
    adjacency.get(edge.de)?.add(edge.para);
    adjacency.get(edge.para)?.add(edge.de);
  }
  const visited = new Set();
  const groups = [];
  for (const node of connections.nodes) {
    if (visited.has(node.id)) continue;
    const group = [node.id];
    visited.add(node.id);
    for (let i = 0; i < group.length; i++) {
      for (const id of adjacency.get(group[i]) ?? []) {
        if (adjacency.has(id) && !visited.has(id)) { visited.add(id); group.push(id); }
      }
    }
    group.sort((a, b) => adjacency.get(b).size - adjacency.get(a).size || a.localeCompare(b));
    groups.push(group);
  }
  // Separate connected components; a high-degree node anchors each radial group.
  // Linear traversal + sorting, no force simulation, timers or pairwise physics.
  const positioned = new Map();
  const columns = Math.max(1, Math.ceil(Math.sqrt(groups.length)));
  const radiusFor = (group) => Math.max(220, (group.length - 1) * 260 / (2 * Math.PI));
  const cell = Math.max(460, ...groups.map((group) => radiusFor(group) * 2 + 240));
  groups.forEach((group, index) => {
    const cx = (index % columns + 0.5) * cell;
    const cy = (Math.floor(index / columns) + 0.5) * cell;
    positioned.set(group[0], { x: cx, y: cy });
    const radius = radiusFor(group);
    group.slice(1).forEach((id, i) => {
      const angle = i / (group.length - 1) * Math.PI * 2 - Math.PI / 2;
      positioned.set(id, { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) });
    });
  });
  return {
    nodes: connections.nodes.map((node) => ({ ...node, ...positioned.get(node.id) })),
    width: columns * cell,
    height: Math.max(1, Math.ceil(groups.length / columns)) * cell,
  };
}

const degrees = (connections) => {
  const degree = new Map(connections.nodes.map((node) => [node.id, 0]));
  for (const edge of connections.edges) {
    if (degree.has(edge.de)) degree.set(edge.de, degree.get(edge.de) + 1);
    if (degree.has(edge.para)) degree.set(edge.para, degree.get(edge.para) + 1);
  }
  return degree;
};
export const nodeSize = (tipo, degree) => (tipo === "fio" ? 7 : 5) + Math.min(7, Math.sqrt(degree) * 2);

// Graphology graph for the renderer. Edge `e<i>` is exactly connections.edges[i]: duplicates and self-links stay,
// edges with a missing endpoint are skipped (filterConnections already drops them), nothing is added.
export function buildConnectionGraph(connections, positions) {
  const graph = new MultiDirectedGraph({ allowSelfLoops: true });
  const degree = degrees(connections);
  for (const node of connections.nodes) {
    const at = positions?.get(node.id);
    graph.addNode(node.id, { x: at?.x ?? 0, y: at?.y ?? 0, label: node.rotulo, tipo: node.tipo, size: nodeSize(node.tipo, degree.get(node.id)) });
  }
  connections.edges.forEach((edge, index) => {
    if (graph.hasNode(edge.de) && graph.hasNode(edge.para)) graph.addDirectedEdgeWithKey(`e${index}`, edge.de, edge.para, { label: edge.rotulo ?? "" });
  });
  return graph;
}

// Force-directed positions, deterministic: seeded by the radial component layout (no Math.random), then a bounded
// number of synchronous ForceAtlas2 steps (no timers/workers). Same input, same output; input is never mutated.
// Settings were tuned on the real graph (many small components): edges stay short and groups keep clear gaps.
const SEED_SCALE = 0.02;
export function forceLayoutConnections(connections, { iterations } = {}) {
  const seed = layoutConnections(connections);
  const positions = new Map(seed.nodes.map((node) => [node.id, { x: node.x * SEED_SCALE, y: node.y * SEED_SCALE }]));
  const graph = buildConnectionGraph(connections, positions);
  if (graph.order > 1) {
    const steps = iterations ?? (graph.order > 300 ? 60 : 500);
    const settings = { strongGravityMode: true, gravity: 0.1, scalingRatio: 40, slowDown: 3, adjustSizes: true, barnesHutOptimize: graph.order > 300 };
    const result = forceAtlas2(graph, { iterations: steps, settings, getEdgeWeight: null });
    // Keep the seed if the physics ever diverges; never emit NaN/Infinity.
    if (Object.values(result).every(({ x, y }) => Number.isFinite(x) && Number.isFinite(y))) {
      for (const [id, { x, y }] of Object.entries(result)) positions.set(id, { x, y });
    }
  }
  return { nodes: connections.nodes.map((node) => ({ ...node, ...positions.get(node.id) })), positions };
}

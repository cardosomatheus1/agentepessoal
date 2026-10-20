// Colocação de rótulos do mapa em pixels de tela: nenhum par se sobrepõe, nenhum sai da borda.
// Determinística (mesma entrada, mesma saída). O Sigma só desenha o que este plano devolver.

export const LABEL_MARGIN = 5; // igual ao DEFAULT_LABEL_MARGIN do Sigma (distância entre o nó e o texto)
export const MOBILE_MAX_WIDTH = 640;

export function labelPolicy(width, height) {
  const mobile = width < MOBILE_MAX_WIDTH;
  const area = Math.max(0, width) * Math.max(0, height);
  // Mobile: mais folga entre rótulos e menos rótulos por área.
  return { mobile, gap: mobile ? 6 : 3, edge: mobile ? 6 : 4, budget: Math.max(1, Math.floor(area / (mobile ? 16000 : 7000))) };
}

function box(c, w, pos) {
  const h = c.size * 1.25;
  const x0 = pos === "right" ? c.x + c.r + LABEL_MARGIN : c.x - c.r - LABEL_MARGIN - w;
  return { x0, x1: x0 + w, y0: c.y - h / 2, y1: c.y + h / 2 };
}
const dentro = (b, W, H, e) => b.x0 >= e && b.y0 >= e && b.x1 <= W - e && b.y1 <= H - e;
const bate = (a, b, g) => a.x0 < b.x1 + g && b.x0 < a.x1 + g && a.y0 < b.y1 + g && b.y0 < a.y1 + g;

/**
 * candidates: { id, x, y, r, text, size, priority, pinned? } em pixels do viewport.
 * measure(text, size) → largura real do texto em px.
 * Retorna Map id → { position: "right" | "left", box }.
 * `pinned` (nó selecionado/em hover) entra primeiro e fora da cota; os demais competem por prioridade.
 */
export function planLabels(candidates, { width, height, measure, policy = labelPolicy(width, height) }) {
  const ordem = [...candidates].filter((c) => c.text).sort((a, b) => (+!!b.pinned - +!!a.pinned) || b.priority - a.priority || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const placed = new Map();
  const boxes = [];
  let livres = policy.budget;
  for (const c of ordem) {
    if (!c.pinned && livres <= 0) break;
    const w = measure(c.text, c.size);
    for (const pos of ["right", "left"]) {
      const b = box(c, w, pos);
      if (!dentro(b, width, height, policy.edge)) continue;
      if (boxes.some((o) => bate(b, o, policy.gap))) continue;
      placed.set(c.id, { position: pos, box: b });
      boxes.push(b);
      if (!c.pinned) livres -= 1;
      break;
    }
    // O nó em foco sempre tem rótulo: se não couber inteiro, fica do lado que mostra mais texto.
    if (c.pinned && !placed.has(c.id)) {
      const visto = (b) => Math.max(0, Math.min(b.x1, width) - Math.max(b.x0, 0));
      const [d, e] = [box(c, w, "right"), box(c, w, "left")];
      const pos = visto(e) > visto(d) ? "left" : "right";
      placed.set(c.id, { position: pos, box: pos === "left" ? e : d });
      boxes.push(pos === "left" ? e : d);
    }
  }
  return placed;
}

export function sameLabelPlan(a, b) {
  if (a.size !== b.size) return false;
  for (const [id, v] of a) if (b.get(id)?.position !== v.position) return false;
  return true;
}

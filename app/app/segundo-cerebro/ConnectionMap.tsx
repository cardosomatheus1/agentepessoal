"use client";

import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Minus, Plus, Maximize, Network, List, Search } from "lucide-react";
import type Sigma from "sigma";
import type { Conexoes, Fio } from "@/lib/second-brain.mjs";
import { buildConnectionGraph, filterConnections, forceLayoutConnections, type MapEdgeAttributes, type MapNodeAttributes } from "@/lib/connection-map.mjs";
import s from "./connection-map.module.css";

type NodeType = "todos" | "fio" | "texto";
type Renderer = Sigma<MapNodeAttributes, MapEdgeAttributes>;
type Status = "carregando" | "pronto" | "erro";
const COLORS = { fio: "#c6f432", texto: "#3fe0e6", dimNode: "#384031", edge: "#5d6b55", edgeActive: "#c6f432", edgeDim: "#262c22", label: "#ecefe6" };
const MIN_RATIO = 0.25, MAX_RATIO = 2.5, STEP = 1.25;
const date = (value: string | null) => {
  if (!value) return "Data não registrada";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("pt-BR", { timeZone: "UTC" });
};
const shortLabel = (label: string, max = 34) => (label.length > max ? `${label.slice(0, max - 1).trimEnd()}…` : label);
const motion = () => (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 250);

export default function ConnectionMap({ connections, threads }: { connections: Conexoes; threads: Fio[] }) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState<NodeType>("todos");
  const [view, setView] = useState<"mapa" | "lista">("mapa");
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("carregando");
  const [zoomPct, setZoomPct] = useState(100);
  const [drawn, setDrawn] = useState({ nodes: 0, edges: 0 });
  const container = useRef<HTMLDivElement>(null);
  const renderer = useRef<Renderer | null>(null);
  const focus = useRef<{ id: string | null; neighbors: Set<string>; matches: Set<string>; filtered: boolean }>({ id: null, neighbors: new Set(), matches: new Set(), filtered: false });
  const helpId = useId().replace(/:/g, "");
  // Positions come from the whole recorded graph, once per data load: filters and selection never move nodes.
  const layout = useMemo(() => forceLayoutConnections(filterConnections(connections)), [connections]);
  const visible = useMemo(() => filterConnections(connections, query, type), [connections, query, type]);
  const graph = useMemo(() => buildConnectionGraph(visible, layout.positions), [visible, layout]);
  const active = visible.nodes.find((node) => node.id === selected);
  const fio = active?.tipo === "fio" ? threads.find((thread) => `fio:${thread.id}` === active.id) : undefined;
  const related = visible.edges.filter((edge) => edge.de === active?.id || edge.para === active?.id);
  const nodeById = new Map(connections.nodes.map((node) => [node.id, node]));
  const isFiltered = !!query.trim() || type !== "todos";
  const hasNodes = visible.nodes.length > 0;
  const sortedNodes = useMemo(() => [...visible.nodes].sort((a, b) => a.rotulo.localeCompare(b.rotulo, "pt-BR")), [visible]);

  useEffect(() => {
    if (view !== "mapa" || !hasNodes || !container.current) return;
    const element = container.current;
    let cancelled = false;
    let instance: Renderer | null = null;
    let observer: ResizeObserver | null = null;
    setStatus("carregando");
    (async () => {
      try {
        // WebGL2 is required by Sigma 4; check first so the fallback is explicit, not a blank canvas.
        if (!document.createElement("canvas").getContext("webgl2")) throw new Error("WebGL2 indisponível");
        const [{ default: SigmaClass }, { pathLine, pathLoop, pathCurved, extremityArrow }] = await Promise.all([import("sigma"), import("sigma/rendering")]);
        if (cancelled) return;
        instance = new SigmaClass<MapNodeAttributes, MapEdgeAttributes>(graph, element, {
          primitives: { edges: { paths: [pathLine(), pathLoop(), pathCurved()], extremities: [extremityArrow()], defaultHead: "arrow" } },
          settings: {
            itemSizesReference: "screen", zoomToSizeRatioFunction: (ratio) => Math.sqrt(ratio), stagePadding: 40,
            minCameraRatio: MIN_RATIO, maxCameraRatio: MAX_RATIO, enableCameraRotation: false, enableCameraMouseRotation: false,
            labelDensity: 0.35, labelGridCellSize: 220, labelRenderedSizeThreshold: 9, zoomingRatio: STEP, zoomDuration: motion(),
            // A resize can briefly report 0 width (rotation, layout switch); redraw on the next size instead of throwing.
            gestureTarget: "graph", allowInvalidContainer: true,
          },
          nodeReducer: (id, data, attrs) => {
            const { id: target, neighbors, matches, filtered } = focus.current;
            const lit = !target || id === target || neighbors.has(id);
            const context = filtered && !matches.has(id);
            return {
              label: shortLabel(attrs.label), labelColor: COLORS.label, labelSize: id === target ? 15 : 13,
              color: lit ? COLORS[attrs.tipo] : COLORS.dimNode, opacity: context && !target ? 0.55 : 1,
              size: id === target ? attrs.size + 3 : attrs.size, highlighted: id === target,
              labelVisibility: target ? (lit ? "visible" : "hidden") : "auto", zIndex: lit ? 1 : 0, depth: id === target ? "topNodes" : "nodes",
              backdropColor: "#181b15", backdropShadowColor: "rgba(0, 0, 0, 0.6)", backdropBorderColor: COLORS[attrs.tipo], backdropBorderWidth: 1, backdropCornerRadius: 6,
              labelBackgroundColor: target && lit ? "rgba(11, 12, 10, 0.8)" : "rgba(0, 0, 0, 0)", labelBackgroundPadding: 3, cursor: "pointer",
            };
          },
          edgeReducer: (id, data, attrs, state, graphState, g) => {
            const target = focus.current.id;
            const touches = !!target && (g.source(id) === target || g.target(id) === target);
            return { color: !target ? COLORS.edge : touches ? COLORS.edgeActive : COLORS.edgeDim, size: touches ? 2.4 : 1.2, zIndex: touches ? 1 : 0, depth: touches ? "topEdges" : "edges", parallelPath: "curved", selfLoopPath: "loop" };
          },
        });
        renderer.current = instance;
        const camera = instance.getCamera();
        camera.on("updated", (state) => setZoomPct(Math.round(100 / state.ratio)));
        instance.on("clickNode", ({ node }) => setSelected(node));
        instance.on("enterNode", ({ node }) => setHovered(node));
        instance.on("leaveNode", () => setHovered(null));
        instance.on("clickStage", () => setSelected(null));
        instance.on("webglContextLost", () => setStatus("erro"));
        instance.on("webglContextRestored", () => setStatus("pronto"));
        observer = new ResizeObserver(() => instance?.scheduleRefresh());
        observer.observe(element);
        // Read-only hook for the local browser checks: node position on screen; removed on cleanup.
        Object.defineProperty(element, "__mapaViewport", { configurable: true, value: (id: string) => (instance?.getGraph().hasNode(id) ? instance.graphToViewport(instance.getGraph().getNodeAttributes(id)) : null) });
        setDrawn({ nodes: graph.order, edges: graph.size });
        setZoomPct(100);
        setStatus("pronto");
      } catch {
        if (!cancelled) setStatus("erro");
      }
    })();
    return () => {
      cancelled = true;
      observer?.disconnect();
      if (instance) {
        instance.getCamera().removeAllListeners();
        instance.removeAllListeners();
        instance.kill();
      }
      delete (element as unknown as Record<string, unknown>).__mapaViewport;
      if (renderer.current === instance) renderer.current = null;
      setHovered(null);
    };
  }, [graph, view, hasNodes]);

  useEffect(() => {
    const id = hovered ?? selected;
    focus.current = { id: id && graph.hasNode(id) ? id : null, neighbors: new Set(id && graph.hasNode(id) ? graph.neighbors(id) : []), matches: visible.matches, filtered: isFiltered };
    renderer.current?.refresh({ skipIndexation: true });
  }, [hovered, selected, graph, visible, isFiltered, status]);

  const camera = () => renderer.current?.getCamera();
  const reset = () => { camera()?.reset({ duration: motion() }); };
  const zoom = (factor: number) => { const c = camera(); if (c) c.animate({ ratio: c.getBoundedRatio(c.ratio / factor) }, { duration: motion() }); };
  function centerOn(id: string) {
    const r = renderer.current;
    const at = r?.getNodeDisplayData(id);
    if (r && at) r.getCamera().animate({ x: at.x, y: at.y }, { duration: motion() });
  }
  function choose(id: string, center = false) { setSelected(id); if (center) centerOn(id); }
  function mapKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.target !== event.currentTarget) return;
    const c = camera();
    if (!c) return;
    const d = 0.1 * c.ratio;
    const deltas: Record<string, [number, number]> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, d], ArrowDown: [0, -d] };
    if (deltas[event.key]) {
      event.preventDefault();
      const [x, y] = deltas[event.key];
      c.setState({ x: c.x + x, y: c.y + y });
    } else if (["+", "=", "-", "0", "Escape"].includes(event.key)) {
      event.preventDefault();
      if (event.key === "Escape") setSelected(null); else if (event.key === "0") reset(); else zoom(event.key === "-" ? 1 / STEP : STEP);
    }
  }
  const clearSelection = () => { setSelected(null); setHovered(null); };

  return (
    <div className={s.root}>
      <header className={s.header}>
        <div><p className={s.eyebrow}>Explore o que está conectado</p><h3>Mapa de conexões</h3></div>
        <div className={s.switcher} aria-label="Visualização das conexões">
          <button type="button" aria-pressed={view === "mapa"} onClick={() => setView("mapa")}><Network size={16} aria-hidden /> Mapa</button>
          <button type="button" aria-pressed={view === "lista"} onClick={() => setView("lista")}><List size={16} aria-hidden /> Lista</button>
        </div>
      </header>
      <div className={s.filters}>
        <label className={s.search}><Search size={16} aria-hidden /><span className={s.srOnly}>Buscar no mapa</span><input type="search" placeholder="Buscar uma conexão…" value={query} onChange={(event) => { setQuery(event.target.value); clearSelection(); }} /></label>
        <label className={s.type}>Mostrar<select value={type} onChange={(event) => { setType(event.target.value as NodeType); clearSelection(); }}><option value="todos">Todos os tipos</option><option value="fio">Fios</option><option value="texto">Referências textuais</option></select></label>
      </div>
      <div className={s.summary} role="status">{visible.nodes.length} nós · {visible.edges.length} de {connections.edges.length} ligações registradas{isFiltered ? " · com vizinhos diretos para contexto" : ""}</div>
      {!hasNodes ? (
        <div className={s.empty}><Network size={36} aria-hidden /><h4>Nenhuma conexão encontrada</h4><p>Tente outro termo ou remova os filtros. Nenhuma relação é inferida.</p><button type="button" onClick={() => { setQuery(""); setType("todos"); clearSelection(); }}>Limpar filtros</button></div>
      ) : (
        <>
          {view === "mapa" ? (
            <div className={s.workspace}>
              <div className={s.canvas}>
                <div className={s.toolbar}>
                  <div className={s.zoom} aria-label="Controles do mapa">
                    <button type="button" aria-label="Diminuir zoom" disabled={status !== "pronto" || zoomPct <= Math.round(100 / MAX_RATIO)} onClick={() => zoom(1 / STEP)}><Minus size={17} aria-hidden /></button>
                    <output aria-label="Zoom">{zoomPct}%</output>
                    <button type="button" aria-label="Aumentar zoom" disabled={status !== "pronto" || zoomPct >= Math.round(100 / MIN_RATIO)} onClick={() => zoom(STEP)}><Plus size={17} aria-hidden /></button>
                    <button type="button" aria-label="Ajustar mapa à tela" disabled={status !== "pronto"} onClick={reset}><Maximize size={17} aria-hidden /></button>
                  </div>
                  <label className={s.jump}><span>Ir para</span><select value={active?.id ?? ""} onChange={(event) => { if (event.target.value) choose(event.target.value, true); else setSelected(null); }}><option value="">Escolha um nó…</option>{sortedNodes.map((node) => <option key={node.id} value={node.id}>{node.tipo === "fio" ? "Fio" : "Referência"}: {shortLabel(node.rotulo)}</option>)}</select></label>
                </div>
                <div ref={container} className={s.stage} data-renderer={status} data-nodes={status === "pronto" ? drawn.nodes : undefined} data-edges={status === "pronto" ? drawn.edges : undefined} role="group" aria-label="Mapa interativo de conexões explícitas" aria-describedby={`${helpId}-help`} tabIndex={0} onKeyDown={mapKey} />
                {status === "carregando" && <p className={s.overlay} aria-live="polite">Desenhando o mapa…</p>}
                {status === "erro" && <div className={s.overlay} role="alert"><p>Não foi possível desenhar o mapa neste navegador (WebGL indisponível).</p><button type="button" onClick={() => setView("lista")}>Ver as ligações em lista</button></div>}
                <p id={`${helpId}-help`} className={s.help}>Arraste para mover · role ou faça pinça para zoom · toque ou clique em um nó para explorar.<span> Teclado: “Ir para” ou a Lista escolhem nós; no mapa, setas, +/−, 0 e Esc.</span></p>
              </div>
              <aside className={s.details} aria-label="Detalhes do nó" aria-live="polite">
                {!active ? <div className={s.invitation}><Network size={32} aria-hidden /><h4>Uma ligação, seu contexto.</h4><p>Selecione um nó para ver o registro e as ligações que o sustentam.</p><small>Distância e posição são apenas organização visual, não relevância.</small></div> : (
                  <><p className={s.eyebrow}>{active.tipo === "fio" ? "Fio registrado" : "Referência textual"}{isFiltered && !visible.matches.has(active.id) ? " · contexto" : ""}</p><h4>{active.rotulo}</h4>
                    {fio ? <><p>{fio.detalhe ?? "Sem descrição adicional."}</p>{fio.proximo_passo && <div className={s.next}><strong>Próximo passo</strong><p>{fio.proximo_passo}</p></div>}<dl><dt>Estado / prioridade</dt><dd>{fio.estado ?? "Não registrado"} / {fio.prioridade ?? "Não registrada"}</dd><dt>Prazo</dt><dd>{date(fio.prazo)}</dd><dt>Fonte</dt><dd>{fio.proveniencia.fonteRotulo} · fio {fio.id}</dd><dt>Atualizado</dt><dd>{date(fio.atualizado ?? fio.criado)}</dd></dl></> : <p>Texto citado em uma ligação. Não é um fio, uma decisão ou um fato de perfil verificado.</p>}
                    <h5>Ligações neste recorte ({related.length})</h5><ul className={s.related}>{related.map((edge, index) => { const other = edge.de === active.id ? edge.para : edge.de; return <li key={index}><button type="button" onClick={() => choose(other, true)}>{edge.de === active.id ? "→" : "←"} {nodeById.get(other)?.rotulo ?? other}</button><p>{edge.rotulo ?? "Ligação registrada"}</p><small>Fonte: fios · registro {edge.evidencia.fioId} · {date(edge.evidencia.em)}</small></li>; })}</ul>
                  </>
                )}
              </aside>
            </div>
          ) : (
            <ul className={s.connectionList} aria-label="Lista de conexões explícitas">{visible.edges.map((edge, index) => <li key={index}><h4>{nodeById.get(edge.de)?.rotulo} <span aria-label="liga-se a">→</span> {nodeById.get(edge.para)?.rotulo}</h4><p>{edge.rotulo ?? "Ligação registrada"}</p><small>Fonte: fios · registro {edge.evidencia.fioId} · {date(edge.evidencia.em)}</small><button type="button" onClick={() => { setSelected(edge.de); setView("mapa"); }}>Explorar no mapa</button></li>)}</ul>
          )}
          <footer className={s.legend}><span><i className={s.threadSwatch} /> Fio</span><span><i className={s.textSwatch} /> Referência textual</span><span>→ Ligação explícita · só leitura</span></footer>
        </>
      )}
    </div>
  );
}

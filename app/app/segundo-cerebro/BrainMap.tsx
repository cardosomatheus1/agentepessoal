"use client";

import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ChevronLeft, ChevronRight, List, Maximize, Minus, Network, Plus, Search } from "lucide-react";
import type Sigma from "sigma";
import type { SegundoCerebro } from "@/lib/second-brain.mjs";
import {
  AGRUPAMENTOS, RELACOES, TIPOS, buildBrainGraph, buildSigmaGraph, filterBrainGraph, layoutBrainGraph, neighborsOf,
  type Agrupamento, type AtributosAresta, type AtributosNo, type NoCerebro, type Relacao, type TipoNo,
} from "@/lib/brain-graph.mjs";
import { planLabels, sameLabelPlan, type LabelCandidate, type LabelPlan } from "@/lib/label-layout.mjs";
import s from "./brain-map.module.css";

type Renderer = Sigma<AtributosNo, AtributosAresta>;
type Status = "carregando" | "pronto" | "erro";
const CORES_CLASSE = { comprovada: "#c6f432", referencia: "#3fe0e6", proveniencia: "#3b4535" } as const;
const DIM = "#2c3327";
const MIN_RATIO = 0.08, MAX_RATIO = 3, STEP = 1.3;
const motion = () => (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 250);
const curto = (t: string, n = 30) => (t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t);
const todos = <T extends string>(xs: readonly T[]) => new Set<string>(xs);
const LABEL_FONT = "sans-serif"; // fonte padrão do Sigma para rótulos de nó

// Plano de rótulos em pixels de tela, refeito a cada câmera/resize/foco; o Sigma só desenha os rótulos do plano.
function planejarRotulos(r: Renderer, alvo: string | null, vizinhos: Set<string>, matches: Set<string>, filtered: boolean, medir: (t: string, px: number) => number): LabelPlan {
  const { width, height } = r.getDimensions();
  const g = r.getGraph();
  const cands: LabelCandidate[] = [];
  g.forEachNode((id, attrs) => {
    if (alvo && id !== alvo && !vizinhos.has(id)) return;
    const d = r.getNodeDisplayData(id);
    if (!d || d.visibility === "hidden" || !d.label) return;
    const p = r.framedGraphToViewport(d);
    const pinned = id === alvo;
    const priority = (vizinhos.has(id) ? 1000 : 0) + (attrs.tipo === "fonte" ? 500 : 0) + (filtered && matches.has(id) ? 200 : 0) + g.degree(id);
    cands.push({ id, x: p.x, y: p.y, r: r.scaleSize(d.size), text: d.label, size: d.labelSize ?? 11, priority, pinned });
  });
  return planLabels(cands, { width, height, measure: medir });
}

export default function BrainMap({ brain, area = "", onOpen }: { brain: SegundoCerebro; area?: string; onOpen: (ref: string) => void }) {
  const grafo = useMemo(() => buildBrainGraph(brain), [brain]);
  const tiposPresentes = useMemo(() => (Object.keys(TIPOS) as TipoNo[]).filter((t) => grafo.nodes.some((n) => n.tipo === t)), [grafo]);
  const fontesPresentes = useMemo(() => brain.sources.map((f) => f.id), [brain]);
  const relacoesPresentes = useMemo(() => (Object.keys(RELACOES) as Relacao[]).filter((r) => grafo.edges.some((e) => e.relacao === r)), [grafo]);
  const [termo, setTermo] = useState("");
  const [tipos, setTipos] = useState<Set<string>>(() => todos(Object.keys(TIPOS)));
  const [fontes, setFontes] = useState<Set<string>>(() => todos(brain.sources.map((f) => f.id)));
  const [relacoes, setRelacoes] = useState<Set<string>>(() => todos(Object.keys(RELACOES)));
  const [vizinhos, setVizinhos] = useState(false);
  const [agrupar, setAgrupar] = useState<Agrupamento>("fonte");
  const [view, setView] = useState<"mapa" | "lista">("mapa");
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [focoIdx, setFocoIdx] = useState(0);
  const [status, setStatus] = useState<Status>("carregando");
  const [zoomPct, setZoomPct] = useState(100);
  const [drawn, setDrawn] = useState({ nodes: 0, edges: 0, isolados: 0 });
  const container = useRef<HTMLDivElement>(null);
  const renderer = useRef<Renderer | null>(null);
  const focus = useRef<{ id: string | null; neighbors: Set<string>; matches: Set<string>; filtered: boolean }>({ id: null, neighbors: new Set(), matches: new Set(), filtered: false });
  const rotulos = useRef<LabelPlan>(new Map());
  const replanejar = useRef<() => void>(() => {});
  const helpId = useId().replace(/:/g, "");

  const layout = useMemo(() => layoutBrainGraph(grafo, agrupar), [grafo, agrupar]);
  const areas = useMemo(() => (area ? new Set([area]) : undefined), [area]);
  const visivel = useMemo(() => filterBrainGraph(grafo, { termo, tipos, fontes, areas, relacoes, vizinhos }), [grafo, termo, tipos, fontes, areas, relacoes, vizinhos]);
  const sigmaGraph = useMemo(() => buildSigmaGraph(visivel, layout.positions), [visivel, layout]);
  const porId = useMemo(() => new Map(grafo.nodes.map((n) => [n.id, n])), [grafo]);
  const matches = useMemo(() => (termo.trim() ? visivel.nodes.filter((n) => visivel.matches.has(n.id)) : []), [visivel, termo]);
  const isolados = useMemo(() => {
    const comAresta = new Set(visivel.edges.flatMap((e) => [e.de, e.para]));
    return visivel.nodes.filter((n) => !comAresta.has(n.id)).length;
  }, [visivel]);
  const ativo = selected ? porId.get(selected) ?? null : null;
  const ligacoes = ativo ? neighborsOf(visivel, ativo.id) : [];
  const ligacoesTotais = ativo ? neighborsOf(grafo, ativo.id).length : 0;
  const filtrado = !!area || !!termo.trim() || tipos.size < Object.keys(TIPOS).length || fontes.size < fontesPresentes.length || relacoes.size < Object.keys(RELACOES).length;
  const hasNodes = visivel.nodes.length > 0;

  useEffect(() => {
    if (view !== "mapa" || !hasNodes || !container.current) return;
    const element = container.current;
    let cancelled = false;
    let instance: Renderer | null = null;
    let observer: ResizeObserver | null = null;
    let quadro = 0;
    rotulos.current = new Map();
    setStatus("carregando");
    (async () => {
      try {
        if (!document.createElement("canvas").getContext("webgl2")) throw new Error("WebGL2 indisponível");
        const [{ default: SigmaClass }, r, p] = await Promise.all([import("sigma"), import("sigma/rendering"), import("sigma/primitives")]);
        if (cancelled) return;
        instance = new SigmaClass<AtributosNo, AtributosAresta>(sigmaGraph, element, {
          primitives: {
            nodes: { shapes: [...p.DEFAULT_NODE_PRIMITIVES.shapes, r.sdfSquare({ cornerRadius: 0.15 }), r.sdfTriangle(), r.sdfDiamond()] },
            edges: { paths: [...p.DEFAULT_EDGE_PRIMITIVES.paths, r.pathCurved()], extremities: [...p.DEFAULT_EDGE_PRIMITIVES.extremities, r.extremityArrow()], defaultHead: "arrow" },
          },
          settings: {
            itemSizesReference: "screen", zoomToSizeRatioFunction: (ratio) => Math.sqrt(ratio), stagePadding: 30,
            minCameraRatio: MIN_RATIO, maxCameraRatio: MAX_RATIO, enableCameraRotation: false, enableCameraMouseRotation: false,
            labelDensity: 0.5, labelGridCellSize: 160, labelRenderedSizeThreshold: 8, zoomingRatio: STEP, zoomDuration: motion(),
            gestureTarget: "graph", allowInvalidContainer: true,
          },
          nodeReducer: (id, data, attrs) => {
            const { id: alvo, neighbors, matches: m, filtered } = focus.current;
            const lit = !alvo || id === alvo || neighbors.has(id);
            const contexto = filtered && !m.has(id);
            return {
              label: curto(attrs.label), labelColor: "#ecefe6", labelSize: id === alvo ? 14 : 11,
              color: lit ? attrs.color : DIM, shape: attrs.shape, opacity: contexto && !alvo ? 0.6 : 1,
              size: id === alvo ? attrs.size + 4 : attrs.size, highlighted: id === alvo,
              labelVisibility: rotulos.current.has(id) ? "visible" : "hidden", labelPosition: rotulos.current.get(id)?.position ?? "right", labelFont: LABEL_FONT,
              zIndex: lit ? 1 : 0, depth: id === alvo ? "topNodes" : "nodes",
              labelBackgroundColor: alvo && lit ? "rgba(11, 12, 10, 0.85)" : "rgba(0, 0, 0, 0)", labelBackgroundPadding: 3, cursor: "pointer",
            };
          },
          edgeReducer: (id, data, attrs, state, graphState, g) => {
            const alvo = focus.current.id;
            const toca = !!alvo && (g.source(id) === alvo || g.target(id) === alvo);
            const cor = CORES_CLASSE[attrs.classe];
            return { color: !alvo ? cor : toca ? cor : "#1d221a", size: toca ? 2.6 : attrs.classe === "comprovada" ? 1.8 : 0.8, zIndex: toca ? 1 : 0, depth: toca ? "topEdges" : "edges", parallelPath: "curved" };
          },
        });
        renderer.current = instance;
        const ctx = document.createElement("canvas").getContext("2d");
        const larguras = new Map<string, number>();
        const medir = (t: string, px: number) => {
          const k = `${px}|${t}`;
          let w = larguras.get(k);
          if (w === undefined) { if (ctx) ctx.font = `${px}px ${LABEL_FONT}`; w = ctx ? ctx.measureText(t).width : t.length * px * 0.62; larguras.set(k, w); }
          return w;
        };
        // Um replanejamento por quadro; só pede refresh ao Sigma se o plano mudou (sem laço: refresh não move a câmera).
        replanejar.current = () => {
          if (quadro) return;
          quadro = requestAnimationFrame(() => {
            quadro = 0;
            const r = renderer.current;
            if (!r || r !== instance) return;
            const f = focus.current;
            const plano = planejarRotulos(r, f.id, f.neighbors, f.matches, f.filtered, medir);
            if (sameLabelPlan(plano, rotulos.current)) { rotulos.current = plano; return; }
            rotulos.current = plano;
            r.refresh({ skipIndexation: true });
          });
        };
        const camera = instance.getCamera();
        camera.on("updated", (st) => { setZoomPct(Math.round(100 / st.ratio)); replanejar.current(); });
        instance.on("clickNode", ({ node }) => setSelected(node));
        instance.on("enterNode", ({ node }) => setHovered(node));
        instance.on("leaveNode", () => setHovered(null));
        instance.on("clickStage", () => setSelected(null));
        instance.on("webglContextLost", () => setStatus("erro"));
        instance.on("webglContextRestored", () => setStatus("pronto"));
        observer = new ResizeObserver(() => { instance?.scheduleRefresh(); replanejar.current(); });
        observer.observe(element);
        Object.defineProperty(element, "__mapaRotulos", { configurable: true, value: () => [...rotulos.current].map(([id, v]) => ({ id, ...v })) });
        replanejar.current();
        Object.defineProperty(element, "__mapaViewport", { configurable: true, value: (id: string) => (instance?.getGraph().hasNode(id) ? instance.graphToViewport(instance.getGraph().getNodeAttributes(id)) : null) });
        Object.defineProperty(element, "__mapaCamera", { configurable: true, value: () => instance?.getCamera().getState() ?? null });
        setDrawn({ nodes: sigmaGraph.order, edges: sigmaGraph.size, isolados });
        setZoomPct(100);
        setStatus("pronto");
      } catch {
        if (!cancelled) setStatus("erro");
      }
    })();
    return () => {
      cancelled = true;
      observer?.disconnect();
      if (quadro) cancelAnimationFrame(quadro);
      replanejar.current = () => {};
      if (instance) {
        instance.getCamera().removeAllListeners();
        instance.removeAllListeners();
        instance.kill();
      }
      delete (element as unknown as Record<string, unknown>).__mapaViewport;
      delete (element as unknown as Record<string, unknown>).__mapaCamera;
      delete (element as unknown as Record<string, unknown>).__mapaRotulos;
      if (renderer.current === instance) renderer.current = null;
      setHovered(null);
    };
  }, [sigmaGraph, view, hasNodes, isolados]);

  useEffect(() => {
    const id = hovered ?? selected;
    const tem = !!id && sigmaGraph.hasNode(id);
    focus.current = { id: tem ? id : null, neighbors: new Set(tem ? sigmaGraph.neighbors(id) : []), matches: visivel.matches, filtered: filtrado };
    renderer.current?.refresh({ skipIndexation: true });
    replanejar.current();
  }, [hovered, selected, sigmaGraph, visivel, filtrado, status]);

  const camera = () => renderer.current?.getCamera();
  const reset = () => { camera()?.reset({ duration: motion() }); };
  const zoom = (f: number) => { const c = camera(); if (c) c.animate({ ratio: c.getBoundedRatio(c.ratio / f) }, { duration: motion() }); };
  function centrar(id: string) {
    const r = renderer.current;
    const at = r?.getNodeDisplayData(id);
    if (r && at) r.getCamera().animate({ x: at.x, y: at.y, ratio: Math.min(r.getCamera().ratio, 0.45) }, { duration: motion() });
  }
  function escolher(id: string, centro = true) { setSelected(id); if (centro) centrar(id); }
  function focar(i: number) {
    if (!matches.length) return;
    const idx = (i + matches.length) % matches.length;
    setFocoIdx(idx);
    escolher(matches[idx].id);
  }
  function mapKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.target !== event.currentTarget) return;
    const c = camera();
    if (!c) return;
    const d = 0.1 * c.ratio;
    const deltas: Record<string, [number, number]> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, d], ArrowDown: [0, -d] };
    if (deltas[event.key]) { event.preventDefault(); const [x, y] = deltas[event.key]; c.setState({ x: c.x + x, y: c.y + y }); }
    else if (["+", "=", "-", "0", "Escape"].includes(event.key)) { event.preventDefault(); if (event.key === "Escape") setSelected(null); else if (event.key === "0") reset(); else zoom(event.key === "-" ? 1 / STEP : STEP); }
  }
  const alternar = (set: Set<string>, setter: (x: Set<string>) => void, v: string) => { const n = new Set(set); if (n.has(v)) n.delete(v); else n.add(v); setter(n); setSelected(null); };
  const limpar = () => { setTermo(""); setTipos(todos(Object.keys(TIPOS))); setFontes(todos(fontesPresentes)); setRelacoes(todos(Object.keys(RELACOES))); setVizinhos(false); setSelected(null); };
  const contar = (f: (n: NoCerebro) => boolean) => grafo.nodes.filter(f).length;

  return (
    <div className={s.root}>
      <header className={s.header}>
        <div><p className={s.eyebrow}>Todos os itens da Pasta{area ? ` · área ${area}` : ""}</p><h3>Mapa do Segundo Cérebro</h3></div>
        <div className={s.switcher} aria-label="Visualização do mapa">
          <button type="button" aria-pressed={view === "mapa"} onClick={() => setView("mapa")}><Network size={16} aria-hidden /> Mapa</button>
          <button type="button" aria-pressed={view === "lista"} onClick={() => setView("lista")}><List size={16} aria-hidden /> Lista</button>
        </div>
      </header>

      <div className={s.filters}>
        <div className={s.searchRow}>
          <label className={s.search}><Search size={16} aria-hidden /><span className={s.srOnly}>Buscar no mapa</span>
            <input type="search" placeholder="Buscar registro, tema, fonte…" value={termo} onChange={(e) => { setTermo(e.target.value); setSelected(null); setFocoIdx(0); }} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); focar(focoIdx); } }} />
          </label>
          {termo.trim() && (
            <div className={s.nav} aria-label="Resultados da busca">
              <button type="button" aria-label="Resultado anterior" disabled={!matches.length} onClick={() => focar(focoIdx - 1)}><ChevronLeft size={16} aria-hidden /></button>
              <output aria-label="Posição na busca">{matches.length ? `${focoIdx + 1}/${matches.length}` : "0"}</output>
              <button type="button" aria-label="Próximo resultado" disabled={!matches.length} onClick={() => focar(focoIdx + 1)}><ChevronRight size={16} aria-hidden /></button>
            </div>
          )}
          <label className={s.select}>Agrupar por
            <select value={agrupar} onChange={(e) => { setAgrupar(e.target.value as Agrupamento); setSelected(null); }}>
              {(Object.keys(AGRUPAMENTOS) as Agrupamento[]).map((k) => <option key={k} value={k}>{AGRUPAMENTOS[k]}</option>)}
            </select>
          </label>
        </div>
        <fieldset className={s.chips}><legend>Tipo</legend>
          {tiposPresentes.map((t) => (
            <label key={t} className={s.chip}><input type="checkbox" checked={tipos.has(t)} onChange={() => alternar(tipos, setTipos, t)} />
              <i className={s[`forma_${TIPOS[t].forma}`]} style={{ background: TIPOS[t].cor }} aria-hidden />{TIPOS[t].rotulo} <small>{contar((n) => n.tipo === t)}</small></label>
          ))}
        </fieldset>
        <fieldset className={s.chips}><legend>Fonte</legend>
          {brain.sources.map((f) => (
            <label key={f.id} className={s.chip} data-estado={f.estado}><input type="checkbox" checked={fontes.has(f.id)} onChange={() => alternar(fontes, setFontes, f.id)} />
              {f.rotulo} <small>{f.estado === "indisponivel" ? "indisponível" : contar((n) => n.fonte === f.id && n.tipo !== "fonte")}</small></label>
          ))}
        </fieldset>
        <fieldset className={s.chips}><legend>Relação</legend>
          {relacoesPresentes.map((r) => (
            <label key={r} className={s.chip}><input type="checkbox" checked={relacoes.has(r)} onChange={() => alternar(relacoes, setRelacoes, r)} />
              <i className={s.linha} style={{ background: CORES_CLASSE[RELACOES[r].classe] }} aria-hidden />{RELACOES[r].rotulo} <small>{grafo.edges.filter((e) => e.relacao === r).length}</small></label>
          ))}
          <label className={s.chip}><input type="checkbox" checked={vizinhos} onChange={() => { setVizinhos(!vizinhos); setSelected(null); }} />Na busca, incluir vizinhos diretos (como contexto)</label>
        </fieldset>
      </div>

      <div className={s.summary} role="status" data-visiveis={visivel.nodes.length} data-isolados={isolados}>
        {visivel.nodes.length} de {grafo.nodes.length} nós · {visivel.edges.length} de {grafo.edges.length} ligações · {isolados} sem ligação visível (continuam no mapa)
        {visivel.contexto.size ? ` · ${visivel.contexto.size} vizinho(s) só como contexto` : ""}
        {filtrado && <button type="button" className={s.linkBtn} onClick={limpar}>Limpar filtros</button>}
      </div>

      {!hasNodes ? (
        <div className={s.empty}><Network size={36} aria-hidden /><h4>Nada com esses filtros</h4><p>Nenhuma relação é inferida para preencher o mapa.</p><button type="button" onClick={limpar}>Limpar filtros</button></div>
      ) : view === "mapa" ? (
        <div className={s.workspace}>
          <div className={s.canvas}>
            <div className={s.toolbar}>
              <div className={s.zoom} aria-label="Controles do mapa">
                <button type="button" aria-label="Diminuir zoom" disabled={status !== "pronto"} onClick={() => zoom(1 / STEP)}><Minus size={17} aria-hidden /></button>
                <output aria-label="Zoom">{zoomPct}%</output>
                <button type="button" aria-label="Aumentar zoom" disabled={status !== "pronto"} onClick={() => zoom(STEP)}><Plus size={17} aria-hidden /></button>
                <button type="button" aria-label="Ajustar mapa à tela" disabled={status !== "pronto"} onClick={reset}><Maximize size={17} aria-hidden /></button>
              </div>
              <label className={s.jump}><span>Ir para</span>
                <select value={ativo?.id ?? ""} onChange={(e) => { if (e.target.value) escolher(e.target.value); else setSelected(null); }}>
                  <option value="">Escolha um nó…</option>
                  {[...visivel.nodes].sort((a, b) => a.tipo.localeCompare(b.tipo) || a.rotulo.localeCompare(b.rotulo, "pt-BR")).map((n) => <option key={n.id} value={n.id}>{TIPOS[n.tipo].rotulo}: {curto(n.rotulo, 48)}</option>)}
                </select>
              </label>
            </div>
            <div ref={container} className={s.stage} data-renderer={status} data-nodes={status === "pronto" ? drawn.nodes : undefined} data-edges={status === "pronto" ? drawn.edges : undefined} data-isolados={status === "pronto" ? drawn.isolados : undefined} role="group" aria-label="Mapa interativo do Segundo Cérebro" aria-describedby={`${helpId}-help`} tabIndex={0} onKeyDown={mapKey} />
            {status === "carregando" && <p className={s.overlay} aria-live="polite">Desenhando o mapa…</p>}
            {status === "erro" && <div className={s.overlay} role="alert"><p>Não foi possível desenhar o mapa neste navegador (WebGL indisponível).</p><button type="button" onClick={() => setView("lista")}>Ver em lista</button></div>}
            <p id={`${helpId}-help`} className={s.help}>Arraste para mover · role ou pinça para zoom · clique ou toque num nó.<span> Teclado: busca + Enter, “Ir para” ou a Lista; no mapa, setas, +/−, 0 e Esc.</span></p>
          </div>
          <Detalhes ativo={ativo} ligacoes={ligacoes} total={ligacoesTotais} porId={porId} brain={brain} agrupar={agrupar} contexto={!!ativo && visivel.contexto.has(ativo.id)} onEscolher={escolher} onOpen={onOpen} />
        </div>
      ) : (
        <ul className={s.lista} aria-label="Lista de registros do mapa">
          {visivel.nodes.map((n) => {
            const rel = neighborsOf(visivel, n.id);
            return (
              <li key={n.id}>
                <p className={s.eyebrow}>{TIPOS[n.tipo].rotulo} · {n.fonte}{visivel.contexto.has(n.id) ? " · contexto" : ""}</p>
                <h4>{n.rotuloCompleto ?? n.rotulo}</h4>
                <p>{rel.length ? `${rel.length} ligação(ões) visível(is)` : "Sem ligação visível"}</p>
                <button type="button" onClick={() => { setView("mapa"); setSelected(n.id); }}>Ver no mapa</button>
              </li>
            );
          })}
        </ul>
      )}

      <footer className={s.legend} aria-label="Legenda">
        {tiposPresentes.map((t) => <span key={t}><i className={s[`forma_${TIPOS[t].forma}`]} style={{ background: TIPOS[t].cor }} aria-hidden />{TIPOS[t].rotulo}</span>)}
        <span><i className={s.linha} style={{ background: CORES_CLASSE.comprovada }} aria-hidden />Ligação comprovada (metadado → registro existente)</span>
        <span><i className={s.linha} style={{ background: CORES_CLASSE.referencia }} aria-hidden />Referência escrita (texto, não registro)</span>
        <span><i className={s.linha} style={{ background: CORES_CLASSE.proveniencia }} aria-hidden />Veio da fonte</span>
        <span className={s.nota}>Agrupamento ({AGRUPAMENTOS[agrupar]}) é só posição: não é relação nem projeto. Fontes sem contrato aparecem como lacuna.</span>
      </footer>
    </div>
  );
}

function Detalhes({ ativo, ligacoes, total, porId, brain, agrupar, contexto, onEscolher, onOpen }: {
  ativo: NoCerebro | null;
  ligacoes: ReturnType<typeof neighborsOf>;
  total: number;
  porId: Map<string, NoCerebro>;
  brain: SegundoCerebro;
  agrupar: Agrupamento;
  contexto: boolean;
  onEscolher: (id: string) => void;
  onOpen: (ref: string) => void;
}) {
  if (!ativo) {
    return (
      <aside className={s.details} aria-label="Detalhes do nó" aria-live="polite">
        <div className={s.invitation}><Network size={30} aria-hidden /><h4>Escolha um nó</h4><p>Veja de onde o registro veio e as ligações gravadas que o sustentam.</p><small>Posição e grupo são organização visual, não relevância nem vínculo.</small></div>
      </aside>
    );
  }
  const fonte = brain.sources.find((f) => f.id === ativo.fonte);
  return (
    <aside className={s.details} aria-label="Detalhes do nó" aria-live="polite">
      <p className={s.eyebrow}>{TIPOS[ativo.tipo].rotulo}{contexto ? " · vizinho (contexto)" : ""}</p>
      <h4>{ativo.rotuloCompleto ?? ativo.rotulo}</h4>
      <dl>
        <dt>Fonte</dt><dd>{fonte?.rotulo ?? ativo.fonte} · {fonte?.estado ?? "—"}{fonte?.codigo && fonte.codigo !== fonte.estado ? ` (${fonte.codigo})` : ""}</dd>
        {ativo.localizador && <><dt>Localizador</dt><dd>{ativo.localizador}</dd></>}
        {ativo.estado && <><dt>Estado</dt><dd>{ativo.estado}</dd></>}
        <dt>Grupo visual</dt><dd>{ativo.meta ?? ativo.fonte} <small>(por {AGRUPAMENTOS[agrupar].toLowerCase()}; não é relação)</small></dd>
        {ativo.tipo === "referencia" && <><dt>O que é</dt><dd>Texto escrito numa ligação ou link que não aponta para nenhum item da Pasta. Não é um registro verificado.</dd></>}
      </dl>
      {ativo.registro && ativo.tipo !== "referencia" && <button type="button" className={s.abrir} onClick={() => onOpen(ativo.id)}>Abrir o registro na página</button>}
      <h5>Ligações neste recorte ({ligacoes.length}{total !== ligacoes.length ? ` de ${total}` : ""})</h5>
      {ligacoes.length === 0 && <p>Nenhuma ligação visível. {total ? "Há ligações escondidas pelos filtros." : "Este registro não tem ligação gravada."}</p>}
      <ul className={s.related}>
        {ligacoes.map(({ edge, outro, direcao }) => (
          <li key={edge.id}>
            <button type="button" onClick={() => onEscolher(outro)}>{direcao === "saida" ? "→" : "←"} {porId.get(outro)?.rotuloCompleto ?? outro}</button>
            <p><span className={s[`classe_${edge.classe}`]}>{RELACOES[edge.relacao].rotulo}</span>{edge.rotulo ? ` · ${edge.rotulo}` : ""}</p>
            <small>Evidência: fonte {edge.evidencia.fonte}{edge.evidencia.registro ? ` · registro ${edge.evidencia.registro}` : ""} · campo {edge.evidencia.campo}{edge.evidencia.localizador ? ` · ${edge.evidencia.localizador}` : ""}</small>
          </li>
        ))}
      </ul>
    </aside>
  );
}

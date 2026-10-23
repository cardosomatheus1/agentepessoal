"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent, type WheelEvent } from "react";
import { Search } from "lucide-react";
import type { SegundoCerebro } from "@/lib/second-brain.mjs";
import { TIPOS, buildBrainGraph, filterBrainGraph, normalizar, type GrafoCerebro, type NoCerebro } from "@/lib/brain-graph.mjs";
import {
  MODOS, RAIO_ORBITA, layoutAneis, layoutDisco, layoutForca, ligacoesDoItem, maisPerto, projetar, type Modo, type Ponto,
} from "@/lib/constelacao.mjs";
import s from "./constelacao.module.css";

// A Constelação (23/10): a Pasta inteira num desenho só, no estilo que o Matheus pediu (vídeo de outro segundo cérebro).
// Três visões do mesmo grafo (lib/constelacao.mjs); o painel ao lado mostra o item escolhido e as ligações gravadas.
// Canvas 2D: ~1000 pontos sem biblioteca; o Mapa detalhado (BrainMap) continua para filtros e lista acessível.

const FUNDO = "#0d120f";
const ORBITA = "#33402f";
const NUCLEO = "#ffe066";
const RELACAO_ROTULO: Record<string, string> = {
  substitui: "substitui", liga: "ligação", wiki: "link no texto", ligacao_texto: "ligação escrita", link_sem_destino: "link", fonte_citada: "fonte citada",
};
const corDe = (n: NoCerebro) => TIPOS[n.tipo]?.cor ?? "#8e9a84";
const curto = (t: string, n = 34) => (t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t);
const semMovimento = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function hexagono(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = Math.PI / 6 + (i * Math.PI) / 3;
    ctx[i ? "lineTo" : "moveTo"](x + r * Math.cos(a), y + r * Math.sin(a));
  }
  ctx.closePath();
}

function etiqueta(ctx: CanvasRenderingContext2D, texto: string, x0: number, y: number, cor: string, largura: number) {
  ctx.font = "600 10px ui-monospace, SFMono-Regular, Menlo, monospace";
  const w = ctx.measureText(texto).width + 14;
  const x = Math.min(largura - w / 2 - 4, Math.max(w / 2 + 4, x0)); // sempre inteira dentro da tela
  ctx.fillStyle = "rgba(13, 18, 15, 0.85)";
  ctx.strokeStyle = cor;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(x - w / 2, y - 9, w, 18, 5);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = cor;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(texto, x, y + 0.5);
}

export default function Constelacao({ brain, area = "", onOpen }: { brain: SegundoCerebro; area?: string; onOpen: (ref: string) => void }) {
  const completo = useMemo(() => buildBrainGraph(brain), [brain]);
  const grafo = useMemo(() => (area ? filterBrainGraph(completo, { areas: new Set([area]) }) : completo), [completo, area]);
  const porId = useMemo(() => new Map(grafo.nodes.map((n) => [n.id, n])), [grafo]);
  const [modo, setModo] = useState<Modo>("disco");
  const [termo, setTermo] = useState("");
  const [escolhido, setEscolhido] = useState<string | null>(null);
  const [sobre, setSobre] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);
  const [forcaCalc, setForcaCalc] = useState<{ g: GrafoCerebro; pos: Map<string, Ponto> } | null>(null);

  const disco = useMemo(() => layoutDisco(grafo), [grafo]);
  const aneis = useMemo(() => layoutAneis(grafo), [grafo]);
  const forca = forcaCalc && forcaCalc.g === grafo ? forcaCalc.pos : null;
  useEffect(() => {
    // A Força custa uns segundos numa Pasta grande: calcula fora do clique, uma vez por Pasta.
    if (modo !== "forca" || forca) return;
    const t = window.setTimeout(() => setForcaCalc({ g: grafo, pos: layoutForca(grafo).posicoes }), 30);
    return () => window.clearTimeout(t);
  }, [grafo, modo, forca]);

  const casa = useMemo(() => {
    const t = normalizar(termo.trim());
    if (!t) return null;
    return new Set(grafo.nodes.filter((n) => normalizar(`${n.rotuloCompleto ?? n.rotulo} ${n.texto ?? ""}`).includes(t)).map((n) => n.id));
  }, [grafo, termo]);
  const contagem = useMemo(() => {
    const c = new Map<string, number>();
    for (const n of grafo.nodes) if (n.tipo !== "fonte") c.set(n.tipo, (c.get(n.tipo) ?? 0) + 1);
    return [...c.entries()].sort((a, b) => b[1] - a[1]);
  }, [grafo]);
  const ativo = escolhido ? porId.get(escolhido) ?? null : null;
  const ligacoes = useMemo(() => (ativo ? ligacoesDoItem(grafo, ativo.id) : null), [grafo, ativo]);
  const vizinhos = useMemo(() => new Set(ligacoes ? [...ligacoes.aponta, ...ligacoes.referenciado].map((l) => l.no.id) : []), [ligacoes]);

  const palco = useRef<HTMLCanvasElement>(null);
  const camera = useRef({ zoom: 1, x: 0, y: 0, giro: 0.6, inclinacao: 0.38 });
  const naTela = useRef(new Map<string, Ponto>());
  const arrasto = useRef<{ x: number; y: number; moveu: boolean } | null>(null);
  const estado = useRef({ modo, casa, escolhido, sobre, vizinhos, forca });
  useEffect(() => { estado.current = { modo, casa, escolhido, sobre, vizinhos, forca }; }, [modo, casa, escolhido, sobre, vizinhos, forca]);

  useEffect(() => {
    const canvas = palco.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let quadro = 0, vivo = true;
    const parado = semMovimento();
    const desenhar = (agora: number) => {
      if (!vivo) return;
      const { modo: m, casa: busca, escolhido: sel, sobre: hov, vizinhos: viz, forca: posForca } = estado.current;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth, h = canvas.clientHeight;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const cam = camera.current;
      const estreito = w < 640;
      const R = Math.min(w, h) * (estreito ? 0.44 : 0.42) * cam.zoom;
      const cx = w / 2 + cam.x, cy = h / 2 + cam.y;
      const fundo = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(w, h) * 0.7);
      fundo.addColorStop(0, "#17221a");
      fundo.addColorStop(1, FUNDO);
      ctx.fillStyle = fundo;
      ctx.fillRect(0, 0, w, h);
      if (m === "aneis" && !parado && !arrasto.current) cam.giro += 0.0018;

      const tela = new Map<string, Ponto>();
      const escalas = new Map<string, number>();
      if (m === "disco") {
        for (const [id, p] of disco.posicoes) tela.set(id, { x: cx + p.x * R, y: cy + p.y * R });
      } else if (m === "forca") {
        for (const [id, p] of posForca ?? disco.posicoes) tela.set(id, { x: cx + p.x * R, y: cy + p.y * R });
      } else {
        const profund: [string, number][] = [];
        for (const [id, p] of aneis.pontos) {
          const q = projetar(p, cam.giro, cam.inclinacao);
          tela.set(id, { x: cx + q.x * R, y: cy + q.y * R });
          escalas.set(id, q.escala);
          profund.push([id, q.profundidade]);
        }
        profund.sort((a, b) => b[1] - a[1]);
        const ordem = new Map<string, Ponto>();
        for (const [id] of profund) ordem.set(id, tela.get(id)!);
        tela.clear();
        for (const [id, p] of ordem) tela.set(id, p);
      }
      naTela.current = tela;

      // Molduras do disco: órbita, setores com etiqueta, hexágonos das fontes.
      if (m === "disco") {
        ctx.strokeStyle = ORBITA;
        ctx.lineWidth = 1;
        for (const r of [RAIO_ORBITA, 0.83]) { ctx.beginPath(); ctx.arc(cx, cy, r * R, 0, 2 * Math.PI); ctx.stroke(); }
        for (const st of disco.setores) {
          if (st.fim - st.inicio < (estreito ? 0.5 : 0.32)) continue; // setor estreito: o nome está na legenda ao lado
          const a = (st.inicio + st.fim) / 2;
          etiqueta(ctx, st.rotulo, cx + 0.83 * R * Math.cos(a), cy + 0.83 * R * Math.sin(a), TIPOS[st.tipo as keyof typeof TIPOS]?.cor ?? "#c6f432", w);
        }
      }
      // Ligações: todas (fracas) na Força; só as do item escolhido nas outras visões.
      const linha = (a: Ponto, b: Ponto, cor: string, larg: number) => {
        ctx.strokeStyle = cor;
        ctx.lineWidth = larg;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        if (m === "disco") ctx.quadraticCurveTo(cx + (a.x + b.x - 2 * cx) * 0.25, cy + (a.y + b.y - 2 * cy) * 0.25, b.x, b.y);
        else ctx.lineTo(b.x, b.y);
        ctx.stroke();
      };
      for (const e of grafo.edges) {
        const a = tela.get(e.de), b = tela.get(e.para);
        if (!a || !b) continue;
        const doFoco = sel && (e.de === sel || e.para === sel);
        if (doFoco && e.relacao !== "proveniencia") linha(a, b, "rgba(198, 244, 50, 0.75)", 1.4);
        else if (m === "forca" && !sel) linha(a, b, e.relacao === "proveniencia" ? "rgba(120, 140, 110, 0.06)" : "rgba(63, 224, 230, 0.16)", 0.7);
      }
      // Núcleo: o próprio Segundo Cérebro.
      const pulso = parado ? 1 : 1 + 0.08 * Math.sin(agora / 600);
      const nucleo = ctx.createRadialGradient(cx, cy, 0, cx, cy, 26 * pulso * Math.sqrt(cam.zoom));
      nucleo.addColorStop(0, "rgba(255, 224, 102, 0.95)");
      nucleo.addColorStop(0.35, "rgba(255, 224, 102, 0.35)");
      nucleo.addColorStop(1, "rgba(255, 224, 102, 0)");
      ctx.fillStyle = nucleo;
      ctx.beginPath(); ctx.arc(cx, cy, 26 * pulso * Math.sqrt(cam.zoom), 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = NUCLEO;
      ctx.beginPath(); ctx.arc(cx, cy, 5 * Math.sqrt(cam.zoom), 0, 2 * Math.PI); ctx.fill();

      // Pontos: halo somado (brilho) e miolo; a busca apaga o resto; o escolhido e os vizinhos acendem.
      ctx.globalCompositeOperation = "lighter";
      const base = Math.max(1.6, 2.3 * Math.sqrt(cam.zoom));
      for (const [id, p] of tela) {
        const n = porId.get(id);
        if (!n || n.tipo === "fonte") continue;
        const apagado = (busca && !busca.has(id)) || (sel && id !== sel && !viz.has(id));
        const k = (escalas.get(id) ?? 1) * (id === sel ? 2.4 : id === hov || viz.has(id) ? 1.7 : 1);
        const r = base * k;
        ctx.globalAlpha = apagado ? 0.08 : 0.22;
        ctx.fillStyle = corDe(n);
        ctx.beginPath(); ctx.arc(p.x, p.y, r * 2.6, 0, 2 * Math.PI); ctx.fill();
        ctx.globalAlpha = apagado ? 0.18 : m === "aneis" ? Math.min(1, 0.45 + 0.5 * (escalas.get(id) ?? 1)) : 0.95;
        ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 2 * Math.PI); ctx.fill();
      }
      ctx.globalCompositeOperation = "source-over";
      ctx.globalAlpha = 1;
      for (const [id, p] of tela) {
        const n = porId.get(id);
        if (!n || n.tipo !== "fonte") continue;
        ctx.shadowColor = "#3fe0e6";
        ctx.shadowBlur = 12;
        ctx.strokeStyle = id === sel ? "#c6f432" : "#7fe9ec";
        ctx.fillStyle = "rgba(13, 18, 15, 0.9)";
        ctx.lineWidth = 1.6;
        hexagono(ctx, p.x, p.y, 8 * Math.sqrt(cam.zoom) * (escalas.get(id) ?? 1));
        ctx.fill(); ctx.stroke();
        ctx.shadowBlur = 0;
        if (m !== "forca" && !estreito) {
          ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
          ctx.fillStyle = "#9fdfe0";
          ctx.textBaseline = "middle";
          const texto = curto(n.rotulo.toLocaleUpperCase("pt-BR"), 22);
          const larg = ctx.measureText(texto).width;
          const direita = p.x >= cx;
          const cabe = direita ? p.x + 14 + larg < w - 6 : p.x - 14 - larg > 6;
          if (cabe) { ctx.textAlign = direita ? "left" : "right"; ctx.fillText(texto, p.x + (direita ? 14 : -14), p.y); }
          else { ctx.textAlign = "center"; ctx.fillText(texto, Math.min(w - larg / 2 - 6, Math.max(larg / 2 + 6, p.x)), p.y + 18); }
        }
      }
      // Nome do item sob o mouse e do escolhido.
      for (const id of [hov, sel]) {
        const p = id ? tela.get(id) : null;
        const n = id ? porId.get(id) : null;
        if (p && n) etiqueta(ctx, curto(n.rotuloCompleto ?? n.rotulo, 46), p.x, p.y - 18, corDe(n), w);
      }
      quadro = requestAnimationFrame(desenhar);
    };
    quadro = requestAnimationFrame(desenhar);
    return () => { vivo = false; cancelAnimationFrame(quadro); };
  }, [disco, aneis, grafo, porId]);

  const ponto = (e: PointerEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const aoMover = (e: PointerEvent<HTMLCanvasElement>) => {
    const a = arrasto.current;
    if (a) {
      const dx = e.clientX - a.x, dy = e.clientY - a.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) a.moveu = true;
      const cam = camera.current;
      if (modo === "aneis") { cam.giro += dx * 0.006; cam.inclinacao = Math.max(-1.2, Math.min(1.2, cam.inclinacao + dy * 0.004)); }
      else { cam.x += dx; cam.y += dy; }
      a.x = e.clientX; a.y = e.clientY;
      return;
    }
    const p = ponto(e);
    setSobre(maisPerto(naTela.current, p.x, p.y, 10));
  };
  const aoSoltar = (e: PointerEvent<HTMLCanvasElement>) => {
    const a = arrasto.current;
    arrasto.current = null;
    if (a && !a.moveu) {
      const p = ponto(e);
      setEscolhido(maisPerto(naTela.current, p.x, p.y, 12));
      setCopiado(false);
    }
  };
  const aoRolar = (e: WheelEvent<HTMLCanvasElement>) => {
    const cam = camera.current;
    cam.zoom = Math.max(0.5, Math.min(6, cam.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
  };
  const teclas = (e: KeyboardEvent<HTMLCanvasElement>) => {
    const cam = camera.current;
    if (e.key === "Escape") setEscolhido(null);
    else if (e.key === "+" || e.key === "=") cam.zoom = Math.min(6, cam.zoom * 1.2);
    else if (e.key === "-") cam.zoom = Math.max(0.5, cam.zoom / 1.2);
    else if (e.key === "0") Object.assign(cam, { zoom: 1, x: 0, y: 0 });
  };
  const copiar = async () => {
    if (!ativo) return;
    try { await navigator.clipboard.writeText(ativo.rotuloCompleto ?? ativo.rotulo); setCopiado(true); } catch { setCopiado(false); }
  };

  return (
    <div className={s.root}>
      <div className={s.header}>
        <div>
          <p className={s.eyebrow}>Constelação{area ? ` · área ${area}` : ""}</p>
          <h3>Tudo o que está na Pasta</h3>
        </div>
        <div className={s.modos} role="group" aria-label="Visão">
          {(Object.keys(MODOS) as Modo[]).map((m) => (
            <button key={m} type="button" aria-pressed={modo === m} onClick={() => setModo(m)}>{MODOS[m].toLocaleUpperCase("pt-BR")}</button>
          ))}
        </div>
        <label className={s.busca}>
          <Search size={14} aria-hidden="true" />
          <input type="search" placeholder="Buscar na Pasta…" value={termo} onChange={(e) => setTermo(e.target.value)} />
          {casa && <small>{casa.size}</small>}
        </label>
      </div>
      <div className={s.area}>
        <div className={s.palcoWrap}>
          <canvas
            ref={palco}
            className={s.palco}
            tabIndex={0}
            role="img"
            aria-label={`Constelação da Pasta: ${grafo.nodes.length} itens em ${MODOS[modo]}. Clique num ponto para ver o item; arraste para ${modo === "aneis" ? "girar" : "mover"}; roda do mouse aproxima.`}
            onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); arrasto.current = { x: e.clientX, y: e.clientY, moveu: false }; }}
            onPointerMove={aoMover}
            onPointerUp={aoSoltar}
            onPointerLeave={() => setSobre(null)}
            onWheel={aoRolar}
            onKeyDown={teclas}
          />
          {modo === "forca" && !forca && <p className={s.aviso}>Arrumando os pontos…</p>}
          <p className={s.dica}>Clique num ponto · arraste para {modo === "aneis" ? "girar" : "mover"} · roda do mouse aproxima · Esc solta</p>
        </div>
        <aside className={s.painel} aria-live="polite">
          {ativo ? (
            <>
              <p className={s.tipo} style={{ color: corDe(ativo) }}>{TIPOS[ativo.tipo]?.rotulo ?? ativo.tipo}</p>
              <h4>{ativo.rotuloCompleto ?? ativo.rotulo}</h4>
              <dl>
                {ativo.fonte && <><dt>Fonte</dt><dd>{ativo.fonte}</dd></>}
                {ativo.area && <><dt>Área</dt><dd>{ativo.area}</dd></>}
                {ativo.estado && <><dt>Estado</dt><dd>{ativo.estado}</dd></>}
                {ativo.meta && <><dt>Detalhe</dt><dd>{ativo.meta}</dd></>}
              </dl>
              {ligacoes && (
                <>
                  <h5>Aponta para · {ligacoes.aponta.length}</h5>
                  <Lista itens={ligacoes.aponta} onEscolher={setEscolhido} />
                  <h5>Referenciado por · {ligacoes.referenciado.length}</h5>
                  <Lista itens={ligacoes.referenciado} onEscolher={setEscolhido} />
                </>
              )}
              <div className={s.acoes}>
                {ativo.registro && ativo.tipo !== "referencia" && ativo.tipo !== "fonte" && (
                  <button type="button" className={s.principal} onClick={() => onOpen(ativo.id)}>Abrir o registro</button>
                )}
                <button type="button" onClick={copiar}>{copiado ? "Copiado" : "Copiar o título"}</button>
              </div>
            </>
          ) : (
            <>
              <p className={s.tipo}>Na Pasta</p>
              <h4>{grafo.nodes.filter((n) => n.tipo !== "fonte").length} registros</h4>
              <ul className={s.legenda}>
                {contagem.map(([t, n]) => (
                  <li key={t}><span style={{ background: TIPOS[t as keyof typeof TIPOS]?.cor }} />{TIPOS[t as keyof typeof TIPOS]?.rotulo ?? t}<small>{n}</small></li>
                ))}
                <li><span className={s.hex} />Fontes de onde vieram<small>{grafo.nodes.filter((n) => n.tipo === "fonte").length}</small></li>
              </ul>
              <p className={s.muted}>Clique num ponto para ver o que ele é, de onde veio e com o que se liga.</p>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

function Lista({ itens, onEscolher }: { itens: { relacao: string; no: NoCerebro }[]; onEscolher: (id: string) => void }) {
  if (!itens.length) return <p className={s.muted}>Nenhuma.</p>;
  return (
    <ul className={s.ligacoes}>
      {itens.slice(0, 30).map(({ relacao, no }) => (
        <li key={`${relacao}-${no.id}`}>
          <button type="button" onClick={() => onEscolher(no.id)}>
            <span style={{ background: corDe(no) }} />{curto(no.rotuloCompleto ?? no.rotulo, 60)}<small>{RELACAO_ROTULO[relacao] ?? relacao}</small>
          </button>
        </li>
      ))}
      {itens.length > 30 && <li className={s.muted}>e mais {itens.length - 30}</li>}
    </ul>
  );
}

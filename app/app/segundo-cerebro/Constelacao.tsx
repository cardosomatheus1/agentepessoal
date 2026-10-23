"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import type { SegundoCerebro } from "@/lib/second-brain.mjs";
import { TIPOS, buildBrainGraph, filterBrainGraph, normalizar, type GrafoCerebro, type NoCerebro } from "@/lib/brain-graph.mjs";
import { MODOS, POSES, corDoTipo, ehHex, ligacoesDoItem, type Modo } from "@/lib/constelacao.mjs";
import { criarCena, type Motor } from "./constelacao-cena";
import s from "./constelacao.module.css";

// A Constelação (23/10): a Pasta inteira num desenho só, no estilo do vídeo que o Matheus mandou. WebGL (Three.js) com
// brilho de verdade (bloom), os itens voando entre as três poses (lib/constelacao.mjs) e o painel ao lado com o item
// escolhido e as ligações gravadas. Sem WebGL, avisa e o Mapa detalhado continua logo abaixo.

const RELACAO_ROTULO: Record<string, string> = {
  substitui: "substitui", liga: "ligação", wiki: "link no texto", ligacao_texto: "ligação escrita", link_sem_destino: "link", fonte_citada: "fonte citada",
};
const curto = (t: string, n = 34) => (t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t);
const corDe = (n: NoCerebro) => corDoTipo(n.tipo);

export default function Constelacao({ brain, area = "", onOpen }: { brain: SegundoCerebro; area?: string; onOpen: (ref: string) => void }) {
  const completo = useMemo(() => buildBrainGraph(brain), [brain]);
  const grafo: GrafoCerebro = useMemo(() => (area ? filterBrainGraph(completo, { areas: new Set([area]) }) : completo), [completo, area]);
  const porId = useMemo(() => new Map(grafo.nodes.map((n) => [n.id, n])), [grafo]);
  const [modo, setModo] = useState<Modo>("disco");
  const [termo, setTermo] = useState("");
  const [escolhido, setEscolhido] = useState<string | null>(null);
  const [sobre, setSobre] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);
  const [semWebgl, setSemWebgl] = useState(false);

  const casa = useMemo(() => {
    const t = normalizar(termo.trim());
    if (!t) return null;
    return new Set(grafo.nodes.filter((n) => normalizar(`${n.rotuloCompleto ?? n.rotulo} ${n.texto ?? ""}`).includes(t)).map((n) => n.id));
  }, [grafo, termo]);
  const contagem = useMemo(() => {
    const c = new Map<string, number>();
    for (const n of grafo.nodes) c.set(n.tipo, (c.get(n.tipo) ?? 0) + 1);
    return [...c.entries()].sort((a, b) => b[1] - a[1]);
  }, [grafo]);
  const ativo = escolhido ? porId.get(escolhido) ?? null : null;
  const ligacoes = useMemo(() => (ativo ? ligacoesDoItem(grafo, ativo.id) : null), [grafo, ativo]);

  const palco = useRef<HTMLDivElement>(null);
  const camadaRotulos = useRef<HTMLDivElement>(null);
  const motor = useRef<Motor | null>(null);
  const modoRef = useRef(modo);
  const realceRef = useRef({ escolhido, sobre, busca: casa });

  useEffect(() => {
    const el = palco.current, rot = camadaRotulos.current;
    if (!el || !rot) return;
    let vivo = true;
    const poses = { disco: POSES.disco(grafo), forca: POSES.forca(grafo), aneis: POSES.aneis(grafo) };
    criarCena({
      el, camadaRotulos: rot, grafo, poses,
      aoSobre: (id) => { if (vivo) setSobre(id); },
      aoEscolher: (id) => { if (vivo) { setEscolhido(id); setCopiado(false); } },
    })
      .then(
        (m) => {
          if (!vivo) { m.destruir(); return; }
          motor.current = m;
          m.irPara(modoRef.current, true);
          m.realcar(realceRef.current);
        },
        () => { if (vivo) setSemWebgl(true); }, // só quando a cena não nasce (sem WebGL)
      );
    return () => { vivo = false; motor.current?.destruir(); motor.current = null; };
  }, [grafo]);
  useEffect(() => { modoRef.current = modo; motor.current?.irPara(modo); }, [modo]);
  useEffect(() => { realceRef.current = { escolhido, sobre, busca: casa }; motor.current?.realcar(realceRef.current); }, [escolhido, sobre, casa]);

  const copiar = async () => {
    if (!ativo) return;
    try { await navigator.clipboard.writeText(ativo.rotuloCompleto ?? ativo.rotulo); setCopiado(true); } catch { setCopiado(false); }
  };
  const itensTotal = grafo.nodes.filter((n) => n.tipo !== "fonte").length;
  const nomeSobre = sobre && sobre !== escolhido ? porId.get(sobre) : null;

  return (
    <div className={s.root}>
      <div className={s.barra}>
        <div className={s.modos} role="group" aria-label="Visão">
          {(Object.keys(MODOS) as Modo[]).map((m) => (
            <button key={m} type="button" aria-pressed={modo === m} onClick={() => setModo(m)}>{MODOS[m].toLocaleUpperCase("pt-BR")}</button>
          ))}
        </div>
        <span className={s.titulo}>segundo cérebro{area ? ` · ${area}` : ""} · {itensTotal} registros</span>
        <label className={s.busca}>
          <Search size={13} aria-hidden="true" />
          <input type="search" placeholder="buscar na pasta" value={termo} onChange={(e) => setTermo(e.target.value)} />
          {casa && <small>{casa.size}</small>}
        </label>
      </div>
      <div className={s.area}>
        <div className={s.palcoWrap}>
          <div
            ref={palco}
            className={s.palco}
            tabIndex={0}
            role="img"
            aria-label={`Constelação da Pasta em ${MODOS[modo]}: ${grafo.nodes.length} itens. Clique num ponto para ver o item; arraste para ${modo === "aneis" ? "girar" : "mover"}; a roda do mouse aproxima.`}
            onKeyDown={(e) => { if (e.key === "Escape") setEscolhido(null); else motor.current?.tecla(e.key); }}
          />
          <div ref={camadaRotulos} className={s.rotulos} aria-hidden="true" />
          {semWebgl && <p className={s.aviso}>Este navegador não desenha WebGL. O Mapa detalhado, logo abaixo, mostra a mesma Pasta.</p>}
          {nomeSobre && <p className={s.dicaItem}><span style={{ color: corDe(nomeSobre) }} />{curto(nomeSobre.rotuloCompleto ?? nomeSobre.rotulo, 70)}</p>}
          <p className={s.dica}>clique num ponto · arraste para {modo === "aneis" ? "girar" : "mover"} · roda aproxima · esc solta</p>
        </div>
        <aside className={s.painel} aria-live="polite">
          {ativo ? (
            <>
              <p className={s.olho}><span className={s.quad} style={{ color: corDe(ativo) }} />no item</p>
              <h4>{ativo.rotuloCompleto ?? ativo.rotulo}</h4>
              <p className={s.chips}>
                <span style={{ borderColor: corDe(ativo), color: corDe(ativo) }}>{(TIPOS[ativo.tipo]?.rotulo ?? ativo.tipo).toLowerCase()}</span>
                {ativo.area && <span>{ativo.area}</span>}
              </p>
              <dl className={s.campos}>
                {ativo.fonte && <><dt>fonte</dt><dd>{ativo.fonte}</dd></>}
                {ativo.estado && <><dt>estado</dt><dd>{ativo.estado}</dd></>}
                {ativo.meta && <><dt>detalhe</dt><dd>{ativo.meta}</dd></>}
              </dl>
              {ligacoes && (
                <>
                  <p className={s.olho}>aponta para · {ligacoes.aponta.length}</p>
                  <Lista itens={ligacoes.aponta} onEscolher={setEscolhido} />
                  <p className={s.olho}>referenciado por · {ligacoes.referenciado.length}</p>
                  <Lista itens={ligacoes.referenciado} onEscolher={setEscolhido} />
                </>
              )}
              <div className={s.acoes}>
                {ativo.registro && ativo.tipo !== "referencia" && ativo.tipo !== "fonte" && (
                  <button type="button" onClick={() => onOpen(ativo.id)}>abrir o registro</button>
                )}
                <button type="button" onClick={copiar}>{copiado ? "copiado" : "copiar o título"}</button>
              </div>
            </>
          ) : (
            <>
              <p className={s.olho}>na pasta</p>
              <h4>{itensTotal} registros</h4>
              <ul className={s.legenda}>
                {contagem.map(([t, n]) => (
                  <li key={t}>
                    <span className={ehHex({ tipo: t } as NoCerebro) ? s.hex : s.ponto} style={{ color: corDoTipo(t) }} />
                    {TIPOS[t as keyof typeof TIPOS]?.rotulo ?? t}<small>{n}</small>
                  </li>
                ))}
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
  if (!itens.length) return <p className={s.muted}>nenhuma</p>;
  return (
    <ul className={s.ligacoes}>
      {itens.slice(0, 30).map(({ relacao, no }) => (
        <li key={`${relacao}-${no.id}`}>
          <button type="button" onClick={() => onEscolher(no.id)}>
            <span style={{ color: corDe(no) }} />{curto(no.rotuloCompleto ?? no.rotulo, 60)}<small>{RELACAO_ROTULO[relacao] ?? relacao}</small>
          </button>
        </li>
      ))}
      {itens.length > 30 && <li className={s.muted}>e mais {itens.length - 30}</li>}
    </ul>
  );
}

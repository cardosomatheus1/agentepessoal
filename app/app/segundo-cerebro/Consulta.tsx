"use client";

import { useMemo, useState, type FormEvent } from "react";
import type { SegundoCerebro } from "@/lib/second-brain.mjs";
import { FONTES, FUNCOES, consultar, roteiro, verificar, type Consulta as Pedido, type Etapa, type Funcao, type ResultadoConsulta, type Verificacao } from "@/lib/brain-query.mjs";
import s from "./consulta.module.css";

// Cada consulta relê a Pasta pela API (nenhum endpoint novo) e confere de novo no fim.
type Rodada = { resultado: ResultadoConsulta; etapas: Etapa[]; verificacao: Verificacao | null };

const ROTULO_ETAPA: Record<Etapa["etapa"], string> = { captura: "Captura", validacao: "Validação", consulta: "Consulta", execucao: "Execução", verificacao: "Verificação" };

export default function Consulta({ brain, area, recarregar, onOpen }: { brain: SegundoCerebro; area: string; recarregar: () => Promise<SegundoCerebro | null>; onOpen: (ref: string) => void }) {
  const [funcao, setFuncao] = useState<Funcao>("retomar");
  const [termo, setTermo] = useState("");
  const [registro, setRegistro] = useState("");
  const [fonte, setFonte] = useState("");
  const [rodada, setRodada] = useState<Rodada | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  // Sugestões só de metadado explícito: prefixo do tema das decisões vigentes.
  const temas = useMemo(() => [...new Set(brain.decisions.filter((d) => d.vigente && d.tema).map((d) => d.tema!.split(".")[0]))].sort(), [brain]);
  const registros = useMemo(() => {
    const op: [string, string][] = [];
    for (const a of brain.subjects) op.push([`assunto:${a.id}`, `Assunto: ${a.titulo}`]);
    for (const c of brain.contexts) op.push([`contexto:${c.id}`, `Contexto: ${c.titulo}`]);
    for (const p of brain.projects) op.push([`projeto:${p.id}`, `Projeto: ${p.titulo}`]);
    for (const f of brain.threads) op.push([`pendencia:${f.id}`, `Pendência: ${f.titulo ?? f.id}`]);
    for (const d of brain.decisions) op.push([`decisao:${d.id}`, `Decisão ${d.id}: ${d.tema ?? ""}`]);
    for (const m of brain.meetings) op.push([`reuniao:${m.id}`, `Reunião: ${m.titulo}`]);
    for (const d of brain.documents) op.push([`documento:${d.id}`, `Documento: ${d.titulo}`]);
    return op;
  }, [brain]);

  async function rodar(pedido: Pedido) {
    setOcupado(true);
    setErro(null);
    try {
      const carga = await recarregar();
      if (!carga) { setErro("Não foi possível reler a Pasta agora."); return; }
      const r = consultar(carga, pedido);
      if (!r.ok) { setErro(r.erro); setRodada(null); return; }
      const etapas = roteiro(carga, r);
      setRodada({ resultado: r, etapas, verificacao: null });
      const recarga = await recarregar();
      if (recarga) {
        const v = verificar(r, recarga);
        setRodada({ resultado: r, etapas: etapas.map((e) => (e.etapa === "verificacao" ? { ...e, estado: v.estado, detalhe: `${e.detalhe} ${v.detalhe}`, evidencias: v.fontes.map((f) => `${f.id}: ${f.antes ?? "—"} → ${f.depois ?? "—"}${f.igual ? " (igual)" : " (mudou)"}`) } : e)), verificacao: v });
      }
    } finally {
      setOcupado(false);
    }
  }
  function enviar(e: FormEvent) {
    e.preventDefault();
    const pedido: Pedido = { funcao };
    if (termo.trim()) pedido.termo = termo.trim();
    if (registro) pedido.registro = registro;
    if (fonte) pedido.fonte = fonte;
    if (area) pedido.area = area;
    void rodar(pedido);
  }
  // Fluxo A parte do tema (campo explícito) da decisão vigente mais recente; o termo pode ser trocado no formulário.
  const temaRecente = [...brain.decisions].filter((d) => d.vigente && d.tema).sort((a, b) => String(b.em ?? "").localeCompare(String(a.em ?? "")))[0]?.tema?.split(".")[0] ?? "";

  return (
    <div className={s.root}>
      <p className={s.nota}>Só leitura. Cada consulta relê a Pasta, monta o roteiro <b>captura → validação → consulta → execução → verificação</b> e relê de novo para verificar. Nada é enviado, gravado ou agendado.</p>
      <div className={s.fluxos} role="group" aria-label="Fluxos prontos">
        <button type="button" disabled={ocupado || !temaRecente} onClick={() => { setFuncao("retomar"); setTermo(temaRecente); setRegistro(""); setFonte(""); void rodar({ funcao: "retomar", termo: temaRecente, ...(area ? { area } : {}) }); }}>
          <strong>A · Retomar</strong><span>{temaRecente ? `Tema “${temaRecente}” (decisão vigente mais recente): assuntos, contexto, decisões e pendências em aberto.` : "Sem decisão vigente com tema."}</span>
        </button>
        <button type="button" disabled={ocupado} onClick={() => { setFuncao("assuntos"); setTermo(""); setRegistro(""); setFonte(""); void rodar({ funcao: "assuntos", ...(area ? { area } : {}) }); }}>
          <strong>B · Onde parou</strong><span>Assuntos em andamento, do mais recente, com o ponto onde pararam.</span>
        </button>
        <button type="button" disabled={ocupado} onClick={() => { setFuncao("prioridades"); setTermo(""); setRegistro(""); setFonte(""); void rodar({ funcao: "prioridades", ...(area ? { area } : {}) }); }}>
          <strong>C · Prioridades e pauta</strong><span>Pendências em aberto por prioridade e prazo, com os limites vigentes.</span>
        </button>
      </div>

      <form className={s.form} onSubmit={enviar} aria-label="Consulta seletiva">
        <label>Função<select value={funcao} onChange={(e) => setFuncao(e.target.value as Funcao)}>{(Object.keys(FUNCOES) as Funcao[]).map((f) => <option key={f} value={f}>{FUNCOES[f]}</option>)}</select></label>
        <label>Termo<input value={termo} maxLength={80} list="sc-temas" placeholder="ex.: um tema" onChange={(e) => setTermo(e.target.value)} /></label>
        <datalist id="sc-temas">{temas.map((t) => <option key={t} value={t} />)}</datalist>
        <label>Registro<select value={registro} onChange={(e) => setRegistro(e.target.value)}><option value="">(nenhum)</option>{registros.map(([v, r]) => <option key={v} value={v}>{r.length > 70 ? `${r.slice(0, 69)}…` : r}</option>)}</select></label>
        <label>Fonte<select value={fonte} onChange={(e) => setFonte(e.target.value)}><option value="">(nenhuma)</option>{FONTES.map((f) => <option key={f} value={f}>{brain.sources.find((x) => x.id === f)?.rotulo ?? f}</option>)}</select></label>
        <button type="submit" className={s.prim} disabled={ocupado}>{ocupado ? "Relendo a Pasta…" : "Consultar"}{area ? ` (área ${area})` : ""}</button>
      </form>

      {erro && <p className={s.erro} role="alert">{erro}</p>}
      {rodada && <Resultado rodada={rodada} onOpen={onOpen} />}
    </div>
  );
}

function Resultado({ rodada, onOpen }: { rodada: Rodada; onOpen: (ref: string) => void }) {
  const { resultado: r, etapas, verificacao } = rodada;
  return (
    <section className={s.resultado} aria-label="Resultado da consulta" data-estado={r.estado} data-funcao={r.consulta.funcao} data-carga={r.carregadoEm} data-verificacao={verificacao?.estado ?? "pendente"}>
      <header>
        <p className={s.kicker}>{r.rotulo} · <span className={s[`estado_${r.estado}`]}>{r.estado}</span></p>
        <h3>{r.resumo}</h3>
      </header>
      {r.bloqueios.length > 0 && (
        <ul className={s.bloqueios} aria-label="Bloqueios">{r.bloqueios.map((b, i) => <li key={i}>{b.motivo}</li>)}</ul>
      )}
      {r.conflitos.length > 0 && <ul className={s.bloqueios} aria-label="Diagnósticos">{r.conflitos.map((c, i) => <li key={i}>Diagnóstico (não autoritativo): {c.detalhe}</li>)}</ul>}
      <ol className={s.etapas} aria-label="Roteiro">
        {etapas.map((e) => (
          <li key={e.etapa} data-etapa={e.etapa} data-estado={e.estado}>
            <strong>{ROTULO_ETAPA[e.etapa]}</strong> <span className={s.badge}>{e.estado.replace("_", " ")}</span>
            <p>{e.detalhe}</p>
            {e.aprovacoes && e.aprovacoes.length > 0 && (
              <details><summary>Regras vigentes que limitam a execução ({e.aprovacoes.length})</summary><ul>{e.aprovacoes.map((a, i) => <li key={i}><button type="button" className={s.ref} onClick={() => onOpen(a.ref)}>{a.ref}</button> {a.texto}</li>)}</ul></details>
            )}
            {e.proposta && e.proposta.length > 0 && <div className={s.proposta}><span>Proposta (não executada)</span><ul>{e.proposta.map((p, i) => <li key={i}>{p}</li>)}</ul>{e.entrega && <p><b>Entrega:</b> {e.entrega}</p>}</div>}
            {e.evidencias && e.evidencias.length > 0 && e.etapa !== "consulta" && <ul className={s.evid}>{e.evidencias.map((x, i) => <li key={i}>{x}</li>)}</ul>}
          </li>
        ))}
      </ol>
      <h4>Registros usados ({r.itens.length})</h4>
      <ul className={s.itens}>
        {r.itens.map((i) => (
          <li key={i.ref} data-ref={i.ref}>
            <div className={s.itemTopo}><span className={s.tipo}>{i.tipo}{i.area ? ` · ${i.area}` : ""}</span>{i.ref.startsWith("referencia:") ? <span>{i.rotulo}</span> : <button type="button" className={s.ref} onClick={() => onOpen(i.ref)}>{i.rotulo}</button>}</div>
            {i.trecho && <p>{i.trecho}</p>}
            <small>Por quê: {i.porque}{i.proveniencia?.localizador ? ` · origem: ${i.proveniencia.fonteRotulo ?? i.proveniencia.fonte} — ${i.proveniencia.localizador}` : ""}</small>
          </li>
        ))}
      </ul>
    </section>
  );
}

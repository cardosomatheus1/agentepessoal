"use client";

import { useMemo, useState, type ReactNode } from "react";
import type { Assunto, Decisao, Fio, Fonte, Nota, Proveniencia, Secao as SecaoNota, SegundoCerebro } from "@/lib/second-brain.mjs";
import s from "./segundo-cerebro.module.css";

// Todo conteúdo vindo do servidor é exibido como texto (React escapa); nada de HTML cru.
// `area` vem do filtro global da página ("" = todas). `onOpen` segue uma referência (tipo:id) até o cartão.

export const ancora = (ref: string) => `reg-${ref.replace(/[^A-Za-z0-9_-]/g, "_")}`;
const PRIORIDADE: Record<string, number> = { urgente: 0, alta: 1, media: 2, média: 2, normal: 3, baixa: 4 };
type Props = { b: SegundoCerebro; area: string; onOpen: (ref: string) => void };

export function fmt(d: string | null | undefined) {
  if (!d) return "—";
  const t = new Date(d);
  if (Number.isNaN(t.getTime())) return d;
  const soData = /^\d{4}-\d{2}-\d{2}$/.test(d);
  return t.toLocaleString("pt-BR", soData ? { dateStyle: "medium", timeZone: "UTC" } : { dateStyle: "medium", timeStyle: "short" });
}

function uniq(xs: (string | null)[]) {
  return [...new Set(xs.filter((x): x is string => !!x))].sort((a, c) => a.localeCompare(c, "pt-BR"));
}
const naArea = (area: string) => (x: { area?: string | null }) => !area || x.area === area;

export function Origem({ p, rotuloData = "Registrado em" }: { p: Proveniencia; rotuloData?: string }) {
  return (
    <dl className={s.prov}>
      <div><dt>Fonte</dt><dd>{p.fonteRotulo}</dd></div>
      {p.localizador && <div><dt>Arquivo na Pasta</dt><dd>{p.localizador}</dd></div>}
      {p.origem && <div><dt>Origem</dt><dd>{p.origem}</dd></div>}
      {p.em !== undefined && <div><dt>{rotuloData}</dt><dd>{fmt(p.em)}</dd></div>}
      <div><dt>Dono</dt><dd>{p.dono}</dd></div>
      <div><dt>Arquivo atualizado</dt><dd>{fmt(p.arquivoAtualizadoEm)}</dd></div>
    </dl>
  );
}

export function Vazio({ fonte, texto }: { fonte?: Fonte; texto: string }) {
  if (fonte?.estado === "indisponivel") return <p className={s.vazio}>Fonte indisponível ({fonte.codigo}) — veja os avisos acima.</p>;
  return <p className={s.vazio}>{texto}</p>;
}

function Secao({ id, titulo, children, nota }: { id: string; titulo: string; children: ReactNode; nota?: ReactNode }) {
  return (
    <section id={id} className={s.secao}>
      <h2 className={s.h2}>{titulo}</h2>
      {nota && <p className={s.muted}>{nota}</p>}
      {children}
    </section>
  );
}

const fonteDe = (b: SegundoCerebro, id: string) => b.sources.find((x) => x.id === id);
const Area = ({ area }: { area?: string | null }) => (area ? <span className={s.tagCiano}>área: {area}</span> : null);

// Texto com [[links]] da Pasta: o link vira botão que abre o item (se ele está na Pasta), senão fica como texto.
export function TextoPasta({ t, b, onOpen }: { t: string; b: SegundoCerebro; onOpen: (ref: string) => void }) {
  const partes = t.split(/(\[\[[^\]\n]{1,200}\]\])/g);
  return (
    <>
      {partes.map((x, i) => {
        const m = /^\[\[([^\]|#]+)(?:[|#]([^\]]*))?\]\]$/.exec(x);
        if (!m) return <span key={i}>{x}</span>;
        const alvo = m[1].trim();
        const ref = b.index[alvo];
        const nome = m[2]?.trim() || alvo.split("/").pop();
        return ref ? <button key={i} type="button" className={s.refBtn} onClick={() => onOpen(ref)}>{nome}</button> : <span key={i}>{nome}</span>;
      })}
    </>
  );
}

// Ligações gravadas de um item (liga e [[links]]), nos dois sentidos.
function Ligacoes({ refItem, b, onOpen }: { refItem: string; b: SegundoCerebro; onOpen: (ref: string) => void }) {
  const lig = b.links.filter((l) => l.de === refItem || l.para === refItem);
  if (!lig.length) return null;
  return (
    <div className={s.fontesFio}><span>Ligações</span>
      <ul>{lig.map((l, i) => {
        const outro = l.de === refItem ? l.para : l.de;
        return <li key={i}>{l.resolvido ? <button type="button" className={s.refBtn} onClick={() => onOpen(outro)}>{outro}</button> : <>{l.alvo} <small>(fora da Pasta)</small></>} <small>{l.de === refItem ? "→" : "←"} {l.vias.join(" + ")}</small></li>;
      })}</ul>
    </div>
  );
}

function Secoes({ secoes, b, onOpen }: { secoes: SecaoNota[]; b: SegundoCerebro; onOpen: (ref: string) => void }) {
  return (
    <>
      {secoes.map((x, i) => (
        <div key={i}>
          {x.titulo && <h4 className={s.h3}>{x.titulo}</h4>}
          <ul className={s.itensCtx}>{x.itens.map((t, j) => <li key={j}><TextoPasta t={t} b={b} onOpen={onOpen} /></li>)}</ul>
        </div>
      ))}
    </>
  );
}

export function Contextos({ b, onOpen }: Props) {
  const validados = b.contexts.filter((c) => c.estado === "validado").length;
  return (
    <Secao id="contexto" titulo="Contexto" nota={`${validados} de ${b.contexts.length} seções validadas pelo Matheus. Pendente = a entrevista ainda não preencheu (nada é inventado).`}>
      {b.contexts.length === 0 ? <Vazio fonte={fonteDe(b, "contexto")} texto="Nenhuma seção de contexto na Pasta." /> : (
        <ul className={s.cartoes}>
          {b.contexts.map((c) => (
            <li key={c.id} id={ancora(`contexto:${c.id}`)} className={`${s.cartao} ${c.estado === "pendente" ? s.apagado : ""}`} tabIndex={-1} data-estado={c.estado}>
              <div className={s.etiquetas}><span className={c.estado === "validado" ? s.tagLima : s.tagCinza}>{c.estado === "validado" ? "validado" : "pendente de validação"}</span>{c.validadoEm && <span className={s.tagCinza}>{fmt(c.validadoEm)}</span>}</div>
              <h3 className={s.h3}>{c.titulo}</h3>
              {c.secoes.length ? <Secoes secoes={c.secoes} b={b} onOpen={onOpen} /> : c.resumo && <p className={s.corpo}>{c.resumo}</p>}
              {c.aprovado && <p className={s.muted}>Ok dele: “{c.aprovado}”</p>}
              <Ligacoes refItem={`contexto:${c.id}`} b={b} onOpen={onOpen} />
              <Origem p={c.proveniencia} />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

export function Assuntos({ b, area, onOpen }: Props) {
  const [todos, setTodos] = useState(false);
  const lista = useMemo(() => b.subjects.filter(naArea(area)).filter((a) => todos || a.emAndamento).sort((x, y) => Number(y.emAndamento) - Number(x.emAndamento) || String(y.atualizado ?? "").localeCompare(String(x.atualizado ?? ""))), [b, area, todos]);
  return (
    <Secao id="assuntos" titulo="Assuntos (onde parou)" nota="Temas em discussão com o agente, com o ponto onde pararam. Um assunto pode virar decisão, gerar pendências ou ficar parado.">
      <div className={s.filtros}><label className={s.muted}><input type="checkbox" checked={todos} onChange={() => setTodos(!todos)} /> Mostrar também os encerrados</label></div>
      {lista.length === 0 ? <Vazio fonte={fonteDe(b, "assuntos")} texto={b.subjects.length ? "Nenhum assunto em andamento com esse filtro." : "Nenhum assunto registrado."} /> : (
        <ul className={s.cartoes}>
          {lista.map((a: Assunto) => (
            <li key={a.id} id={ancora(`assunto:${a.id}`)} className={`${s.cartao} ${a.emAndamento ? "" : s.apagado}`} tabIndex={-1}>
              <div className={s.etiquetas}><span className={a.estado === "andamento" ? s.tagLima : s.tagCinza}>{a.estado}</span><Area area={a.area} /></div>
              <h3 className={s.h3}>{a.titulo}</h3>
              <p className={s.passo}><span>Onde parou</span>{a.onde_parou ?? "(ainda nada)"}</p>
              {a.historico.length > 0 && <details className={s.mais}><summary>Histórico ({a.historico.length})</summary><ul>{a.historico.map((h, i) => <li key={i}>{fmt(h.em)}: {h.nota}</li>)}</ul></details>}
              <Ligacoes refItem={`assunto:${a.id}`} b={b} onOpen={onOpen} />
              <p className={s.datas}>Desde {fmt(a.criado)} · atualizado {fmt(a.atualizado)}</p>
              <Origem p={a.proveniencia} rotuloData="Última atualização" />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

export function Decisoes({ b, area, onOpen }: Props) {
  const lista = useMemo(() => b.decisions.filter(naArea(area)), [b, area]);
  const [busca, setBusca] = useState("");
  const [tipo, setTipo] = useState("");
  const [estado, setEstado] = useState("");
  const tipos = useMemo(() => uniq(lista.map((d) => d.tipo)), [lista]);
  const estados = useMemo(() => uniq(lista.map((d) => d.estadoEfetivo)), [lista]);
  const filtradas = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return lista.filter((d: Decisao) => (!tipo || d.tipo === tipo) && (!estado || d.estadoEfetivo === estado) && (!q || [d.tema, d.valor, d.citacao, d.origem].some((x) => x?.toLowerCase().includes(q))));
  }, [lista, busca, tipo, estado]);
  return (
    <Secao id="decisoes" titulo="Decisões" nota="Vigente = ativa e dentro da validade. Substituídas e revogadas ficam visíveis como histórico, apagadas.">
      <div className={s.filtros}>
        <input className={s.busca} placeholder="Buscar em tema, valor, citação…" value={busca} onChange={(e) => setBusca(e.target.value)} aria-label="Buscar decisões" />
        <select value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Tipo"><option value="">Todos os tipos</option>{tipos.map((t) => <option key={t} value={t}>{t}</option>)}</select>
        <select value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado"><option value="">Todos os estados</option>{estados.map((t) => <option key={t} value={t}>{t}</option>)}</select>
      </div>
      {filtradas.length === 0 ? <Vazio fonte={lista.length ? undefined : fonteDe(b, "decisoes")} texto={lista.length ? "Nada encontrado com esses filtros." : "Nenhuma decisão registrada."} /> : (
        <ul className={s.cartoes}>
          {filtradas.map((d) => (
            <li key={d.id} id={ancora(`decisao:${d.id}`)} className={`${s.cartao} ${d.vigente ? "" : s.apagado}`} tabIndex={-1}>
              <div className={s.etiquetas}>
                <span className={s.tagCinza}>#{d.id}</span>
                {d.tipo && <span className={s.tag}>{d.tipo}</span>}
                <span className={d.vigente ? s.tagLima : s.tagCinza}>{d.estadoEfetivo}</span>
                <Area area={d.area} />
                {d.valido_ate && <span className={s.tagCinza}>válida até {fmt(d.valido_ate)}</span>}
                {d.substitui && <a className={s.tagCiano} href={`#${ancora(`decisao:${d.substitui}`)}`}>substitui #{d.substitui}</a>}
                {d.substituida_por && <a className={s.tagCiano} href={`#${ancora(`decisao:${d.substituida_por}`)}`}>substituída por #{d.substituida_por}</a>}
              </div>
              <h3 className={s.h3}>{d.tema ?? "(sem tema)"}</h3>
              {d.valor && <p className={s.corpo}>{d.valor}</p>}
              {d.citacao && <blockquote className={s.citacao}>“{d.citacao}”</blockquote>}
              {d.motivo && <p className={s.muted}>Motivo do fim: {d.motivo}</p>}
              <Ligacoes refItem={`decisao:${d.id}`} b={b} onOpen={onOpen} />
              <Origem p={d.proveniencia} />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

export function Pendencias({ b, area, onOpen }: Props) {
  const lista = useMemo(() => b.threads.filter(naArea(area)), [b, area]);
  const [prioridade, setPrioridade] = useState("");
  const [estado, setEstado] = useState("");
  const prioridades = useMemo(() => uniq(lista.map((f) => f.prioridade)), [lista]);
  const estados = useMemo(() => uniq(lista.map((f) => f.estado)), [lista]);
  const filtrados = useMemo(() => lista.filter((f: Fio) => (!prioridade || f.prioridade === prioridade) && (!estado || f.estado === estado)).sort((a, c) => {
    if (a.emAberto !== c.emAberto) return a.emAberto ? -1 : 1;
    const pa = PRIORIDADE[(a.prioridade ?? "").toLowerCase()] ?? 9;
    const pb = PRIORIDADE[(c.prioridade ?? "").toLowerCase()] ?? 9;
    return pa - pb || (a.prazo ?? "9999").localeCompare(c.prazo ?? "9999");
  }), [lista, prioridade, estado]);
  return (
    <Secao id="pendencias" titulo="Pendências" nota="O que falta fazer. Em aberto = aberta, ou adiada cuja data já chegou. “Quem age” é quem faz, não um papel confirmado.">
      <div className={s.filtros}>
        <select value={prioridade} onChange={(e) => setPrioridade(e.target.value)} aria-label="Prioridade"><option value="">Todas as prioridades</option>{prioridades.map((t) => <option key={t} value={t}>{t}</option>)}</select>
        <select value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Situação"><option value="">Todas as situações</option>{estados.map((t) => <option key={t} value={t}>{t}</option>)}</select>
      </div>
      {filtrados.length === 0 ? <Vazio fonte={lista.length ? undefined : fonteDe(b, "pendencias")} texto={lista.length ? "Nada encontrado com esses filtros." : "Nenhuma pendência registrada."} /> : (
        <ul className={s.cartoes}>
          {filtrados.map((f) => (
            <li key={f.id} id={ancora(`pendencia:${f.id}`)} className={`${s.cartao} ${f.emAberto ? "" : s.apagado}`} tabIndex={-1}>
              <div className={s.etiquetas}>
                <span className={f.emAberto ? s.tagLima : s.tagCinza}>{f.emAberto ? "em aberto" : f.estado ?? "—"}</span>
                <Area area={f.area} />
                {f.prioridade && <span className={s.tagCiano}>{f.prioridade}</span>}
                {f.prazo && <span className={s.tag}>prazo {fmt(f.prazo)}</span>}
                {f.adiar_ate && <span className={s.tagCinza}>adiado até {f.adiar_ate}</span>}
                {f.dono && <span className={s.tagCinza}>quem age: {f.dono}</span>}
              </div>
              <h3 className={s.h3}>{f.titulo ?? f.id}</h3>
              {f.proximo_passo && <p className={s.passo}><span>Próximo passo</span>{f.proximo_passo}</p>}
              {f.detalhe && <p className={s.corpo}>{f.detalhe}</p>}
              {f.fontes.length > 0 && <div className={s.fontesFio}><span>Fontes citadas</span><ul>{f.fontes.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
              <Ligacoes refItem={`pendencia:${f.id}`} b={b} onOpen={onOpen} />
              <p className={s.datas}>Criada {fmt(f.criado)} · atualizada {fmt(f.atualizado)}</p>
              <Origem p={f.proveniencia} rotuloData="Última data" />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

export function Ficha({ b }: { b: SegundoCerebro }) {
  const f = fonteDe(b, "perfil");
  return (
    <Secao id="perfil" titulo="Perfil (ficha)" nota="Contexto/perfil.md, mantido pela ferramenta ficha. O número é a referência que a ferramenta usa; não é um id estável.">
      {b.profile.length === 0 ? <Vazio fonte={f} texto={f?.codigo === "pendente" ? "Perfil pendente de validação: a entrevista ainda não preencheu." : "Nenhum fato no perfil."} /> : (
        <ul className={s.cartoes}>
          {b.profile.map((x) => (
            <li key={x.id} id={ancora(`fato:${x.id}`)} className={s.cartao} tabIndex={-1}>
              <div className={s.etiquetas}><span className={s.tagCinza}>entrada {x.numero}</span></div>
              <p className={s.corpo}>{x.texto}</p>
              <Origem p={x.proveniencia} />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

function Notas({ id, tipo, titulo, nota, lista, fonte, vazio, b, onOpen, abertas = false }: { id: string; tipo: string; titulo: string; nota: string; lista: Nota[]; fonte?: Fonte; vazio: string; b: SegundoCerebro; onOpen: (ref: string) => void; abertas?: boolean }) {
  return (
    <Secao id={id} titulo={titulo} nota={nota}>
      {lista.length === 0 ? <Vazio fonte={fonte} texto={vazio} /> : (
        <ul className={s.cartoes}>
          {lista.map((n, i) => (
            <li key={n.id} id={ancora(`${tipo}:${n.id}`)} className={s.cartao} tabIndex={-1}>
              <div className={s.etiquetas}>{n.data && <span className={s.tagCinza}>{fmt(n.data)}</span>}<Area area={n.area} /></div>
              <h3 className={s.h3}>{n.titulo}</h3>
              <details className={s.mais} open={abertas && i === 0}><summary>{n.resumo ? n.resumo.slice(0, 120) : "Abrir"}</summary><Secoes secoes={n.secoes} b={b} onOpen={onOpen} /></details>
              <Ligacoes refItem={`${tipo}:${n.id}`} b={b} onOpen={onOpen} />
              <Origem p={n.proveniencia} />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

export function NotasDoDia({ b, area, onOpen }: Props) {
  return <Notas id="notas" tipo="nota" titulo="Notas do dia" nota="Uma por dia, escrita pelo agente às 20h; a mais recente primeiro." lista={b.daily.filter(naArea(area))} fonte={fonteDe(b, "notas")} vazio="Nenhuma nota do dia ainda." b={b} onOpen={onOpen} abertas />;
}
export function Reunioes({ b, area, onOpen }: Props) {
  return <Notas id="reunioes" tipo="reuniao" titulo="Reuniões" nota="Resumo de cada reunião, com decisões e próximos passos; a mais recente primeiro." lista={b.meetings.filter(naArea(area))} fonte={fonteDe(b, "reunioes")} vazio="Nenhuma reunião registrada." b={b} onOpen={onOpen} />;
}
export function Documentos({ b, area, onOpen }: Props) {
  return <Notas id="documentos" tipo="documento" titulo="Documentos" nota="Documentos de referência e relatórios da Pasta (ex.: auditorias)." lista={b.documents.filter(naArea(area))} fonte={fonteDe(b, "documentos")} vazio="Nenhum documento na Pasta." b={b} onOpen={onOpen} />;
}
export function Projetos({ b, area, onOpen }: Props) {
  return <Notas id="projetos" tipo="projeto" titulo="Projetos" nota="Notas soltas em Projetos/ (subpastas de projeto não são lidas)." lista={b.projects.filter(naArea(area))} fonte={fonteDe(b, "projetos")} vazio="Nenhum projeto na Pasta." b={b} onOpen={onOpen} />;
}

const ESTADO_ROTULO: Record<Fonte["estado"], string> = { ok: "disponível", vazia: "vazia", indisponivel: "indisponível" };

export function Fontes({ b }: { b: SegundoCerebro }) {
  return (
    <Secao id="fontes" titulo="Cobertura e fontes" nota={b.coverage.nota}>
      <div className={s.stats}>
        <div className={s.stat}><span className={s.statNum}>{b.coverage.fontesOk}</span><span className={s.statRot}>fontes lidas de {b.coverage.fontes}</span></div>
        <div className={s.stat}><span className={s.statNum}>{b.coverage.fontesIndisponiveis}</span><span className={s.statRot}>indisponíveis</span></div>
        <div className={s.stat}><span className={s.statNum}>{b.coverage.ligacoes}</span><span className={s.statRot}>ligações gravadas</span></div>
        <div className={s.stat}><span className={s.statNum}>{b.coverage.textosCortados}</span><span className={s.statRot}>textos cortados</span></div>
      </div>
      <div className={s.tabelaWrap}>
        <table className={s.tabela}>
          <thead><tr><th>Fonte</th><th>Situação</th><th>Código</th><th>Registros</th><th>Fora</th><th>Textos cortados</th><th>Na Pasta</th><th>Impressão</th><th>Arquivo atualizado</th></tr></thead>
          <tbody>
            {b.sources.map((f) => (
              <tr key={f.id} id={ancora(`fonte:${f.id}`)} data-fonte={f.id} data-estado={f.estado}>
                <td>{f.rotulo}</td>
                <td className={f.estado === "ok" || f.estado === "vazia" ? s.ok : s.falha}>{ESTADO_ROTULO[f.estado]}</td>
                <td>{f.codigo}{f.arquivos.length > 0 ? ` (${f.arquivos.slice(0, 5).map((a) => `${a.chave}: ${a.codigo}`).join(", ")}${f.arquivos.length > 5 ? "…" : ""})` : ""}</td>
                <td>{f.registros}</td>
                <td>{f.excluidos}</td>
                <td>{f.truncados}</td>
                <td>{f.localizador?.replace(/^segundo_cerebro\/pasta\/?/, "") || "—"}</td>
                <td>{f.impressao ?? "—"}</td>
                <td>{fmt(f.arquivoAtualizadoEm)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={s.muted}>“Arquivo atualizado” é a data de modificação do arquivo, não a data do fato. A impressão (SHA-256 curto do conteúdo) muda quando a fonte muda: a consulta usa isso para verificar.</p>
    </Secao>
  );
}

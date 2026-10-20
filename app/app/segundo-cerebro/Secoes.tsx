"use client";

import { useMemo, useState, type ReactNode } from "react";
import type { Decisao, Fio, Fonte, Proveniencia, SegundoCerebro, SecaoOnboarding } from "@/lib/second-brain.mjs";
import s from "./segundo-cerebro.module.css";

// Todo conteúdo vindo do servidor é exibido como texto (React escapa); nada de HTML cru.

export const ancora = (ref: string) => `reg-${ref.replace(/[^A-Za-z0-9_-]/g, "_")}`;
const PRIORIDADE: Record<string, number> = { urgente: 0, alta: 1, media: 2, média: 2, normal: 3, baixa: 4 };

export function fmt(d: string | null | undefined) {
  if (!d) return "—";
  const t = new Date(d);
  if (Number.isNaN(t.getTime())) return d;
  const soData = /^\d{4}-\d{2}-\d{2}$/.test(d);
  return t.toLocaleString("pt-BR", soData ? { dateStyle: "medium", timeZone: "UTC" } : { dateStyle: "medium", timeStyle: "short" });
}

function uniq(xs: (string | null)[]) {
  return [...new Set(xs.filter((x): x is string => !!x))].sort((a, b) => a.localeCompare(b, "pt-BR"));
}

export function Origem({ p, rotuloData = "Registrado em" }: { p: Proveniencia; rotuloData?: string }) {
  return (
    <dl className={s.prov}>
      <div><dt>Fonte</dt><dd>{p.fonteRotulo}</dd></div>
      {p.localizador && <div><dt>Localizador</dt><dd>{p.localizador}</dd></div>}
      {p.origem && <div><dt>Origem</dt><dd>{p.origem}</dd></div>}
      {p.em !== undefined && <div><dt>{rotuloData}</dt><dd>{fmt(p.em)}</dd></div>}
      <div><dt>Dono</dt><dd>{p.dono}</dd></div>
      <div><dt>Arquivo atualizado</dt><dd>{fmt(p.arquivoAtualizadoEm)}</dd></div>
    </dl>
  );
}

export function Vazio({ fonte, texto }: { fonte?: Fonte; texto: string }) {
  if (fonte?.estado === "indisponivel") return <p className={s.vazio}>Fonte indisponível ({fonte.codigo}) — veja os avisos acima.</p>;
  if (fonte?.estado === "sem_contrato") return <p className={s.vazio}>Lacuna: não existe fonte canônica para isto. Nada é mostrado como se existisse.</p>;
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

export function Contextos({ b }: { b: SegundoCerebro }) {
  return (
    <Secao id="contexto" titulo="Contexto" nota="Único contexto autorizado no servidor: o registro de uma conversa. Não é onboarding nem contexto empresarial.">
      {b.contexts.length === 0 ? <Vazio fonte={fonteDe(b, "contexto")} texto="Contexto sem seções." /> : (
        <ul className={s.cartoes}>
          {b.contexts.map((c) => (
            <li key={c.id} id={ancora(`contexto:${c.id}`)} className={s.cartao} tabIndex={-1}>
              <h3 className={s.h3}>{c.titulo}</h3>
              <ul className={s.itensCtx}>{c.itens.map((i) => <li key={i.linha}><span>L{i.linha}</span>{i.texto}</li>)}</ul>
              <Origem p={c.proveniencia} />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

export function Projetos({ b }: { b: SegundoCerebro }) {
  const f = fonteDe(b, "projetos");
  return (
    <Secao id="projetos" titulo="Projetos" nota="Só projetos cadastrados no Agent Zero com dono.txt = matheus. Assunto de conversa não vira projeto.">
      {f && f.excluidos > 0 && <p className={s.muted}>{f.excluidos} projeto(s) da lista ficaram de fora por falta de prova de dono.</p>}
      {b.projects.length === 0 ? <Vazio fonte={f} texto="Nenhum projeto com dono comprovado." /> : (
        <ul className={s.cartoes}>
          {b.projects.map((p) => (
            <li key={p.id} id={ancora(`projeto:${p.id}`)} className={s.cartao} tabIndex={-1}>
              <div className={s.etiquetas}><span className={s.tagLima}>projeto cadastrado</span><span className={s.tagCinza}>{p.id}</span></div>
              <h3 className={s.h3}>{p.titulo}</h3>
              {p.descricao && <p className={s.corpo}>{p.descricao}</p>}
              {p.instrucoes && <details className={s.mais}><summary>Instruções do projeto</summary><p className={s.corpo}>{p.instrucoes}</p></details>}
              <p className={s.muted}>Fios, decisões ou reuniões ligados: nenhum registrado (o contrato do projeto não grava ligações).</p>
              <Origem p={p.proveniencia} />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

export function Rotinas({ b }: { b: SegundoCerebro }) {
  return (
    <Secao id="rotinas" titulo="Rotinas" nota="Lidas do contrato das rotinas (SKILL.md com tag rotina). Só leitura: nada é executado daqui.">
      {b.routines.length === 0 ? <Vazio fonte={fonteDe(b, "rotinas")} texto="Nenhuma rotina na lista." /> : (
        <ul className={s.cartoes}>
          {b.routines.map((r) => (
            <li key={r.id} id={ancora(`rotina:${r.id}`)} className={s.cartao} tabIndex={-1}>
              <div className={s.etiquetas}><span className={r.dono ? s.tagLima : s.tagCinza}>{r.dono ? "dono: matheus" : "compartilhada"}</span><span className={s.tagCinza}>versão {r.versao}</span>{r.correcoes.length > 0 && <span className={s.tagCiano}>{r.correcoes.length} correção(ões)</span>}</div>
              <h3 className={s.h3}>{r.nome}</h3>
              {r.descricao && <p className={s.corpo}>{r.descricao}</p>}
              <dl className={s.rotina}>
                <dt>Entradas e acessos</dt><dd>{r.entradas ?? "—"}</dd>
                <dt>Passos ({r.passos.length})</dt><dd><ol>{r.passos.map((p, i) => <li key={i}>{p}</li>)}</ol></dd>
                <dt>Precisa de aprovação</dt><dd>{r.aprovacao ?? "—"}</dd>
                <dt>Como verificar</dt><dd>{r.verificar ?? "—"}</dd>
                <dt>O que entregar</dt><dd>{r.entregar ?? "—"}</dd>
                {r.correcoes.length > 0 && <><dt>Correções do usuário (valem acima dos passos)</dt><dd><ul>{r.correcoes.map((c) => <li key={c.linha}>{c.data ? `${c.data}${c.por ? ` (${c.por})` : ""}: ` : ""}{c.texto}</li>)}</ul></dd></>}
              </dl>
              {r.secoesAusentes.length > 0 && <p className={s.muted}>Seções ausentes: {r.secoesAusentes.join(", ")}.</p>}
              <p className={s.muted}>{r.donoNota}.</p>
              <Origem p={r.proveniencia} />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

export function Decisoes({ b }: { b: SegundoCerebro }) {
  const lista = b.decisions;
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
                {d.valido_ate && <span className={s.tagCinza}>válida até {fmt(d.valido_ate)}</span>}
                {d.substitui && <a className={s.tagCiano} href={`#${ancora(`decisao:${d.substitui}`)}`}>substitui #{d.substitui}</a>}
                {d.substituida_por && <a className={s.tagCiano} href={`#${ancora(`decisao:${d.substituida_por}`)}`}>substituída por #{d.substituida_por}</a>}
              </div>
              <h3 className={s.h3}>{d.tema ?? "(sem tema)"}</h3>
              {d.valor && <p className={s.corpo}>{d.valor}</p>}
              {d.citacao && <blockquote className={s.citacao}>“{d.citacao}”</blockquote>}
              {d.motivo && <p className={s.muted}>Motivo do fim: {d.motivo}</p>}
              <Origem p={d.proveniencia} />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

export function Fios({ b }: { b: SegundoCerebro }) {
  const lista = b.threads;
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
    <Secao id="passos" titulo="Fios (próximos passos)" nota="Em aberto = aberto, ou adiado cuja data já chegou (regra do registro de fios). “Dono” do fio é quem age, não um papel confirmado.">
      <div className={s.filtros}>
        <select value={prioridade} onChange={(e) => setPrioridade(e.target.value)} aria-label="Prioridade"><option value="">Todas as prioridades</option>{prioridades.map((t) => <option key={t} value={t}>{t}</option>)}</select>
        <select value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Situação"><option value="">Todas as situações</option>{estados.map((t) => <option key={t} value={t}>{t}</option>)}</select>
      </div>
      {filtrados.length === 0 ? <Vazio fonte={lista.length ? undefined : fonteDe(b, "fios")} texto={lista.length ? "Nada encontrado com esses filtros." : "Nenhum fio registrado."} /> : (
        <ul className={s.cartoes}>
          {filtrados.map((f) => (
            <li key={f.id} id={ancora(`fio:${f.id}`)} className={`${s.cartao} ${f.emAberto ? "" : s.apagado}`} tabIndex={-1}>
              <div className={s.etiquetas}>
                <span className={f.emAberto ? s.tagLima : s.tagCinza}>{f.emAberto ? "em aberto" : f.estado ?? "—"}</span>
                {f.prioridade && <span className={s.tagCiano}>{f.prioridade}</span>}
                {f.prazo && <span className={s.tag}>prazo {fmt(f.prazo)}</span>}
                {f.adiar_ate && <span className={s.tagCinza}>adiado até {f.adiar_ate}</span>}
                {f.dono && <span className={s.tagCinza}>quem age: {f.dono}</span>}
              </div>
              <h3 className={s.h3}>{f.titulo ?? f.id}</h3>
              {f.proximo_passo && <p className={s.passo}><span>Próximo passo</span>{f.proximo_passo}</p>}
              {f.detalhe && <p className={s.corpo}>{f.detalhe}</p>}
              {f.ligacoes.length > 0 && <div className={s.fontesFio}><span>Ligação escrita</span><ul>{f.ligacoes.map((l, i) => <li key={i}>{l.alvo}{l.rotulo ? ` (${l.rotulo})` : ""}</li>)}</ul></div>}
              {f.fontes.length > 0 && <div className={s.fontesFio}><span>Fontes citadas</span><ul>{f.fontes.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
              <p className={s.datas}>Criado {fmt(f.criado)} · atualizado {fmt(f.atualizado)}</p>
              <Origem p={f.proveniencia} rotuloData="Última data do fio" />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

export function Ficha({ b }: { b: SegundoCerebro }) {
  return (
    <Secao id="perfil" titulo="Ficha (fatos)" nota="Fatos da ficha, na ordem do helper. O número é a referência que a ferramenta ficha usa; não é um id estável.">
      {b.profile.length === 0 ? <Vazio fonte={fonteDe(b, "perfil")} texto="Nenhum fato na ficha." /> : (
        <ul className={s.cartoes}>
          {b.profile.map((f) => (
            <li key={f.id} id={ancora(`fato:${f.id}`)} className={s.cartao} tabIndex={-1}>
              <div className={s.etiquetas}><span className={s.tagCinza}>entrada {f.numero}</span></div>
              <p className={s.corpo}>{f.texto}</p>
              <Origem p={f.proveniencia} />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

export function Documentos({ b }: { b: SegundoCerebro }) {
  return (
    <Secao id="documentos" titulo="Documentos" nota="Só os documentos autorizados deste pedido. O conteúdo não é copiado: aparece o índice de seções, o tamanho e o hash para conferir a origem.">
      {b.documents.length === 0 ? <Vazio fonte={fonteDe(b, "documentos")} texto="Nenhum documento disponível." /> : (
        <ul className={s.cartoes}>
          {b.documents.map((d) => (
            <li key={d.id} id={ancora(`documento:${d.id}`)} className={s.cartao} tabIndex={-1}>
              <div className={s.etiquetas}><span className={s.tagCinza}>{d.dono}</span><span className={s.tagCinza}>{d.linhas} linhas</span></div>
              <h3 className={s.h3}>{d.titulo}</h3>
              <p className={s.muted}>SHA-256 {d.sha256.slice(0, 16)}… · {d.bytes} bytes</p>
              {d.citaDocumentos.length > 0 && <p className={s.muted}>Cita (caminho no texto): {d.citaDocumentos.map((c, i) => <a key={c} href={`#${ancora(`documento:${c}`)}`}>{i ? ", " : ""}{c}</a>)}</p>}
              <details className={s.mais}><summary>Seções ({d.secoes.length})</summary><ul>{d.secoes.map((x) => <li key={x.linha}>L{x.linha} · {x.titulo}</li>)}</ul></details>
              <Origem p={d.proveniencia} />
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

export function ReunioesDaily({ b }: { b: SegundoCerebro }) {
  return (
    <Secao id="reunioes" titulo="Reuniões e daily">
      <div className={s.lacunas}>
        <Vazio fonte={fonteDe(b, "reunioes")} texto="" />
        <p className={s.muted}>Reuniões: {b.gaps.find((g) => g.id === "reunioes")?.motivo}</p>
        <p className={s.muted}>Daily: {b.gaps.find((g) => g.id === "daily")?.motivo}</p>
      </div>
    </Secao>
  );
}

function TabelaOnboarding({ titulo, secoes, onOpen }: { titulo: string; secoes: SecaoOnboarding[]; onOpen: (ref: string) => void }) {
  return (
    <div className={s.onb}>
      <h3 className={s.h3}>{titulo}</h3>
      <table className={s.tabela}>
        <thead><tr><th>Seção</th><th>Estado</th><th>Destino canônico</th><th>Por quê</th></tr></thead>
        <tbody>
          {secoes.map((x) => (
            <tr key={x.id} data-estado={x.estado}>
              <td>{x.titulo}<small className={s.publicado}>publicado: {x.publicado}</small></td>
              <td className={x.estado === "parcial" ? s.ok : s.falha}>{x.estado}</td>
              <td>{x.destino}</td>
              <td>{x.motivo}{x.evidencias.length > 0 && <span className={s.evidencias}>{x.evidencias.slice(0, 6).map((r) => <button key={r} type="button" onClick={() => onOpen(r)}>{r}</button>)}{x.evidencias.length > 6 ? ` +${x.evidencias.length - 6}` : ""}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Onboarding({ b, onOpen }: { b: SegundoCerebro; onOpen: (ref: string) => void }) {
  const o = b.proposals.onboarding;
  return (
    <Secao id="onboarding" titulo="Onboarding (proposta)" nota={o.nota}>
      <TabelaOnboarding titulo="Parte 1 — negócio (7 seções)" secoes={o.negocio} onOpen={onOpen} />
      <TabelaOnboarding titulo="Parte 2 — pessoal (6 seções)" secoes={o.pessoal} onOpen={onOpen} />
      <p className={s.muted}>Próximo passo proposto: retomar com o Matheus só as seções pendentes, uma por vez; fatos vão para a ficha e preferências para decisões, cada um pela ferramenta canônica e com a aprovação dele.</p>
    </Secao>
  );
}

const ESTADO_ROTULO: Record<Fonte["estado"], string> = { ok: "disponível", vazia: "vazia", indisponivel: "indisponível", sem_contrato: "sem fonte canônica" };

export function Fontes({ b }: { b: SegundoCerebro }) {
  return (
    <Secao id="fontes" titulo="Cobertura e fontes" nota={b.coverage.nota}>
      <div className={s.stats}>
        <div className={s.stat}><span className={s.statNum}>{b.coverage.fontesOk}</span><span className={s.statRot}>fontes lidas de {b.coverage.fontes}</span></div>
        <div className={s.stat}><span className={s.statNum}>{b.coverage.fontesSemContrato}</span><span className={s.statRot}>sem fonte canônica</span></div>
        <div className={s.stat}><span className={s.statNum}>{b.coverage.fontesIndisponiveis}</span><span className={s.statRot}>indisponíveis</span></div>
        <div className={s.stat}><span className={s.statNum}>{b.coverage.excluidosPorDono}</span><span className={s.statRot}>fora por falta de dono</span></div>
      </div>
      <div className={s.tabelaWrap}>
        <table className={s.tabela}>
          <thead><tr><th>Fonte</th><th>Situação</th><th>Código</th><th>Registros</th><th>Fora</th><th>Textos cortados</th><th>Localizador</th><th>Impressão</th><th>Arquivo atualizado</th></tr></thead>
          <tbody>
            {b.sources.map((f) => (
              <tr key={f.id} id={ancora(`fonte:${f.id}`)} data-fonte={f.id} data-estado={f.estado}>
                <td>{f.rotulo}</td>
                <td className={f.estado === "ok" || f.estado === "vazia" ? s.ok : s.falha}>{ESTADO_ROTULO[f.estado]}</td>
                <td>{f.codigo}{f.arquivos.length > 0 ? ` (${f.arquivos.map((a) => a.codigo).join(", ")})` : ""}</td>
                <td>{f.registros}</td>
                <td>{f.excluidos}</td>
                <td>{f.truncados}</td>
                <td>{f.localizador ?? "—"}</td>
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

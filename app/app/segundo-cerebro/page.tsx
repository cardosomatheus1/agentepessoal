"use client";

import { useCallback, useEffect, useState } from "react";
import type { SegundoCerebro } from "@/lib/second-brain.mjs";
import s from "./segundo-cerebro.module.css";
import BrainMap from "./BrainMap";
import Consulta from "./Consulta";
import { Assuntos, Contextos, Decisoes, Documentos, Ficha, Fontes, NotasDoDia, Pendencias, Projetos, Reunioes, ancora, fmt } from "./Secoes";

// Todo conteúdo vindo do servidor é exibido como texto (React escapa); nada de HTML cru.

const SECOES = [
  ["visao", "Visão geral"],
  ["consulta", "Consulta"],
  ["mapa", "Mapa"],
  ["assuntos", "Assuntos"],
  ["pendencias", "Pendências"],
  ["decisoes", "Decisões"],
  ["notas", "Notas do dia"],
  ["reunioes", "Reuniões"],
  ["contexto", "Contexto"],
  ["perfil", "Perfil"],
  ["projetos", "Projetos"],
  ["documentos", "Documentos"],
  ["fontes", "Fontes"],
] as const;

// Acesso pela sessão do Agent Zero (cookie do mesmo site, enviado pelo navegador). A página não pede nem guarda
// chave: o gateway do servidor confere a sessão do Matheus e fala com a API interna.
const LOGIN = "/login?next=/segundo-cerebro";

type Acesso = "carregando" | "ok" | "sem-sessao" | "outra-conta" | "erro";

export default function SegundoCerebroPage() {
  const [acesso, setAcesso] = useState<Acesso>("carregando");
  const [dados, setDados] = useState<SegundoCerebro | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async (): Promise<SegundoCerebro | null> => {
    setCarregando(true);
    setErro(null);
    try {
      const r = await fetch("/api/segundo-cerebro", { method: "GET", cache: "no-store", credentials: "same-origin" });
      if (r.status === 401 || r.status === 403) {
        setDados(null);
        setAcesso(r.status === 401 ? "sem-sessao" : "outra-conta");
        return null;
      }
      if (!r.ok) {
        const corpo = (await r.json().catch(() => null)) as { erro?: string } | null;
        setErro(corpo?.erro ?? `Erro ${r.status}.`);
        setAcesso((a) => (a === "ok" ? a : "erro"));
        return null;
      }
      const novo = (await r.json()) as SegundoCerebro;
      setDados(novo);
      setAcesso("ok");
      return novo;
    } catch {
      setErro("Não foi possível falar com o servidor.");
      setAcesso((a) => (a === "ok" ? a : "erro"));
      return null;
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    // Primeira carga fora do corpo do efeito (o estado inicial já é "carregando").
    const t = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(t);
  }, [carregar]);

  if (acesso !== "ok" || !dados) {
    return (
      <main className={s.gate}>
        <div className={s.gateCard}>
          <p className={s.kicker}>Acesso restrito</p>
          <h1 className={s.titulo}>Segundo Cérebro</h1>
          {acesso === "carregando" && <p className={s.muted} role="status">Carregando…</p>}
          {acesso === "sem-sessao" && (
            <>
              <p className={s.muted} role="alert">Sua sessão expirou ou você ainda não entrou.</p>
              <a className={s.btnPrim} href={LOGIN}>Entrar</a>
            </>
          )}
          {acesso === "outra-conta" && (
            <>
              <p className={s.muted} role="alert">Esta página é só do Matheus. Saia e entre com a conta dele.</p>
              <a className={s.btnPrim} href="/logout">Sair</a>
            </>
          )}
          {acesso === "erro" && (
            <>
              <p className={s.erro} role="alert">{erro}</p>
              <button className={s.btnPrim} type="button" onClick={() => void carregar()} disabled={carregando}>
                {carregando ? "Tentando…" : "Tentar de novo"}
              </button>
            </>
          )}
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- "/" é o chat do Agent Zero, fora deste app: navegação completa */}
          <a href="/" className={s.voltar}>← Voltar ao chat</a>
        </div>
      </main>
    );
  }

  return <Painel dados={dados} carregando={carregando} erro={erro} recarregar={carregar} />;
}

function Painel({ dados, carregando, erro, recarregar }: { dados: SegundoCerebro; carregando: boolean; erro: string | null; recarregar: () => Promise<SegundoCerebro | null> }) {
  const [aviso, setAviso] = useState<string | null>(null);
  const [area, setArea] = useState("");
  const daArea = <T extends { area?: string | null }>(xs: T[]) => xs.filter((x) => !area || x.area === area);
  const decisoes = daArea(dados.decisions);
  const vigentes = decisoes.filter((d) => d.vigente).length;
  const pendencias = daArea(dados.threads);
  const abertos = pendencias.filter((f) => f.emAberto).length;
  const assuntos = daArea(dados.subjects);
  const andamento = assuntos.filter((a) => a.emAndamento).length;
  const validados = dados.contexts.filter((c) => c.estado === "validado").length;

  // Navegação íntegra: abre o cartão do registro; se ele não está na página (filtro, outra fonte), diz isso.
  const abrir = useCallback((ref: string) => {
    const el = document.getElementById(ancora(ref));
    if (!el) { setAviso(`O registro ${ref} não está visível na página (filtro ativo ou não é um registro navegável).`); return; }
    setAviso(null);
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.focus({ preventScroll: true });
    el.setAttribute("data-destacado", "sim");
    window.setTimeout(() => el.removeAttribute("data-destacado"), 2500);
  }, []);

  return (
    <div className={s.shell}>
      <nav className={s.nav} aria-label="Seções">
        <div className={s.marca}>
          <span className={s.ponto} aria-hidden />
          <span>Segundo Cérebro</span>
        </div>
        <ul>
          {SECOES.map(([id, nome]) => (
            <li key={id}><a href={`#${id}`}>{nome}</a></li>
          ))}
        </ul>
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- "/" é o chat do Agent Zero, fora deste app */}
        <a href="/" className={s.navChat}>← Chat</a>
      </nav>

      <main className={s.main}>
        <header className={s.topo}>
          <div>
            <p className={s.kicker}>Matheus · Pasta lida {fmt(dados.fetchedAt)}</p>
            <h1 className={s.titulo}>Segundo Cérebro</h1>
          </div>
          <div className={s.acoes}>
            <label className={s.muted}>Área{" "}
              <select value={area} onChange={(e) => setArea(e.target.value)} aria-label="Filtrar por área">
                <option value="">Todas</option>
                {dados.areas.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </label>
            <button type="button" className={s.btn} onClick={() => void recarregar()} disabled={carregando}>
              {carregando ? "Atualizando…" : "Atualizar"}
            </button>
            <a className={s.btn} href="/logout">Sair</a>
          </div>
        </header>

        {erro && <p className={s.erro} role="alert">{erro}</p>}
        {aviso && <p className={s.avisos} role="status">{aviso}</p>}
        {dados.warnings.length > 0 && (
          <ul className={s.avisos} aria-label="Avisos">
            {dados.warnings.map((w) => <li key={w.fonte + w.codigo}>{w.mensagem}</li>)}
          </ul>
        )}

        <section id="visao" className={s.secao}>
          <h2 className={s.h2}>Visão geral</h2>
          <p className={s.muted}>Mostra a Pasta do Segundo Cérebro, a única fonte, escrita só pelo agente a partir das conversas no Telegram. Esta página só lê: não grava nada.{area ? ` Filtrando pela área ${area}.` : ""}</p>
          <div className={s.stats}>
            <Stat valor={andamento} rotulo="assuntos em andamento" de={assuntos.length} />
            <Stat valor={abertos} rotulo="pendências em aberto" de={pendencias.length} />
            <Stat valor={vigentes} rotulo="decisões vigentes" de={decisoes.length} />
            <Stat valor={validados} rotulo="seções de contexto validadas" de={dados.contexts.length} />
            <Stat valor={daArea(dados.daily).length} rotulo="notas do dia" />
            <Stat valor={dados.gaps.length} rotulo="lacunas" />
          </div>
          {dados.rules && dados.rules.regras.length > 0 && (
            <details className={s.mais}><summary>Regras da Pasta (CLAUDE.md)</summary><ol>{dados.rules.regras.map((r, i) => <li key={i}>{r}</li>)}</ol></details>
          )}
          <div className={s.duas}>
            <div>
              <h3 className={s.h3}>Lacunas</h3>
              <ul className={s.lista} aria-label="Lacunas">{dados.gaps.map((g) => <li key={g.id}>{g.motivo}</li>)}</ul>
            </div>
            <div>
              <h3 className={s.h3}>Conflitos e diagnósticos <small className={s.muted}>(não autoritativos)</small></h3>
              {dados.conflicts.length + dados.diagnostics.length === 0 ? (
                <p className={s.muted}>Nenhum conflito com evidência estruturada (só invariantes da Pasta: uma decisão ativa por tema, perfil sem duplicadas, id único por item, substituição e liga apontando para itens que existem). Semelhança de palavras não conta como conflito.</p>
              ) : (
                <ul className={s.lista} aria-label="Conflitos e diagnósticos">
                  {[...dados.conflicts, ...dados.diagnostics].map((c, i) => (
                    <li key={i}>{c.detalhe} · {c.regra} · {c.registros.map((r) => <button key={r} type="button" className={s.refBtn} onClick={() => abrir(r)}>{r}</button>)}</li>
                  ))}
                </ul>
              )}
              <p className={s.muted}>Nada é corrigido por esta página: correção é pelo agente, no Telegram.</p>
            </div>
          </div>
        </section>

        <section id="consulta" className={s.secao}>
          <h2 className={s.h2}>Consulta</h2>
          <Consulta brain={dados} area={area} recarregar={recarregar} onOpen={abrir} />
        </section>

        <section id="mapa" className={s.secao}>
          <h2 className={s.h2}>Mapa</h2>
          <BrainMap brain={dados} area={area} onOpen={abrir} />
        </section>

        <Assuntos b={dados} area={area} onOpen={abrir} />
        <Pendencias b={dados} area={area} onOpen={abrir} />
        <Decisoes b={dados} area={area} onOpen={abrir} />
        <NotasDoDia b={dados} area={area} onOpen={abrir} />
        <Reunioes b={dados} area={area} onOpen={abrir} />
        <Contextos b={dados} area={area} onOpen={abrir} />
        <Ficha b={dados} />
        <Projetos b={dados} area={area} onOpen={abrir} />
        <Documentos b={dados} area={area} onOpen={abrir} />
        <Fontes b={dados} />
      </main>
    </div>
  );
}

function Stat({ valor, rotulo, de }: { valor: number; rotulo: string; de?: number }) {
  return (
    <div className={s.stat}>
      <span className={s.statNum}>{valor}</span>
      <span className={s.statRot}>{rotulo}{de !== undefined ? ` de ${de}` : ""}</span>
    </div>
  );
}

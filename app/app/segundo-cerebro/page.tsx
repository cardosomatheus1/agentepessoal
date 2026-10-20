"use client";

import { useCallback, useEffect, useState } from "react";
import type { SegundoCerebro } from "@/lib/second-brain.mjs";
import s from "./segundo-cerebro.module.css";
import BrainMap from "./BrainMap";
import Consulta from "./Consulta";
import { Contextos, Decisoes, Documentos, Ficha, Fios, Fontes, Onboarding, Projetos, ReunioesDaily, Rotinas, ancora, fmt } from "./Secoes";

// Todo conteúdo vindo do servidor é exibido como texto (React escapa); nada de HTML cru.

const SECOES = [
  ["visao", "Visão geral"],
  ["consulta", "Consulta"],
  ["mapa", "Mapa"],
  ["contexto", "Contexto"],
  ["projetos", "Projetos"],
  ["rotinas", "Rotinas"],
  ["decisoes", "Decisões"],
  ["passos", "Fios"],
  ["perfil", "Ficha"],
  ["documentos", "Documentos"],
  ["reunioes", "Reuniões e daily"],
  ["onboarding", "Onboarding"],
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
  const vigentes = dados.decisions.filter((d) => d.vigente).length;
  const abertos = dados.threads.filter((f) => f.emAberto).length;

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
            <p className={s.kicker}>Matheus · fontes lidas {fmt(dados.fetchedAt)}</p>
            <h1 className={s.titulo}>Segundo Cérebro</h1>
          </div>
          <div className={s.acoes}>
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
          <p className={s.muted}>Projeção só de leitura das fontes canônicas (ficha, decisões, fios, rotinas, contexto autorizado, projetos com dono e documentos do pedido). Esta página não grava nada e não é uma segunda base.</p>
          <div className={s.stats}>
            <Stat valor={dados.coverage.registros} rotulo="registros lidos" />
            <Stat valor={vigentes} rotulo="decisões vigentes" de={dados.decisions.length} />
            <Stat valor={abertos} rotulo="fios em aberto" de={dados.threads.length} />
            <Stat valor={dados.routines.length} rotulo="rotinas" />
            <Stat valor={dados.projects.length} rotulo="projetos com dono" />
            <Stat valor={dados.gaps.length} rotulo="lacunas" />
          </div>
          <div className={s.duas}>
            <div>
              <h3 className={s.h3}>Lacunas</h3>
              <ul className={s.lista} aria-label="Lacunas">{dados.gaps.map((g) => <li key={g.id}>{g.motivo}</li>)}</ul>
            </div>
            <div>
              <h3 className={s.h3}>Conflitos e diagnósticos <small className={s.muted}>(não autoritativos)</small></h3>
              {dados.conflicts.length + dados.diagnostics.length === 0 ? (
                <p className={s.muted}>Nenhum conflito com evidência estruturada (só invariantes dos contratos: uma decisão ativa por tema, ficha sem duplicadas, id de fio único, referências de substituição válidas, rotina com seções e menos de 8 correções). Semelhança de palavras não conta como conflito.</p>
              ) : (
                <ul className={s.lista} aria-label="Conflitos e diagnósticos">
                  {[...dados.conflicts, ...dados.diagnostics].map((c, i) => (
                    <li key={i}>{c.detalhe} · {c.regra} · {c.registros.map((r) => <button key={r} type="button" className={s.refBtn} onClick={() => abrir(r)}>{r}</button>)}</li>
                  ))}
                </ul>
              )}
              <p className={s.muted}>Propostas não aprovadas: veja Onboarding. Nada é promovido a dado canônico por esta página.</p>
            </div>
          </div>
        </section>

        <section id="consulta" className={s.secao}>
          <h2 className={s.h2}>Consulta</h2>
          <Consulta brain={dados} recarregar={recarregar} onOpen={abrir} />
        </section>

        <section id="mapa" className={s.secao}>
          <h2 className={s.h2}>Mapa</h2>
          <BrainMap brain={dados} onOpen={abrir} />
        </section>

        <Contextos b={dados} />
        <Projetos b={dados} />
        <Rotinas b={dados} />
        <Decisoes b={dados} />
        <Fios b={dados} />
        <Ficha b={dados} />
        <Documentos b={dados} />
        <ReunioesDaily b={dados} />
        <Onboarding b={dados} onOpen={abrir} />
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

import type { SegundoCerebro } from "./second-brain.mjs";

export type Funcao = "retomar" | "rotina" | "prioridades" | "pauta" | "registro" | "fonte" | "buscar" | "onboarding";
export interface Consulta { funcao: Funcao; fonte?: string; registro?: string; termo?: string }
export interface ItemConsulta {
  ref: string;
  tipo: string;
  rotulo: string;
  trecho: string | null;
  proveniencia: { fonte?: string; fonteRotulo?: string; localizador?: string | null; arquivoAtualizadoEm?: string | null } | null;
  porque: string;
}
export interface FonteUsada { id: string; estado: string; codigo: string; impressao: string | null }
export interface ResultadoConsulta {
  ok: true;
  consulta: { funcao: Funcao; fonte: string | null; registro: string | null; termo: string | null };
  rotulo: string;
  estado: "ok" | "parcial" | "bloqueado";
  resumo: string;
  itens: ItemConsulta[];
  proximosPassos: { ref: string; texto: string }[];
  bloqueios: { fonte: string | null; motivo: string }[];
  conflitos: { tipo: string; detalhe: string; registros: string[] }[];
  fontesUsadas: FonteUsada[];
  carregadoEm: string;
}
export interface Etapa {
  etapa: "captura" | "validacao" | "consulta" | "execucao" | "verificacao";
  estado: string;
  detalhe: string;
  evidencias?: string[];
  aprovacoes?: { ref: string; texto: string }[];
  proposta?: string[];
  entrega?: string | null;
}
export interface Verificacao {
  estado: "verificado" | "divergente";
  detalhe: string;
  fontes: { id: string; antes: string | null; depois: string | null; igual: boolean }[];
  registros: { citados: number; presentes: number };
  verificadoEm: string;
}
export const FUNCOES: Readonly<Record<Funcao, string>>;
export const FONTES: readonly string[];
export function validarConsulta(q: unknown): { ok: true; consulta: ResultadoConsulta["consulta"] } | { ok: false; erro: string };
export function acharRegistro(brain: SegundoCerebro, ref: string): unknown;
export function consultar(brain: SegundoCerebro, consulta: Consulta): ResultadoConsulta | { ok: false; erro: string };
export function roteiro(brain: SegundoCerebro, resultado: ResultadoConsulta): Etapa[];
export function verificar(resultado: ResultadoConsulta, recarga: SegundoCerebro): Verificacao;

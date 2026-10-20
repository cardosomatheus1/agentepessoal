import type { MultiDirectedGraph } from "graphology";
import type { SegundoCerebro } from "./second-brain.mjs";

export type TipoNo = "fonte" | "projeto" | "contexto" | "documento" | "rotina" | "decisao" | "fato" | "fio" | "referencia";
export type Relacao = "proveniencia" | "substitui" | "ligacao_fio" | "cita_documento" | "ligacao_texto" | "fonte_citada";
export type ClasseRelacao = "proveniencia" | "comprovada" | "referencia";
export type Agrupamento = "fonte" | "meta" | "tipo";

export interface Evidencia { fonte: string; registro: string | null; campo: string; localizador: string | null }
export interface NoCerebro {
  id: string;
  tipo: TipoNo;
  rotulo: string;
  rotuloCompleto?: string;
  fonte: string;
  meta?: string;
  texto?: string;
  estado?: string | null;
  localizador?: string | null;
  registro: { fonte: string; id?: string } | null;
}
export interface ArestaCerebro { id: string; de: string; para: string; relacao: Relacao; classe: ClasseRelacao; rotulo: string | null; evidencia: Evidencia }
export interface GrafoCerebro { nodes: NoCerebro[]; edges: ArestaCerebro[] }

export const TIPOS: Readonly<Record<TipoNo, { rotulo: string; cor: string; forma: "square" | "diamond" | "triangle" | "circle"; tamanho: number }>>;
export const RELACOES: Readonly<Record<Relacao, { rotulo: string; classe: ClasseRelacao }>>;
export const AGRUPAMENTOS: Readonly<Record<Agrupamento, string>>;
export function normalizar(s: unknown): string;
export function buildBrainGraph(brain: Partial<SegundoCerebro>): GrafoCerebro;
export function grupoDe(node: NoCerebro, modo?: Agrupamento): string;
export function filterBrainGraph(
  graph: GrafoCerebro,
  opts?: { termo?: string; tipos?: Set<string>; fontes?: Set<string>; relacoes?: Set<string>; vizinhos?: boolean },
): GrafoCerebro & { matches: Set<string>; contexto: Set<string> };
export function layoutBrainGraph(graph: GrafoCerebro, modo?: Agrupamento): {
  positions: Map<string, { x: number; y: number }>;
  centros: Map<string, { x: number; y: number; raio: number }>;
};
export type AtributosNo = { x: number; y: number; label: string; tipo: TipoNo; color: string; shape: string; size: number };
export type AtributosAresta = { relacao: Relacao; classe: ClasseRelacao; label: string };
export function nodeStyle(node: NoCerebro, degree?: number): { color: string; shape: string; size: number };
export function buildSigmaGraph(view: GrafoCerebro, positions: Map<string, { x: number; y: number }>): MultiDirectedGraph<AtributosNo, AtributosAresta>;
export function neighborsOf(graph: GrafoCerebro, id: string): { edge: ArestaCerebro; outro: string; direcao: "saida" | "entrada" }[];

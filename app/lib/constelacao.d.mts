import type { GrafoCerebro, NoCerebro, Relacao } from "./brain-graph.mjs";

export type Modo = "disco" | "forca" | "aneis";
export type Ponto = { x: number; y: number };
export type Ponto3 = { x: number; y: number; z: number };
export const MODOS: Readonly<Record<Modo, string>>;
export const ORDEM_TIPOS: readonly string[];
export const RAIO_ORBITA: number;
export function rotuloTipo(tipo: string, n: number): string;
export function layoutDisco(graph: GrafoCerebro): {
  posicoes: Map<string, Ponto>;
  setores: { tipo: string; n: number; inicio: number; fim: number; rotulo: string }[];
  orbita: ({ id: string; rotulo: string } & Ponto)[];
};
export function layoutForca(graph: GrafoCerebro, opts?: { passos?: number }): { posicoes: Map<string, Ponto> };
export function layoutAneis(graph: GrafoCerebro): { pontos: Map<string, Ponto3> };
export function projetar(p: Ponto3, giro: number, inclinacao?: number, dist?: number): Ponto & { escala: number; profundidade: number };
export function ligacoesDoItem(graph: GrafoCerebro, id: string): {
  aponta: { relacao: Relacao; no: NoCerebro }[];
  referenciado: { relacao: Relacao; no: NoCerebro }[];
};
export function maisPerto(pontosTela: Map<string, Ponto>, px: number, py: number, raio?: number): string | null;

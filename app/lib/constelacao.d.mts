import type { GrafoCerebro, NoCerebro, Relacao } from "./brain-graph.mjs";

export type Modo = "disco" | "forca" | "aneis";
export type Ponto = { x: number; y: number };
export type Pose = { x: number; y: number; z: number; ang: number; sx: number; sy: number };
export type PoseHex = { x: number; y: number; z: number; tam: number };
export type Rotulo = { texto: string; x: number; y: number; z: number; cor: string; estilo: "pilula" | "texto" };
export type Cena = {
  itens: Map<string, Pose>;
  hexes: Map<string, PoseHex>;
  rotulos: Rotulo[];
  setores: { tipo: string; n: number; inicio: number; fim: number }[];
  linhas: { r: number; cor: string }[];
};
export const MODOS: Readonly<Record<Modo, string>>;
export const CORES: Readonly<Record<string, string>>;
export const NUCLEO: string;
export const TIPOS_HEX: readonly string[];
export const ORDEM_FAIXAS: readonly string[];
export const RAIO_ORBITA: number;
export const RAIO_LINHA: number;
export function ehHex(n: NoCerebro): boolean;
export function corDoTipo(tipo: string): string;
export function rotuloTipo(tipo: string, n: number): string;
export function girassol(n: number, r: number): Ponto[];
export function poseDisco(graph: GrafoCerebro): Cena;
export function poseForca(graph: GrafoCerebro): Cena;
export function poseAneis(graph: GrafoCerebro): Cena;
export const POSES: Readonly<Record<Modo, (graph: GrafoCerebro) => Cena>>;
export function suavizar(t: number): number;
export function misturar(a: Pose, b: Pose, t: number): Pose;
export function ligacoesDoItem(graph: GrafoCerebro, id: string): {
  aponta: { relacao: Relacao; no: NoCerebro }[];
  referenciado: { relacao: Relacao; no: NoCerebro }[];
};
export function maisPerto(pontosTela: Map<string, Ponto>, px: number, py: number, raio?: number): string | null;

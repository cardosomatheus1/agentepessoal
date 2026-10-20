import type { MultiDirectedGraph } from "graphology";
import type { Conexoes } from "./second-brain.mjs";
export function filterConnections(connections: Conexoes, query?: string, type?: string): Conexoes & { matches: Set<string> };
export function layoutConnections(connections: Conexoes): {
  nodes: (Conexoes["nodes"][number] & { x: number; y: number })[];
  width: number;
  height: number;
};
export type Positions = Map<string, { x: number; y: number }>;
export type MapNodeAttributes = { x: number; y: number; label: string; tipo: string; size: number };
export type MapEdgeAttributes = { label: string };
export function nodeSize(tipo: string, degree: number): number;
export function buildConnectionGraph(connections: Conexoes, positions?: Positions): MultiDirectedGraph<MapNodeAttributes, MapEdgeAttributes>;
export function forceLayoutConnections(connections: Conexoes, options?: { iterations?: number }): {
  nodes: (Conexoes["nodes"][number] & { x: number; y: number })[];
  positions: Positions;
};

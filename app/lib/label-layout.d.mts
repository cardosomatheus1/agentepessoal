export const LABEL_MARGIN: number;
export const MOBILE_MAX_WIDTH: number;
export type LabelPolicy = { mobile: boolean; gap: number; edge: number; budget: number };
export type LabelBox = { x0: number; x1: number; y0: number; y1: number };
export type LabelCandidate = { id: string; x: number; y: number; r: number; text: string; size: number; priority: number; pinned?: boolean };
export type LabelPlan = Map<string, { position: "right" | "left"; box: LabelBox }>;
export function labelPolicy(width: number, height: number): LabelPolicy;
export function planLabels(
  candidates: LabelCandidate[],
  options: { width: number; height: number; measure: (text: string, size: number) => number; policy?: LabelPolicy },
): LabelPlan;
export function sameLabelPlan(a: LabelPlan, b: LabelPlan): boolean;

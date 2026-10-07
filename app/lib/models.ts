export type ModeId = "rapido" | "padrao" | "power";

export interface Mode {
  id: ModeId;
  label: string;
  hint: string;
  model: string;
  /** Show summarized reasoning in the "Pensando" block. */
  thinking: boolean;
  effort?: "low" | "medium" | "high";
}

// Bedrock cross-region inference profile IDs (bedrock-runtime endpoint).
export const MODES: Record<ModeId, Mode> = {
  rapido: {
    id: "rapido",
    label: "Rápido",
    hint: "Respostas instantâneas",
    model: "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    thinking: false,
  },
  padrao: {
    id: "padrao",
    label: "Padrão",
    hint: "Equilíbrio entre velocidade e profundidade",
    model: "us.anthropic.claude-sonnet-5-5",
    thinking: true,
    effort: "medium",
  },
  power: {
    id: "power",
    label: "Power",
    hint: "Raciocínio mais profundo",
    model: "us.anthropic.claude-opus-5-5",
    thinking: true,
    effort: "high",
  },
};

export const DEFAULT_MODE: ModeId = "padrao";

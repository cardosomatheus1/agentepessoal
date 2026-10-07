export type ModeId = "rapido" | "padrao" | "power";

export interface Mode {
  id: ModeId;
  label: string;
  hint: string;
  /** Bedrock model or inference profile ID (Converse API). */
  model: string;
}

// OpenAI models served by Amazon Bedrock. Claude stays available by swapping the ID
// (e.g. "us.anthropic.claude-sonnet-5-5"); the Converse API is the same for both.
export const MODES: Record<ModeId, Mode> = {
  rapido: {
    id: "rapido",
    label: "Rápido",
    hint: "GPT-5.6 Luna · mais barato",
    model: "us.openai.gpt-5.6-luna",
  },
  padrao: {
    id: "padrao",
    label: "Padrão",
    hint: "GPT-5.6 Terra · equilíbrio",
    model: "us.openai.gpt-5.6-terra",
  },
  power: {
    id: "power",
    label: "Power",
    hint: "GPT-5.6 Sol · raciocínio mais forte",
    model: "us.openai.gpt-5.6-sol",
  },
};

export const DEFAULT_MODE: ModeId = "padrao";

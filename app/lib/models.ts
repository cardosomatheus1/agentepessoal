export type ModeId = "rapido" | "avancado";

export interface Mode {
  id: ModeId;
  label: string;
  hint: string;
  /** Bedrock model or inference profile ID (Converse API). */
  model: string;
}

// OpenAI models served by Amazon Bedrock.
export const MODES: Record<ModeId, Mode> = {
  rapido: {
    id: "rapido",
    label: "Rápido",
    hint: "GPT-6 Luna · respostas rápidas e baratas",
    model: "us.openai.gpt-6-luna",
  },
  avancado: {
    id: "avancado",
    label: "Avançado",
    hint: "GPT-6.1 Sol · raciocínio mais forte",
    model: "us.openai.gpt-6.1-sol",
  },
};

export const DEFAULT_MODE: ModeId = "rapido";

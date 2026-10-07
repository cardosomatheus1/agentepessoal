import {
  BedrockRuntimeClient,
  ConverseStreamCommand,
  type Message as BedrockMessage,
} from "@aws-sdk/client-bedrock-runtime";
import { MODES, type ModeId } from "./models";

/** Events streamed to the browser, one JSON object per line. */
export type ChatEvent =
  | { t: "thinking"; d: string }
  | { t: "text"; d: string }
  | { t: "done"; stop: string | null }
  | { t: "error"; message: string };

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

// Uses the default AWS credential chain (env vars locally, IAM role on Lambda/EC2).
const client = new BedrockRuntimeClient({
  region: process.env.AWS_REGION ?? "us-east-1",
});

function systemPrompt() {
  const today = new Date().toLocaleDateString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "full",
  });
  return [
    "Você é o assistente pessoal do usuário. Responda em português do Brasil,",
    "a menos que ele escreva em outro idioma. Seja direto e útil; use Markdown",
    "(listas, tabelas, blocos de código) quando ajudar a leitura.",
    `Hoje é ${today}.`,
  ].join(" ");
}

export async function* streamChat(
  modeId: ModeId,
  turns: ChatTurn[],
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const mode = MODES[modeId] ?? MODES.rapido;
  const messages: BedrockMessage[] = turns.map((t) => ({
    role: t.role,
    content: [{ text: t.content }],
  }));

  try {
    const res = await client.send(
      new ConverseStreamCommand({
        modelId: mode.model,
        system: [{ text: systemPrompt() }],
        messages,
        inferenceConfig: { maxTokens: 32000 },
      }),
      { abortSignal: signal },
    );

    let stop: string | null = null;
    for await (const ev of res.stream ?? []) {
      const delta = ev.contentBlockDelta?.delta;
      // Only some models (e.g. gpt-oss, Claude) return readable reasoning text.
      if (delta?.reasoningContent?.text) yield { t: "thinking", d: delta.reasoningContent.text };
      if (delta?.text) yield { t: "text", d: delta.text };
      if (ev.messageStop) stop = ev.messageStop.stopReason ?? null;
    }
    yield { t: "done", stop };
  } catch (err) {
    if (signal?.aborted) return;
    const message = err instanceof Error ? err.message : String(err);
    yield { t: "error", message };
  }
}

import { AnthropicBedrock } from "@anthropic-ai/bedrock-sdk";
import type Anthropic from "@anthropic-ai/sdk";
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

const client = new AnthropicBedrock({
  awsRegion: process.env.AWS_REGION ?? "us-east-1",
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
  const mode = MODES[modeId] ?? MODES.padrao;
  const messages: Anthropic.MessageParam[] = turns.map((t) => ({
    role: t.role,
    content: t.content,
  }));

  try {
    const stream = client.messages.stream(
      {
        model: mode.model,
        max_tokens: 64000,
        system: systemPrompt(),
        messages,
        ...(mode.thinking
          ? { thinking: { type: "adaptive", display: "summarized" } }
          : {}),
        ...(mode.effort ? { output_config: { effort: mode.effort } } : {}),
      } as Anthropic.MessageStreamParams,
      { signal },
    );

    for await (const ev of stream) {
      if (ev.type === "content_block_delta") {
        if (ev.delta.type === "thinking_delta") {
          yield { t: "thinking", d: ev.delta.thinking };
        } else if (ev.delta.type === "text_delta") {
          yield { t: "text", d: ev.delta.text };
        }
      }
    }
    const final = await stream.finalMessage();
    yield { t: "done", stop: final.stop_reason };
  } catch (err) {
    if (signal?.aborted) return;
    const message = err instanceof Error ? err.message : String(err);
    yield { t: "error", message };
  }
}

import { streamChat, type ChatTurn } from "@/lib/chat";
import { DEFAULT_MODE, MODES, type ModeId } from "@/lib/models";

export const maxDuration = 300;

export async function POST(req: Request) {
  const body = (await req.json()) as { mode?: ModeId; messages?: ChatTurn[] };
  const turns = (body.messages ?? []).filter(
    (m) => (m.role === "user" || m.role === "assistant") && m.content?.trim(),
  );
  if (!turns.length || turns[turns.length - 1].role !== "user") {
    return Response.json({ error: "última mensagem deve ser do usuário" }, { status: 400 });
  }
  const mode = body.mode && body.mode in MODES ? body.mode : DEFAULT_MODE;

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      for await (const ev of streamChat(mode, turns, req.signal)) {
        controller.enqueue(encoder.encode(JSON.stringify(ev) + "\n"));
      }
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
    },
  });
}

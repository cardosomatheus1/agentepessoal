import { connection } from "next/server";
import { handleSecondBrainRequest } from "@/lib/second-brain.mjs";

// Com cacheComponents ligado, `export const dynamic` não é aceito; connection()
// garante renderização a cada requisição (equivalente a force-dynamic).
export async function GET(req: Request) {
  await connection();
  const r = await handleSecondBrainRequest(req, process.env);
  return new Response(JSON.stringify(r.body), { status: r.status, headers: r.headers });
}

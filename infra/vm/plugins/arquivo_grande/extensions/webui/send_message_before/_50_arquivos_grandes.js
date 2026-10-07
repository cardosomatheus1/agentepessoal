// "+ → Attach files" (and drag & drop / paste) for any size: attachments that would not fit
// through the tunnel (~100 MB per request) go straight to S3 and land in this chat's anexos/;
// the message then carries a line with each file's path. Small files keep the normal path.
import { store } from "/plugins/arquivo_grande/webui/arquivo-grande-store.js";

const MB = 1024 * 1024;
const POR_ARQUIVO = 25 * MB; // above this, S3 is also faster than the tunnel
const TOTAL = 80 * MB; // keep the normal request well under the tunnel limit

export default async function arquivosGrandes(sendCtx) {
  if (sendCtx.cancel) return;
  const anexos = [...(sendCtx.attachments || [])];
  if (!anexos.some((a) => a.file?.size)) return;

  const grandes = [];
  const resto = [...anexos].sort((a, b) => (b.file?.size || 0) - (a.file?.size || 0));
  const total = () => resto.reduce((s, a) => s + (a.file?.size || 0), 0);
  while (resto.length && ((resto[0].file?.size || 0) > POR_ARQUIVO || total() > TOTAL)) grandes.push(resto.shift());
  if (!grandes.length) return;

  const context = sendCtx.context || globalThis.getContext?.();
  if (!context) return;
  try {
    const linhas = [];
    for (const a of grandes) linhas.push(await store.enviarArquivo(a.file, context));
    sendCtx.attachments = anexos.filter((a) => !grandes.includes(a));
    sendCtx.message = [sendCtx.message, ...linhas].filter((t) => t && t.trim()).join("\n");
  } catch (e) {
    sendCtx.cancel = true; // keep the text and attachments in the composer
    globalThis.toastFrontendError?.(`Não consegui enviar um arquivo grande: ${e.message}. Nada foi enviado; tente de novo.`, "Anexos");
  }
}

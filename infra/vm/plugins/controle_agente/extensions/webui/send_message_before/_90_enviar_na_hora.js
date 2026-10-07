// With the agent working, Enter delivers the message right away (like Grok) instead of
// parking it in the queue until the whole task ends. The agent reads it at its next
// step: within a second during commands, or as soon as the model starts answering.
import * as api from "/js/api.js";
import { store as chatsStore } from "/components/sidebar/chats/chats-store.js";
import { store as inputStore } from "/components/chat/input/input-store.js";

export default async function enviarNaHora(sendCtx) {
  if (sendCtx.cancel || !chatsStore.selectedContext?.running) return;
  const message = (sendCtx.message || "").trim();
  const attachments = sendCtx.attachments || [];
  if (!message && !attachments.length) return; // empty Enter keeps its usual meaning

  sendCtx.cancel = true;
  const context = sendCtx.context;
  const messageId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  inputStore.reset();

  try {
    let response;
    if (attachments.length) {
      const form = new FormData();
      form.append("text", message);
      form.append("context", context);
      form.append("message_id", messageId);
      for (const a of attachments) form.append("attachments", a.file || a);
      response = await api.fetchApi("/message_async", { method: "POST", body: form });
    } else {
      response = await api.fetchApi("/message_async", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: message, context, message_id: messageId }),
      });
    }
    if (!response.ok) throw new Error(await response.text());
  } catch (e) {
    inputStore.message = message; // give the text back so nothing is lost
    globalThis.toastFetchError?.("Não consegui enviar a mensagem", e);
  }
}

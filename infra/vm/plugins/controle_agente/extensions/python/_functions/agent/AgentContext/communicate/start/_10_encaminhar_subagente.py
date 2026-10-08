"""A message typed in a subordinate's chat goes to the chat that started it.

Subordinate and parallel-worker chats show up in the chat list like any other, so the user may
write in one. Their agent only knows the task it was handed (no logins, links or decisions of
the main chat): asked "did new exam results come out?" it looked at the phone's home screen and
asked the user to open the portal. AgentContext.communicate is only reached by messages from the
UI/API (call_subordinate hands its task over directly), so a message arriving here for a
subordinate chat came from the user: forward it to the parent chat, show it there as the user's
message and leave a note in the subordinate chat saying where the answer will be.
"""

from helpers.extension import Extension


def _parent_id(ctx) -> str:
    try:
        pid = ctx.get_output_data("parent_context_id") or ""
    except Exception:
        pid = ""
    return pid or ctx.get_data("_parallel_parent_context_id") or ""


class EncaminharSubagente(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        try:
            args = (data or {}).get("args") or ()
            ctx = args[0] if args else None
            msg = args[1] if len(args) > 1 else (data or {}).get("kwargs", {}).get("msg")
            if ctx is None or msg is None or not (msg.message or msg.attachments):
                return
            pid = _parent_id(ctx)
            if not pid or pid == ctx.id:
                return
            from agent import AgentContext
            from helpers import message_queue as mq

            parent = AgentContext.get(pid)
            if parent is None:
                return
            here = ctx.name or ctx.id
            there = parent.name or parent.id
            ctx.log.log(
                type="info",
                content=f"Esta conversa é de um subagente da conversa **{there}** e não guarda o contexto dela. "
                f"Sua mensagem foi encaminhada para **{there}** — a resposta aparece lá.",
            )
            mq.log_user_message(parent, msg.message, msg.attachments or [], source=f" (enviada em “{here}”)")
            data["result"] = parent.communicate(msg)
        except Exception as exc:  # never lose the message: fall back to the normal path
            print(f"controle_agente: encaminhar subagente falhou: {exc}", flush=True)

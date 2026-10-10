"""Keep the chat's last-activity time current, so "most recent first" puts active chats on top.

Agent.hist_add_message stamps `last_message` on the agent, but the sidebar reads the context's
`last_message`, which therefore stayed at the chat's creation time."""

from helpers.extension import Extension


class UltimaAtividade(Extension):
    def execute(self, **kwargs):
        quando = getattr(self.agent, "last_message", None)
        contexto = getattr(self.agent, "context", None)
        if quando and contexto is not None:
            contexto.last_message = quando

"""Keep the text of the main agent's answer (tool_execute_after gets no arguments)."""

from helpers.extension import Extension


class GuardarResposta(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if self.agent and self.agent.number == 0 and tool_name == "response":
            args = tool_args or {}
            self.agent.set_data("_whatsapp_resposta", str(args.get("text") or args.get("message") or ""))

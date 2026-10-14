"""Count the agent's steps in the current task (one tool call = one step) for the guards in helpers/guardas.py."""

from helpers.extension import Extension


class ContarPasso(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if self.agent:
            self.agent.data["_guardas_passos"] = int(self.agent.data.get("_guardas_passos") or 0) + 1

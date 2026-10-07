"""Keep the current tool's arguments for the loop detector (tool_execute_after gets none)."""

from helpers.extension import Extension


class LembrarArgumentos(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if self.agent:
            self.agent.set_data("_detector_loop_args", dict(tool_args or {}))

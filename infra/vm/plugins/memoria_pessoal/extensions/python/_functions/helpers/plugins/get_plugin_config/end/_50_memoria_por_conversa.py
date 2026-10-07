"""Give every standalone chat its own long-term (vector) memory.

Agent Zero already isolates memory per project ("agent"); chats outside a
project would otherwise share one global memory. Here the _memory config gets
a per-chat subdir, so facts from one conversation never surface in another.
Shared facts about the user live in /a0/usr/memoria/sobre-voce.md instead.
"""

from helpers import projects
from helpers.extension import Extension


class MemoriaPorConversa(Extension):
    def execute(self, data: dict, **kwargs):
        args = data.get("args") or ()
        name = args[0] if args else (data.get("kwargs") or {}).get("plugin_name")
        result = data.get("result")
        if name != "_memory" or not self.agent or not isinstance(result, dict):
            return
        if projects.get_context_project_name(self.agent.context):
            return  # project memory isolation handles agents
        data["result"] = {**result, "agent_memory_subdir": f"chats/{self.agent.context.id}"}

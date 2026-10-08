"""Give every standalone chat its own long-term (vector) memory.

Agent Zero already isolates memory per project ("agent"); chats outside a
project would otherwise share one global memory. Here the _memory config gets
a per-chat subdir, so facts from one conversation never surface in another.
Shared facts about each person live in /a0/usr/memoria/usuarios/<login>.md instead.
"""

from helpers import projects
from helpers.extension import Extension

RECALL_LIMITS = {"memory_recall_memories_max_result": 3, "memory_recall_solutions_max_result": 1}


class MemoriaPorConversa(Extension):
    def execute(self, data: dict, **kwargs):
        args = data.get("args") or ()
        name = args[0] if args else (data.get("kwargs") or {}).get("plugin_name")
        result = data.get("result")
        if name != "_memory" or not self.agent or not isinstance(result, dict):
            return
        # The recalled memories and "solutions from the past" ride along with every model call
        # (~20k characters with the defaults of 5 and 3): keep only the closest ones.
        result = {**result, **RECALL_LIMITS}
        if not projects.get_context_project_name(self.agent.context):  # project isolation handles agents
            result["agent_memory_subdir"] = f"chats/{self.agent.context.id}"
        data["result"] = result

"""Give every standalone chat its own long-term (vector) memory.

Agent Zero already isolates memory per project ("agent"); chats outside a
project would otherwise share one global memory. Here the _memory config gets
a per-chat subdir, so facts from one conversation never surface in another.
Shared facts about each person live in /a0/usr/memoria/usuarios/<login>.md instead.
"""

import json
import os

from helpers import projects
from helpers.extension import Extension

RECALL_LIMITS = {"memory_recall_memories_max_result": 3, "memory_recall_solutions_max_result": 1}
TAREFAS = "/a0/usr/scheduler/tasks.json"
_tarefas = {"mtime": None, "ids": set()}


def chat_de_tarefa(ctx_id: str) -> bool:
    """The chat is the dedicated chat of a scheduled task (the scheduler makes ordinary chats for them)."""
    try:
        mtime = os.path.getmtime(TAREFAS)
        if mtime != _tarefas["mtime"]:
            with open(TAREFAS, encoding="utf-8") as f:
                _tarefas["ids"] = {t.get("context_id") or t.get("uuid") for t in json.load(f).get("tasks", [])}
            _tarefas["mtime"] = mtime
    except Exception:
        return False
    return ctx_id in _tarefas["ids"]


def rodada_sem_novidade(agent) -> bool:
    """A scheduled round that ended with "SEM NOVIDADE" (or skipped by the gate): nothing to learn from it."""
    ultima = str(getattr(getattr(agent, "loop_data", None), "last_response", "") or "")
    return "SEM NOVIDADE" in ultima[:400] and chat_de_tarefa(agent.context.id)


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
        # 20/10 (prompt enxuto): ~40 rounds a day end "SEM NOVIDADE"; memorizing each one cost 2+ model calls for nothing
        if result.get("memory_memorize_enabled") and rodada_sem_novidade(self.agent):
            result["memory_memorize_enabled"] = False
        if not projects.get_context_project_name(self.agent.context):  # project isolation handles agents
            result["agent_memory_subdir"] = f"chats/{self.agent.context.id}"
        data["result"] = result

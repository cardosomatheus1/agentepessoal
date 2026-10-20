"""Replaces Agent Zero's extensions/python/message_loop_prompts_after/_75_include_workdir_extras.py (same file name: a
plugin extension with the name of a core one is loaded instead of it).

21/10: outside a project, Agent Zero put the file tree of /a0/usr/workdir (settings `workdir_show`) in the extras of
every step: ~9,500 characters, measured on a request of Matheus's chat, sent again whenever any file in the folder
changed (delegados/, saidas/… change all the time). Hermes Agent never sends a file tree: the agent lists the folder
itself when it needs to. Here a chat outside a project gets one fixed line with the folder (the same every step, so
cache_prompt sends it once). Inside a project with its file structure turned on, Agent Zero's behaviour is kept as it
was (the project owner asked for it).

Core file this mirrors (md5 checked by tests/suite.py): ca5fb21762e53e5130fd46a4c0784496."""

from agent import LoopData
from helpers.extension import Extension

LINHA = ("Pasta de trabalho: {pasta} (para ver o que tem nela, liste com `ls`/`find` no terminal ou leia com "
         "`text_editor`; a lista não vem aqui para o prompt ficar curto).")


def linha_da_pasta(pasta: str) -> str:
    return LINHA.format(pasta=pasta or "/a0/usr/workdir")


class IncludeWorkdirExtras(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return
        from helpers import projects

        if projects.get_context_project_name(self.agent.context):
            await self._nucleo(loop_data)
            return
        from helpers import settings

        cfg = settings.get_settings_for_prompt()
        if not bool(cfg.get("workdir_show")):
            return
        loop_data.extras_temporary["project_file_structure"] = linha_da_pasta(str(cfg.get("workdir_path") or ""))

    async def _nucleo(self, loop_data):
        """Agent Zero's own extension (the project branch is what runs: the chat is in a project)."""
        import importlib.util
        from pathlib import Path

        caminho = Path("/a0/extensions/python/message_loop_prompts_after/_75_include_workdir_extras.py")
        spec = importlib.util.spec_from_file_location("a0_include_workdir_extras_nucleo", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        await m.IncludeWorkdirExtras(agent=self.agent).execute(loop_data=loop_data)

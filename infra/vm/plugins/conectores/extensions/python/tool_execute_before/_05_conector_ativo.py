"""A connector tool that runs in this chat (called by its name, e.g. inside `parallel`, or already in the list) stays in
the chat's native tool list from then on (helpers/sob_demanda.py). Runs after _03_dono_conector, which refuses another
person's connector."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("conectores_carregar", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)


class ConectorAtivo(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if not self.agent or "." not in (tool_name or ""):
            return
        try:
            s = carregar.modulo("sob_demanda")
            if s.servidor_e_nome(tool_name)[0] in s.ENXUTOS and not s.na_lista(tool_name, s.ativas(self.agent.context), False):
                s.ativar(self.agent.context, [tool_name])
        except Exception as exc:  # the call itself goes on
            print(f"conectores: ferramenta não marcada como ativa: {type(exc).__name__}: {exc}", flush=True)

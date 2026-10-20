"""Right after a tool's result enters the history, the first time in this chat, its manual (the full description the
tool list no longer carries) goes in as the next message. Again only if it left what the model sees (summarized).
Never after the final answer. A separate message, not part of the result: big results are cut to head + tail
(resultados_grandes) and the manual must arrive whole."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("prompt_enxuto_carregar", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)


def nome_da_ferramenta(data: dict) -> str:
    args, kw = data.get("args") or (), data.get("kwargs") or {}
    nome = kw.get("tool_name") or (args[1] if len(args) > 1 else "")
    return str(nome or "")


class ManualNaPrimeira(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        agent = self.agent
        if not isinstance(data, dict) or agent is None or data.get("exception"):
            return
        try:
            e, i = carregar.modulo("enxuto"), carregar.modulo("indice")
            nome = nome_da_ferramenta(data)
            if not nome or nome in i.SEM_MANUAL or not e.ligado():
                return
            texto = e.manual(nome, texto_modo=e.modo_texto(agent))
            if not texto or e.no_historico(agent.history.output(), e.MARCA.format(nome=nome)):
                return
            agent.hist_add_message(False, content=texto)
        except Exception as exc:  # the tool result is already in; the manual is a bonus
            print(f"prompt_enxuto: manual de ferramenta não entrou: {type(exc).__name__}: {exc}", flush=True)

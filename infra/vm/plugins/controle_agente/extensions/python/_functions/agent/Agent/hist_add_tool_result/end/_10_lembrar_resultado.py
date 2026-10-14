"""Remember the history item of a result just added, so a later identical one can point at it while it is still
whole in the history (start/_10_resultado_repetido.py)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("controle_agente_guardas", _RAIZ / "helpers" / "guardas.py")
guardas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guardas)


class LembrarResultado(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        agent_data = getattr(self.agent, "data", None)
        if not isinstance(data, dict) or not isinstance(agent_data, dict):
            return
        k = agent_data.pop("_guardas_resultado_pendente", "")
        if k and not data.get("exception"):
            guardas.Resultados(agent_data.get("_guardas_resultados")).guardar(k, data.get("result"))

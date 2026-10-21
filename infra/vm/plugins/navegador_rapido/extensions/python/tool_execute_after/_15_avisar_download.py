"""A download saved under its real name is reported in the very next tool result (helpers/downloads.py)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_ARQ = Path(__file__).resolve().parents[3] / "helpers" / "downloads.py"
_spec = importlib.util.spec_from_file_location("navegador_rapido_downloads_aviso", _ARQ)
downloads = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(downloads)


_ARQ_C = Path(__file__).resolve().parents[3] / "helpers" / "correcoes.py"
_spec_c = importlib.util.spec_from_file_location("navegador_rapido_correcoes_aviso", _ARQ_C)
correcoes = importlib.util.module_from_spec(_spec_c)
_spec_c.loader.exec_module(correcoes)


def _dialogos(contexto: str) -> str:
    """JS dialogs the site opened since the last browser result (correcoes.responder_dialogo)."""
    from plugins._browser.helpers import runtime

    pendentes = correcoes._tabela(runtime._BrowserRuntimeCore, correcoes.DIALOGOS).pop(contexto, [])
    return correcoes.aviso_dialogos(pendentes)


class AvisarDownload(Extension):
    async def execute(self, response=None, tool_name: str = "", **kwargs):
        try:
            texto = downloads.aviso(downloads.a_avisar())
            if tool_name == "browser":
                texto += _dialogos(str(self.agent.context.id))
                texto += self.agent.get_data("_navegador_erros") or ""
                self.agent.set_data("_navegador_erros", "")
            if texto and response is not None and isinstance(getattr(response, "message", None), str):
                response.message += texto
        except Exception as exc:  # never break a tool result over this
            print(f"navegador_rapido: aviso de download: {exc}", flush=True)

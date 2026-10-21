"""A download saved under its real name is reported in the very next tool result (helpers/downloads.py)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_ARQ = Path(__file__).resolve().parents[3] / "helpers" / "downloads.py"
_spec = importlib.util.spec_from_file_location("navegador_rapido_downloads_aviso", _ARQ)
downloads = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(downloads)


class AvisarDownload(Extension):
    async def execute(self, response=None, tool_name: str = "", **kwargs):
        try:
            texto = downloads.aviso(downloads.a_avisar())
            if texto and response is not None and isinstance(getattr(response, "message", None), str):
                response.message += texto
        except Exception as exc:  # never break a tool result over this
            print(f"navegador_rapido: aviso de download: {exc}", flush=True)

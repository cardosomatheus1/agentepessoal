"""Third-party text reaches the model marked as data, not orders; and the page the browser is on is remembered, so the
prospecting window only applies on the Instagram (12/10 review). Runs after the vault's masking (_08)."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def revisor():
    nome = "aprovacoes_revisor"
    caminho = RAIZ / "helpers" / "revisor.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        for estado in ("PENDENTES", "PEDIDOS"):  # waiting approvals survive a reload
            if antigo is not None and hasattr(antigo, estado):
                setattr(modulo, estado, getattr(antigo, estado))
        sys.modules[nome] = modulo
    return sys.modules[nome]


class DadoExterno(Extension):
    async def execute(self, response=None, tool_name: str = "", **kwargs):
        if not self.agent or response is None or not isinstance(getattr(response, "message", None), str):
            return
        try:
            rv = revisor()
            if (tool_name or "").lower() == "browser":
                url = rv.url_atual(response.message)
                if url:
                    self.agent.context.set_data("_navegador_url", url)
            response.message = rv.marcar_dado_externo(tool_name, response.message)
        except Exception as exc:  # never breaks the tool's answer
            print(f"aprovacoes: dado externo: {exc}", flush=True)

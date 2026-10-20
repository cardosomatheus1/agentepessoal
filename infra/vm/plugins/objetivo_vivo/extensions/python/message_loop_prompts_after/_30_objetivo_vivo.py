"""The chat's live goal at the end of the prompt, as a persistent extra: cache_prompt (_98) writes it into the
history only when it changed or fell far behind, so the start of the prompt stays the same (provider cache)."""

import importlib.util
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("objetivo_vivo_carregar", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)


class ObjetivoVivo(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        agent = self.agent
        extras = getattr(loop_data, "extras_persistent", None)
        if agent is None or not isinstance(extras, dict):
            return
        try:
            o = carregar.objetivo()
            if not o.conversa_de_pessoa(agent):
                return
            ctx = agent.context
            texto = o.bloco(ctx.get_data(o.CHAVE), o.dono(agent), bool(ctx.get_data("whatsapp_de")))
            if texto:
                extras[o.EXTRA] = texto
        except Exception as exc:
            print(f"objetivo_vivo: bloco não montado: {type(exc).__name__}: {exc}", flush=True)

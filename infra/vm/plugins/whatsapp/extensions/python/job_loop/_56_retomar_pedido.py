"""A phone request the agent was working on when it restarted (memguard, a crash) is resumed or asked about.

The marks are written by api/receber.py and closed by the final answer; the rules (15 min, once per request, not in
a restart loop) are in helpers/turnos.py (rodada), tested there. The job loop starts after the chats are loaded
(run_ui.init_a0), so its first pass in a new process is the restart hook; startup_migration runs before that.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension


def _helper(nome: str, arquivo: str):
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / arquivo
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        for estado in ("PENDENTES", "PEDIDOS"):
            if antigo is not None and hasattr(antigo, estado):
                setattr(modulo, estado, getattr(antigo, estado))
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _principal(usuario: str):
    from agent import AgentContext

    return next((c for c in AgentContext.all() if c.get_data("whatsapp_de") == usuario
                 and not c.get_data("whatsapp_paralela")), None)


class RetomarPedido(Extension):
    async def execute(self, **kwargs):
        from agent import AgentContext

        t, p = _helper("whatsapp_turnos", "turnos.py"), _helper("whatsapp_ponte", "ponte.py")
        for usuario, texto, botoes in t.rodada(AgentContext.get, _principal):
            erro = await asyncio.to_thread(p.enviar, usuario, texto, "", "", botoes, "resposta", True, reenviar=True)
            if erro:
                print(f"whatsapp: restart notice to {usuario} not delivered (kept for a retry): {erro}", flush=True)

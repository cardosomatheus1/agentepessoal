"""Send a file, image or short note to the WhatsApp of the person who owns this chat.

Only the chat's owner can be reached (by login name; the bridge maps it to the number), so this
tool cannot message third parties.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

from helpers.tool import Response, Tool


def ponte():
    nome = "whatsapp_ponte"
    if nome not in sys.modules:
        caminho = Path(__file__).resolve().parents[1] / "helpers" / "ponte.py"
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        sys.modules[nome] = modulo
    return sys.modules[nome]


class WhatsappEnviar(Tool):
    async def execute(self, arquivo: str = "", texto: str = "", legenda: str = "", **kwargs) -> Response:
        if not arquivo and not texto:
            return Response(message="Informe `arquivo` (caminho em /a0/usr) e/ou `texto`.", break_loop=False)
        p = ponte()
        destino = p.dono(self.agent.context)
        erro = await asyncio.to_thread(p.enviar, destino, texto, arquivo, legenda)
        if erro:
            return Response(message=f"Não enviado: {erro}", break_loop=False)
        return Response(message="Enviado no WhatsApp do usuário.", break_loop=False)

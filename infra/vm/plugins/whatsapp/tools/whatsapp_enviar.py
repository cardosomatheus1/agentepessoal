"""Send a file, image or short note to the WhatsApp of the person who owns this chat.

Only the chat's owner can be reached (by login name; the bridge maps it to the number), so this
tool cannot message third parties.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

from helpers.tool import Response, Tool


def carregar(nome: str, caminho: Path):
    """Load a helper by path, again when the file changed (a deploy), keeping pending state."""
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        if antigo is not None and hasattr(antigo, "PENDENTES"):
            modulo.PENDENTES = antigo.PENDENTES
        sys.modules[nome] = modulo
    return sys.modules[nome]


def ponte():
    nome = "whatsapp_ponte"
    caminho = Path(__file__).resolve().parents[1] / "helpers" / "ponte.py"
    return carregar(nome, caminho)


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

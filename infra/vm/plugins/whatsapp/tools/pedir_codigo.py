"""Ask the chat's owner, on WhatsApp, for a one-time code (2FA, SMS, e-mail) and wait for it.

The next short WhatsApp message from that person is taken as the code and handed back here, in
whatever chat asked for it. The code goes to the agent (it is short-lived); passwords never do —
they live in the vault (§§secret).
"""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

from helpers.tool import Response, Tool

ESPERA = 10 * 60


def carregar(nome: str, caminho: Path):
    """Load a helper by path, again when the file changed (a deploy), keeping pending state."""
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


def ponte():
    return carregar("whatsapp_ponte", Path(__file__).resolve().parents[1] / "helpers" / "ponte.py")


class PedirCodigo(Tool):
    async def execute(self, pergunta: str = "", **kwargs) -> Response:
        p = ponte()
        usuario = p.dono(self.agent.context)
        pedido = {"contexto": self.agent.context.id, "codigo": "", "criado": time.time()}
        p.PEDIDOS[usuario] = pedido
        texto = (f"🔑 *Preciso de um código* — {self.agent.context.name or 'conversa'}\n\n"
                 f"{pergunta.strip() or 'Código de verificação'}\n\nResponda só com o código.")
        erro = await asyncio.to_thread(p.enviar, usuario, texto)
        if erro:
            p.PEDIDOS.pop(usuario, None)
            return Response(message=f"Não consegui pedir pelo WhatsApp ({erro}). Peça o código ao usuário pela conversa.",
                            break_loop=False)
        await self.set_progress("esperando o código no WhatsApp…")
        try:
            limite = time.time() + ESPERA
            while time.time() < limite:
                if pedido["codigo"]:
                    return Response(message=f"Código recebido do usuário: {pedido['codigo']}", break_loop=False)
                if self.agent.intervention is not None:  # typed in the chat instead
                    codigo = str(getattr(self.agent.intervention, "message", "")).strip()
                    if codigo and len(codigo) <= 40:
                        self.agent.intervention = None
                        return Response(message=f"Código recebido do usuário: {codigo}", break_loop=False)
                    break
                await asyncio.sleep(1)
        finally:
            if p.PEDIDOS.get(usuario) is pedido:
                p.PEDIDOS.pop(usuario, None)
        return Response(message="O usuário não mandou o código a tempo. Diga onde parou e o que falta.", break_loop=False)

"""Ask the person a question with 2-3 options as buttons on the phone, and wait for the choice (helpers/pergunta.py)."""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

from helpers.tool import Response, Tool

ESPERA_PADRAO, ESPERA_MAX = 15, 30  # minutes


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


def ajudante():
    return carregar("whatsapp_pergunta", Path(__file__).resolve().parents[1] / "helpers" / "pergunta.py")


class Perguntar(Tool):
    async def execute(self, pergunta: str = "", opcoes: list | None = None, minutos: int = ESPERA_PADRAO,
                      **kwargs) -> Response:
        p, g, ctx = ponte(), ajudante(), self.agent.context
        usuario = p.dono(ctx)
        try:
            texto, botoes = g.montar(usuario, ctx.id, pergunta, opcoes or [])
        except ValueError as exc:
            return Response(message=f"Pergunta NÃO enviada: {exc}. Mande `opcoes` com 2 ou 3 textos curtos.",
                            break_loop=False)
        estado = {"pergunta": " ".join(str(pergunta).split()), "escolha": "", "em": time.time(),
                  "opcoes": [" ".join(str(o).split()) for o in opcoes if str(o).strip()]}
        ctx.set_data(g.CHAVE, estado)
        erro = await asyncio.to_thread(p.enviar, usuario, texto, "", "", botoes, "urgente", True)
        if erro:
            ctx.set_data(g.CHAVE, None)
            return Response(message=f"A pergunta não chegou ao celular ({erro}). Pergunte na resposta, com as opções "
                                    "numeradas.", break_loop=False)
        try:
            minutos = max(1, min(int(minutos or ESPERA_PADRAO), ESPERA_MAX))
        except (TypeError, ValueError):
            minutos = ESPERA_PADRAO
        await self.set_progress("esperando a escolha no celular…")
        limite = time.time() + minutos * 60
        while time.time() < limite:
            atual = ctx.get_data(g.CHAVE) or {}
            if atual.get("escolha"):
                return Response(message=f"Escolha da pessoa: «{atual['escolha']}». Continue a tarefa com ela agora.",
                                break_loop=False)
            if self.agent.intervention is not None:  # answered by typing in the chat instead
                resposta = str(getattr(self.agent.intervention, "message", "")).strip()
                if resposta:
                    self.agent.intervention = None
                    ctx.set_data(g.CHAVE, dict(atual, escolha=resposta))
                    return Response(message=f"Resposta da pessoa: «{resposta}». Continue a tarefa com ela agora.",
                                    break_loop=False)
                break
            await asyncio.sleep(1)
        return Response(message=(f"Sem escolha em {minutos} min (os botões continuam valendo: a escolha chega depois como "
                                 "mensagem). Se uma opção for segura e fácil de desfazer, siga com ela e diga qual; senão, "
                                 "termine dizendo o que fez e que espera a escolha."), break_loop=False)

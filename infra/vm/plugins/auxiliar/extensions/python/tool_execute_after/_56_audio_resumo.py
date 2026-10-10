"""The morning summary (scheduled task named "📰…") also arrives as a short voice note, to listen on the go —
unless it has nothing to say."""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

from helpers.extension import Extension


def _carregar(nome: str, caminho: Path):
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _enviar_audio(a, ponte, login: str, texto: str, pasta: Path) -> None:
    destino = pasta / f"resumo-{time.strftime('%Y%m%d-%H%M')}.ogg"
    erro = a.audio(a.roteiro_falado(texto), destino)
    if erro:
        print(f"auxiliar: morning voice note failed: {erro}", flush=True)
        return
    erro = ponte.enviar(login, arquivo=str(destino), legenda="🎧 Resumo da manhã em áudio", tipo="progresso")
    if erro:
        print(f"auxiliar: morning voice note not delivered: {erro}", flush=True)


class AudioResumo(Extension):
    async def execute(self, response=None, tool_name: str = "", **kwargs):
        agent = self.agent
        if not agent or agent.number != 0 or tool_name != "response" or response is None:
            return
        if not getattr(response, "break_loop", False):
            return
        ponte = sys.modules.get("whatsapp_ponte")
        if ponte is None:
            return
        if not (ponte.tarefa(agent.context) or "").startswith("📰"):
            return
        texto = agent.get_data("_whatsapp_resposta") or ""
        if not texto.strip() or texto.strip().upper().startswith(ponte.SILENCIO):
            return
        raiz = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
        a = _carregar("auxiliar_helper", raiz / "helpers" / "auxiliar.py")
        if not a.vale_audio(texto):
            return
        login = ponte.dono(agent.context) or "matheus"
        pasta = Path("/a0/usr/auxiliar/audio")
        for velho in pasta.glob("resumo-*.ogg") if pasta.exists() else []:
            if time.time() - velho.stat().st_mtime > 7 * 86400:
                velho.unlink(missing_ok=True)
        asyncio.create_task(asyncio.to_thread(_enviar_audio, a, ponte, login, texto, pasta))

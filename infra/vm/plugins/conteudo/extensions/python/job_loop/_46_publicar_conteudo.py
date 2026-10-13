"""Publishes today's @raiz.connect post when its hour comes (helpers/conteudo.py). Runs in a thread so the loop never
waits for Meta; the reservation inside rodar() keeps a second pass from publishing the same post."""

import asyncio
import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

_spec = importlib.util.spec_from_file_location("conteudo_helper", Path(__file__).resolve().parents[3] / "helpers" / "conteudo.py")
conteudo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conteudo)
_RODANDO = {"sim": False}


def _avisar(texto: str) -> None:
    caminho = Path("/a0/usr/plugins/whatsapp/helpers/ponte.py")
    try:
        ponte = sys.modules.get("whatsapp_ponte")
        if ponte is None and caminho.exists():
            s = importlib.util.spec_from_file_location("whatsapp_ponte", caminho)
            ponte = importlib.util.module_from_spec(s)
            s.loader.exec_module(ponte)
        erro = ponte.enviar("matheus", texto, tipo="urgente") if ponte else "ponte indisponível"
        if erro:
            print(f"conteudo: aviso não saiu: {erro}", flush=True)
    except Exception as exc:
        print(f"conteudo: aviso não saiu: {exc}", flush=True)


def _passo() -> None:
    try:
        if not conteudo.devido():
            return
        api = conteudo.api_do_cofre()
        if api is None:
            print("conteudo: sem token da Meta no cofre", flush=True)
            return
        r = conteudo.rodar(api, _avisar)
        if r:
            print(f"conteudo: {r}", flush=True)
    except Exception as exc:
        print(f"conteudo: {type(exc).__name__}: {exc}", flush=True)
    finally:
        _RODANDO["sim"] = False


class PublicarConteudo(Extension):
    async def execute(self, **kwargs):
        if _RODANDO["sim"] or not (conteudo.PASTA / "agenda.json").exists():
            return
        _RODANDO["sim"] = True
        asyncio.get_running_loop().run_in_executor(None, _passo)

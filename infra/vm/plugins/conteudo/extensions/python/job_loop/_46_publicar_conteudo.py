"""Publishes today's @raiz.connect post when its hour comes (helpers/conteudo.py). Runs in a thread so the loop never
waits for Meta; the reservation inside rodar() keeps a second pass from publishing the same post."""

import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

from helpers.extension import Extension

_CAMINHO = Path(__file__).resolve().parents[3] / "helpers" / "conteudo.py"
_ATUAL: dict = {}
_RODANDO = {"sim": False}


def _helper():
    """The helper, re-read when its file changes (17/10: the framework only reloads this extension when a file under
    extensions/ changes, so a helper-only deploy stayed invisible to the running loop). Each load writes
    PASTA/rotina.json with the pid and the sha256 of the helper actually in memory: that is the proof of what runs."""
    st = _CAMINHO.stat()
    marca = (st.st_mtime_ns, st.st_size)
    if _ATUAL.get("marca") != marca:
        fonte = _CAMINHO.read_bytes()
        spec = importlib.util.spec_from_file_location("conteudo_helper", _CAMINHO)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _ATUAL.update(marca=marca, modulo=m)
        try:
            (m.PASTA / "rotina.json").write_text(json.dumps({
                "pid": os.getpid(), "helper": str(_CAMINHO), "helper_sha256": hashlib.sha256(fonte).hexdigest(),
                "tipos": list(m.TIPOS), "carregado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z")}), encoding="utf-8")
        except OSError as exc:
            print(f"conteudo: rotina.json não gravou: {exc}", flush=True)
    return _ATUAL["modulo"]


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
        conteudo = _helper()
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
        if _RODANDO["sim"]:
            return
        try:
            if not (_helper().PASTA / "agenda.json").exists():
                return
        except Exception as exc:
            print(f"conteudo: helper não carregou: {type(exc).__name__}: {exc}", flush=True)
            return
        _RODANDO["sim"] = True
        asyncio.get_running_loop().run_in_executor(None, _passo)

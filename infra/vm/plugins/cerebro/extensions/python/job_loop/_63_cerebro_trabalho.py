"""Each job-loop pass: the operator's turns waiting in /a0/usr/segundo_cerebro/entrada go to the Pasta
(helpers/trabalho.py), in a thread so the loop never waits on the model; one pass at a time."""

import importlib.util
import sys
import threading
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_RODANDO = threading.Lock()


def mods():
    nome, caminho = "cerebro_modulos", RAIZ / "helpers" / "modulos.py"
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        sys.modules[nome] = m
    return sys.modules[nome]


def trabalho():
    nome, caminho = "cerebro_trabalho", RAIZ / "helpers" / "trabalho.py"
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def _rodar():
    if not _RODANDO.acquire(blocking=False):
        return
    try:
        m = mods()
        avisar = lambda login, linha: m.m("ponte").enviar(login, linha, tipo="progresso")  # noqa: E731
        for r in trabalho().processar(m, avisar=avisar):
            print(f"cerebro: trabalho do operador {r}", flush=True)
    except Exception as exc:
        print(f"cerebro: trabalho do operador falhou: {type(exc).__name__}: {exc}", flush=True)
    finally:
        _RODANDO.release()


class CerebroTrabalho(Extension):
    async def execute(self, **kwargs):
        try:
            if any(trabalho().ENTRADA.glob("*.json")):
                threading.Thread(target=_rodar, daemon=True, name="cerebro-trabalho").start()
        except Exception as exc:
            print(f"cerebro: trabalho do operador não iniciou: {type(exc).__name__}: {exc}", flush=True)

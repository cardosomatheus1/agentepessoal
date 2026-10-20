"""Once a week, the container's old temporary files and package caches go (helpers/temporarios.py), logged to
/a0/usr/limpeza/log.jsonl. Runs in a thread so the job loop never waits on the disk."""

import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
INTERVALO = 7 * 86400
MARCA = Path("/a0/usr/marcas/limpeza_temporarios")
LOG = Path("/a0/usr/limpeza/log.jsonl")


def _helper():
    nome, caminho = "limpeza_temporarios", RAIZ / "helpers" / "temporarios.py"
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def na_hora(marca: Path = MARCA, intervalo: float = INTERVALO) -> bool:
    """At most once per intervalo; the time lives in the marker's mtime (job-loop modules are reloaded every pass)."""
    try:
        if time.time() - marca.stat().st_mtime < intervalo:
            return False
    except OSError:
        pass
    try:
        marca.parent.mkdir(parents=True, exist_ok=True)
        marca.touch()
    except OSError:
        return False
    return True


def _rodar() -> None:
    try:
        r = _helper().limpar()
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps({"em": time.time(), "temporarios": len(r["apagados"]), "liberado_mb": r["liberado_mb"]}) + "\n")
        print(f"limpeza: temporários antigos e caches apagados, {r['liberado_mb']} MB", flush=True)
    except Exception as exc:
        print(f"limpeza: temporários não limpos: {type(exc).__name__}: {exc}", flush=True)


class LimparTemporarios(Extension):
    async def execute(self, **kwargs):
        if na_hora():
            asyncio.get_running_loop().run_in_executor(None, _rodar)

"""Conferência (12/10 review, §4.1): every 30 min, without a model, look at the action ledger for what needs a look
(today: the same text to the same person executed twice) and tell the person once per finding."""

import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
ESTADO = Path("/a0/usr/central/conferencia.json")  # module globals reset on every job loop pass: state in a file
INTERVALO = 30 * 60


def carregar(nome: str, caminho: Path):
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


class Conferencia(Extension):
    async def execute(self, **kwargs):
        try:
            ultima = json.loads(ESTADO.read_text(encoding="utf-8")).get("em", 0)
        except (OSError, ValueError):
            ultima = 0
        if time.time() - ultima < INTERVALO:
            return
        try:
            ESTADO.parent.mkdir(parents=True, exist_ok=True)
            ESTADO.write_text(json.dumps({"em": time.time()}), encoding="utf-8")
            livro = carregar("central_livro", RAIZ / "helpers" / "livro.py")
            ponte = carregar("whatsapp_ponte", Path("/a0/usr/plugins/whatsapp/helpers/ponte.py"))
            for login in livro.logins():
                for achado in livro.conferir(login):
                    if livro.novo_alerta(achado["chave"], login, achado["texto"]):
                        erro = await asyncio.to_thread(ponte.enviar, login, achado["texto"], "", "", None, "urgente")
                        print(f"central: conferência avisou {login}: {achado['chave']}" + (f" (falhou: {erro})" if erro else ""),
                              flush=True)
        except Exception as exc:  # never stops the job loop
            print(f"central: conferência falhou: {type(exc).__name__}: {exc}", flush=True)

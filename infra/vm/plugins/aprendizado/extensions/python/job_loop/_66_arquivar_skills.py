"""Once a day: the skills this plugin wrote that nobody loaded nor rewrote in 30 days go to the archive (22/10, skill
hygiene), and Matheus gets one line on the phone saying which."""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
ESTADO = {"ultimo": 0.0}
CADA = 24 * 3600


def _passo() -> None:
    try:
        spec = importlib.util.spec_from_file_location("aprendizado_helper_job", RAIZ / "helpers" / "aprender.py")
        a = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(a)
        if a.DESLIGADO.exists():
            return
        a.registrar_uso("")  # starts the count the first time (nothing is archived before 30 days of counting)
        feitas = a.arquivar_paradas()
        if feitas:
            ponte = Path("/a0/usr/plugins/whatsapp/helpers/ponte.py")
            if ponte.exists():
                s = importlib.util.spec_from_file_location("whatsapp_ponte_arquivo", ponte)
                p = importlib.util.module_from_spec(s)
                s.loader.exec_module(p)
                p.enviar("matheus", f"📚 Arquivei {len(feitas)} skill(s) que ninguém usou em 30 dias: {', '.join(feitas)}. "
                                    "Estão em /a0/usr/aprendizado/arquivo/ se precisar de volta.", tipo="progresso")
    except Exception as exc:
        print(f"aprendizado: arquivo de skills: {exc}", flush=True)


class ArquivarSkills(Extension):
    async def execute(self, **kwargs):
        if time.time() - ESTADO["ultimo"] < CADA:
            return
        ESTADO["ultimo"] = time.time()
        asyncio.get_running_loop().run_in_executor(None, _passo)

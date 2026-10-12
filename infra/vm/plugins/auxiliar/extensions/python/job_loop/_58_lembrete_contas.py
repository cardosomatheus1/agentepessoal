"""Bill reminders without a model call: 3 days before, the day before and the day itself, between 8h and 21h."""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

from helpers.extension import Extension

MARCA = Path("/a0/usr/marcas/auxiliar_contas")


def _na_hora(marca: Path, intervalo: float) -> bool:
    """True at most once per intervalo. Job-loop extensions are loaded again on every pass, so a module variable
    never kept the time (12/10 review: "every 10 minutes" ran every minute): the time lives in the marker's mtime."""
    try:
        if time.time() - marca.stat().st_mtime < intervalo:
            return False
    except OSError:
        pass
    try:
        marca.parent.mkdir(parents=True, exist_ok=True)
        marca.touch()
    except OSError:
        pass
    return True


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


class LembreteContas(Extension):
    async def execute(self, **kwargs):
        if not _na_hora(MARCA, 120):
            return
        raiz = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
        try:
            a = _carregar("auxiliar_helper", raiz / "helpers" / "auxiliar.py")
            if not 8 <= a.agora().hour < 21 or not a.PASTA.exists():
                return
            ponte = sys.modules.get("whatsapp_ponte") or _carregar("whatsapp_ponte", Path("/a0/usr/plugins/whatsapp/helpers/ponte.py"))
            for arquivo in a.PASTA.glob("*.json"):
                login = arquivo.stem
                for conta, etapa in a.lembretes_de_contas(login):
                    erro = await asyncio.to_thread(ponte.enviar, login, a.mensagem_conta(conta, etapa), "", "",
                                                   a.botoes_conta(login, conta["id"]), "resposta")
                    if erro:  # not delivered: unmarked, so the next pass tries again
                        a.desfazer_lembrete(login, conta["id"], etapa)
                        print(f"auxiliar: reminder for bill {conta['id']} not delivered (will retry): {erro}", flush=True)
        except Exception as exc:
            print(f"auxiliar: bill reminders failed: {exc}", flush=True)

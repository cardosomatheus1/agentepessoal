"""Bill reminders without a model call: 3 days before, the day before and the day itself, between 8h and 21h."""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

from helpers.extension import Extension

_ultima = {"t": 0.0}


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
        if time.time() - _ultima["t"] < 120:
            return
        _ultima["t"] = time.time()
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
                    if erro:
                        print(f"auxiliar: reminder for bill {conta['id']} not delivered: {erro}", flush=True)
        except Exception as exc:
            print(f"auxiliar: bill reminders failed: {exc}", flush=True)

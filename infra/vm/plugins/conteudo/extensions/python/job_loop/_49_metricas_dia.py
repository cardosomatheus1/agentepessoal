"""Keeps the day's @raiz.connect numbers once a day, near midnight (helpers/conteudo.py metricas_do_dia): followers per
day, so "quantos seguidores ganhei?" has an answer (25/10). In a thread: the loop never waits for Meta."""

import asyncio
import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

_CAMINHO = Path(__file__).resolve().parents[3] / "helpers" / "conteudo.py"
_RODANDO = {"sim": False, "dia": ""}


def _helper():
    m = sys.modules.get("conteudo_helper")
    if m is None or getattr(m, "__file__", "") != str(_CAMINHO):
        spec = importlib.util.spec_from_file_location("conteudo_helper_metricas", _CAMINHO)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    return m


def _passo() -> None:
    try:
        c = _helper()
        api = c.api_do_cofre()
        if api is None:
            return
        r = c.metricas_do_dia(api)
        if r is None or r.get("ok"):  # None after the hour = today is already kept: done for the day
            import datetime as dt
            _RODANDO["dia"] = dt.datetime.now(c._tz()).date().isoformat()
        if r:
            print(f"conteudo: métricas do dia: {r}", flush=True)
    except Exception as exc:
        print(f"conteudo: métricas do dia: {type(exc).__name__}: {exc}", flush=True)
    finally:
        _RODANDO["sim"] = False


class MetricasDia(Extension):
    async def execute(self, **kwargs):
        import datetime as dt
        try:
            c = _helper()
            momento = dt.datetime.now(c._tz())
        except Exception as exc:
            print(f"conteudo: helper não carregou: {type(exc).__name__}: {exc}", flush=True)
            return
        if _RODANDO["sim"] or momento.strftime("%H:%M") < c.HORA_METRICAS or _RODANDO["dia"] == momento.date().isoformat():
            return
        _RODANDO["sim"] = True
        asyncio.get_running_loop().run_in_executor(None, _passo)

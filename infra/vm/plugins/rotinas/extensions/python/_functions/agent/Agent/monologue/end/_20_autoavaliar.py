"""End of a scheduled round (marked at its start by monologue/start/_30_correcoes_agendada.py): the self-assessment
(helpers/autoavaliacao.py) grades it in one line and, when it sees an improvement, proposes it to Matheus with
Aplicar / Não. Background thread: the scheduler is not kept waiting. A round the gate skipped is not assessed; a round
that ended with an error is logged as an infra failure (no model call, no proposal)."""

import importlib.util
import sys
import threading
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
PULO = "SEM NOVIDADE (portão"  # helpers/portao.py PULO


def autoavaliacao():
    nome, caminho = "rotinas_autoavaliacao", RAIZ / "helpers" / "autoavaliacao.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _rodar(marca: dict, resultado, erro) -> None:
    try:
        r = autoavaliacao().autoavaliar(marca["uuid"], marca.get("nome") or marca["uuid"], resultado,
                                        pedido=marca.get("pedido") or "", erro=erro)
        av = r.get("avaliacao") or {}
        print(f"rotinas: autoavaliação de '{marca.get('nome')}': {r['motivo']}"
              + (f" (nota {av.get('nota')}: {av.get('linha')})" if av else ""), flush=True)
    except Exception as exc:  # never visible to him; the next round assesses again
        print(f"rotinas: autoavaliação falhou: {type(exc).__name__}: {exc}", flush=True)


def iniciar(marca: dict, resultado, erro) -> threading.Thread:
    t = threading.Thread(target=_rodar, args=(marca, resultado, erro), daemon=True, name="rotinas-autoavaliacao")
    t.start()
    return t


class Autoavaliar(Extension):
    async def execute(self, data: dict | None = None, **kwargs):
        agente = self.agent
        if data is None or agente is None or getattr(agente, "number", 1) != 0:
            return
        try:
            ctx = agente.context
            marca = ctx.get_data("_autoavaliar")
            if not isinstance(marca, dict) or not marca.get("uuid"):
                return
            ctx.set_data("_autoavaliar", None)
            resultado = data.get("result")
            erro = data.get("exception") if isinstance(data.get("exception"), BaseException) else None
            if erro is None and isinstance(resultado, str) and resultado.startswith(PULO):
                return
            iniciar(marca, resultado if isinstance(resultado, str) else "", erro)
        except Exception as exc:
            print(f"rotinas: autoavaliação não iniciou: {type(exc).__name__}: {exc}", flush=True)

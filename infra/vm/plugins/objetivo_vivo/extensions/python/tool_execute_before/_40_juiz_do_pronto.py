"""Before the final answer of a person's request, an independent check that it is really done (helpers/juiz.py)."""

import asyncio
import importlib.util
from pathlib import Path

from helpers.errors import RepairableException
from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("objetivo_vivo_carregar_juiz", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)
_specj = importlib.util.spec_from_file_location("objetivo_vivo_juiz", _RAIZ / "helpers" / "juiz.py")
juiz = importlib.util.module_from_spec(_specj)
_specj.loader.exec_module(juiz)

ESPERA_S = 45


class JuizDoPronto(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        agent = self.agent
        if tool_name != "response" or agent is None or not isinstance(tool_args, dict):
            return
        recado = ""
        try:
            o = carregar.objetivo()
            if not o.conversa_de_pessoa(agent):
                return
            ctx = agent.context
            estado = ctx.get_data(o.CHAVE)
            passos = juiz.provas(getattr(ctx.log, "logs", []))
            registro = ctx.get_data(juiz.CHAVE)
            if not juiz.deve_julgar(estado, passos, registro):
                return
            resposta = str(tool_args.get("text") or tool_args.get("message") or "")
            texto = await asyncio.wait_for(
                agent.call_utility_model(system=juiz.SISTEMA,
                                         message=juiz.entrada(estado.get("pedido", ""), passos, resposta)),
                ESPERA_S)
            v = juiz.veredito(texto)
            print(f"objetivo_vivo: juiz do pronto: {v}", flush=True)
            if v and not v["pronto"]:
                ctx.set_data(juiz.CHAVE, juiz.contar(estado, registro))
                recado = juiz.recado(v["falta"])
        except Exception as exc:  # the judge never blocks an answer by failing
            print(f"objetivo_vivo: juiz do pronto indisponível: {type(exc).__name__}: {exc}", flush=True)
            return
        if recado:
            raise RepairableException(recado)

"""Tool `passos`: the agreed steps of the person's current request (shown at the end of the prompt by objetivo_vivo)."""

import importlib.util
from pathlib import Path

from helpers.tool import Response, Tool

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("objetivo_vivo_carregar", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)


def executar(agent, passos=None, feitos=None) -> str:
    o = carregar.objetivo()
    if not o.conversa_de_pessoa(agent):
        return "Aqui não há objetivo vivo (rotina, gatilho ou ajudante): siga as instruções da tarefa."
    ctx = agent.context
    estado = ctx.get_data(o.CHAVE) or {}
    if not estado.get("pedido"):
        return "Ainda não há pedido da pessoa nesta conversa; nada registrado."
    if passos is None and feitos in (None, "", []):
        return o.bloco(estado, o.dono(agent), bool(ctx.get_data("whatsapp_de")))
    novo = o.com_passos(estado, passos, feitos)
    if passos is not None and not novo["passos"]:
        return "Nenhum passo válido: mande `passos` como lista de textos (\"[x] feito\", \"[ ] falta\")."
    ctx.set_data(o.CHAVE, novo)
    faltam = [p["texto"] for p in novo["passos"] if not p.get("feito")]
    if not faltam:
        return "Todos os passos feitos. Confira o resultado e dê a resposta final."
    return f"Registrado. Falta(m) {len(faltam)}: " + "; ".join(faltam) + ". Siga para o próximo sem parar."


class Passos(Tool):
    async def execute(self, passos=None, feitos=None, **kwargs):
        return Response(message=executar(self.agent, passos, feitos), break_loop=False)

"""A new message of the person updates the chat's live goal (helpers/objetivo.py): a new request replaces it, a
status question or a confirmation keeps it. The id of the message that holds the current request is kept too:
resumo_seguro never summarizes from it to the end (the task in progress)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("objetivo_vivo_carregar", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)


class ObjetivoNaMensagem(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        if not isinstance(data, dict) or isinstance(data.get("exception"), BaseException):
            return
        try:
            args, kw = data.get("args") or (), data.get("kwargs") or {}
            agent = args[0] if args else self.agent
            mensagem = kw.get("message", args[1] if len(args) > 1 else None)
            o = carregar.objetivo()
            if not o.conversa_de_pessoa(agent):
                return
            texto = str(getattr(mensagem, "message", mensagem) or "")
            msg = data.get("result")
            ctx = agent.context
            antes = ctx.get_data(o.CHAVE) or {}
            depois = o.nova_mensagem(antes, texto, str(getattr(msg, "id", "") or ""))
            if depois != antes:
                ctx.set_data(o.CHAVE, depois)
        except Exception as exc:  # the message is already in the history; the goal is a bonus
            print(f"objetivo_vivo: objetivo não atualizado: {type(exc).__name__}: {exc}", flush=True)

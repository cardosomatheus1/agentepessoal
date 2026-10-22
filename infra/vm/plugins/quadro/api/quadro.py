"""The Tarefas board of the logged-in person: read it, close a task (only the person, here), reopen one, or "Faz pra
mim" (the task gets a chat of its own, like Claude Duet's sub-chats; outcomes also reach the phone)."""

import importlib.util
import sys
from pathlib import Path

from helpers.api import ApiHandler, Request, Response


def quadro():
    caminho = Path(__file__).resolve().parents[1] / "helpers" / "quadro.py"
    antigo = sys.modules.get("quadro_helper")
    if antigo is None or getattr(antigo, "_mtime", None) != caminho.stat().st_mtime:
        spec = importlib.util.spec_from_file_location("quadro_helper", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = caminho.stat().st_mtime
        sys.modules["quadro_helper"] = m
    return sys.modules["quadro_helper"]


def _usuario() -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    u = sep.usuario_da_requisicao() if sep else None
    return (u or "matheus").lower()  # single-user installs: the owner


def _nova_conversa(usuario: str, nome: str, texto: str) -> str:
    from agent import AgentContext, UserMessage
    from helpers import message_queue as mq
    from helpers import projects
    from initialize import initialize_agent

    ctx = AgentContext(config=initialize_agent(), name=nome)
    projects.reconcile_agent_profile(ctx, projects.get_context_project_name(ctx))
    for chave, valor in (("dono", usuario), ("usuario", usuario), ("avisar_sempre", True)):
        ctx.set_data(chave, valor)
    mq.log_user_message(ctx, texto, [], None, source=" (quadro)")
    ctx.communicate(UserMessage(message=texto, attachments=[], id=""))
    return ctx.id


class Quadro(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        q, login = quadro(), _usuario()
        acao, fid = str(input.get("acao") or "ler"), str(input.get("id") or "")
        msg = ""
        if acao in ("concluir", "reabrir", "fazer") and fid:
            f = q.fios()
            fio = f.obter(login, fid)
            if not fio:
                return {"ok": False, "erro": "essa tarefa não existe mais", "quadro": q.montar(login)}
            if acao == "fazer" and fio.get("estado") not in ("aberto", "adiado"):
                return {"ok": False, "erro": "essa tarefa já não está em aberto", "quadro": q.montar(login)}
            if acao == "concluir":
                f.concluir(login, fid, f"{login}: concluiu no quadro de Tarefas")
                msg = "Concluída."
            elif acao == "reabrir":
                f.reabrir(login, fid)
                msg = "Reaberta."
            else:
                cid = _nova_conversa(login, f"Tarefa: {str(fio.get('titulo', ''))[:48]}", q.texto_fazer(fio))
                f.mesclar(login, [{"id": fid, "conversa": cid}])
                msg = "Comecei numa conversa só desta tarefa (está na lista de conversas); aviso no celular quando terminar."
        return {"ok": True, "mensagem": msg, "quadro": q.montar(login)}

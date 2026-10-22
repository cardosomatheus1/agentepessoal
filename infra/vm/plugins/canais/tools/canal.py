"""Tool `canal`: channels by subject (helpers/canais.py)."""

import importlib.util
import sys
from pathlib import Path

from helpers.tool import Response, Tool


def canais():
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "canais.py"
    antigo = sys.modules.get("canais_helper")
    if antigo is None or getattr(antigo, "_mtime", None) != caminho.stat().st_mtime:
        spec = importlib.util.spec_from_file_location("canais_helper", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = caminho.stat().st_mtime
        sys.modules["canais_helper"] = m
    return sys.modules["canais_helper"]


def _dono(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return (sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")) or "matheus"


def _nova_conversa(usuario: str, nome: str, canal: dict, texto: str) -> str:
    from agent import AgentContext, UserMessage
    from helpers import message_queue as mq
    from helpers import projects
    from initialize import initialize_agent

    ctx = AgentContext(config=initialize_agent(), name=nome)
    projects.reconcile_agent_profile(ctx, projects.get_context_project_name(ctx))
    for chave, valor in (("dono", usuario), ("usuario", usuario), (canais().CHAVE, canal)):
        ctx.set_data(chave, valor)
    mq.log_user_message(ctx, texto, [], None, source=" (canal)")
    ctx.communicate(UserMessage(message=texto, attachments=[], id=""))
    return ctx.id


class Canal(Tool):
    async def execute(self, acao: str = "listar", nome: str = "", proposito: str = "", **kwargs) -> Response:
        c, login, ctx = canais(), _dono(self.agent.context), self.agent.context
        acao = str(acao or "listar").lower()
        if acao in ("criar", "transformar"):
            r = c.novo(login, nome, proposito)
            if not r["ok"]:
                return Response(message=f"Não criei: {r['erro']}", break_loop=False)
            canal = r["canal"]
            dados = {"id": canal["id"], "nome": canal["nome"], "proposito": canal["proposito"]}
            if acao == "transformar":  # this very chat becomes the channel
                ctx.set_data(c.CHAVE, dados)
                ctx.name = f"# {canal['nome']}"
                c.atualizar(login, canal["id"], conversa=ctx.id)
                return Response(message=f"Esta conversa agora é o canal #{canal['nome']}. Sugira a ele 3 tarefas que você "
                                        "pode fazer aqui e pergunte qual ajuda mais.", break_loop=False)
            cid = _nova_conversa(login, f"# {canal['nome']}", dados, c.boas_vindas(canal))
            c.atualizar(login, canal["id"], conversa=cid)
            return Response(message=f"Canal #{canal['nome']} criado (está na lista de conversas, com 3 sugestões de "
                                    "tarefas). Diga isso a ele em uma linha.", break_loop=False)
        if acao == "proposito":
            atual = ctx.get_data(c.CHAVE)
            if not atual:
                return Response(message="Esta conversa não é um canal.", break_loop=False)
            canal = c.atualizar(login, atual["id"], proposito=proposito)
            if canal:
                ctx.set_data(c.CHAVE, {"id": canal["id"], "nome": canal["nome"], "proposito": canal["proposito"]})
            return Response(message="Propósito atualizado." if canal else "Canal não encontrado.", break_loop=False)
        lista = c.listar(login)
        if not lista:
            return Response(message="Nenhum canal ainda.", break_loop=False)
        return Response(message="\n".join(f"- #{x['nome']}: {x['proposito'][:120]}" for x in lista), break_loop=False)

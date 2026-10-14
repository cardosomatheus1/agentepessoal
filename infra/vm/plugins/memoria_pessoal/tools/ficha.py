"""Tool `ficha`: add, patch and remove entries of the speaker's profile (helpers/ficha.py), with a ceiling, no
duplicates and the protection filter. Only in a conversation with the person: a scheduled round or a trigger reads
DMs, e-mails and pages, which never become facts about the person."""

import importlib.util
import sys
from pathlib import Path

from helpers.tool import Response, Tool

DONO = "matheus"
RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def _helper(nome: str, arquivo: str):
    caminho = RAIZ / "helpers" / arquivo
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def quem(context) -> str:
    """The person speaking (same rule as the `decisao` tool and the memory block)."""
    falante = (context.get_data("usuario") or "").strip().lower()
    if falante:
        return falante
    sep = sys.modules.get("login_usuarios_separacao")
    return ((sep.dono_contexto(context) if sep else context.get_data("dono")) or DONO).strip().lower()


def fora_de_conversa(context, rotina) -> str:
    """Why this chat may not change the ficha ("" when it may)."""
    if context.get_data("gatilhos_de"):
        return "esta conversa é a de gatilhos (avisos automáticos de fora)"
    if rotina(context):
        return "esta conversa é uma rotina agendada (lê DMs, e-mails e páginas de terceiros)"
    return ""


def executar(f, login: str, acao: str, texto: str = "", trecho: str = "", novo: str = "", origem: str = "",
             bloqueio: str = "") -> str:
    acao = str(acao or "listar").strip().lower()
    escrita = acao in ("add", "adicionar", "anotar", "patch", "trocar", "corrigir", "editar", "remove", "remover",
                       "apagar", "tirar")
    if escrita and bloqueio:
        return (f"Não mexi na ficha: {bloqueio}. A ficha só muda numa conversa com a pessoa, com o que ela mesma contou; "
                "se isto é importante, conte na resposta e deixe que ela confirme.")
    try:
        if acao in ("add", "adicionar", "anotar"):
            return f.adicionar(login, texto, por="agente", origem=origem)["mensagem"]
        if acao in ("patch", "trocar", "corrigir", "editar"):
            return f.trocar(login, trecho, novo or texto, por="agente", origem=origem)["mensagem"]
        if acao in ("remove", "remover", "apagar", "tirar"):
            return f.remover(login, trecho or texto, por="agente", origem=origem)["mensagem"]
        lista = f.entradas(login)
    except f.FormatoAntigo:
        return ("A ficha ainda está no formato antigo (texto livre) e o operador ainda não a migrou: por enquanto ela "
                "fica como está. Não edite o arquivo; conte o fato na resposta.")
    except f.EstadoIlegivel as exc:
        return f"Não mexi na ficha: {exc}"
    if not lista:
        return "A ficha está vazia."
    return f"Ficha ({f.uso(lista)}/{f.TETO} caracteres):\n" + f.numeradas(lista)


def _rotina(context) -> bool:
    ponte = sys.modules.get("whatsapp_ponte")
    if ponte is not None:
        try:
            return bool(ponte.tarefa(context))
        except Exception:
            pass
    return _helper("memoria_pessoal_conversas", "conversas.py").e_rotina(context.id)


class Ficha(Tool):
    async def execute(self, acao: str = "listar", texto: str = "", trecho: str = "", novo: str = "", **kwargs) -> Response:
        ctx = self.agent.context
        msg = executar(_helper("memoria_pessoal_ficha", "ficha.py"), quem(ctx), acao, texto=str(texto or ""),
                       trecho=str(trecho or kwargs.get("old_text") or ""), novo=str(novo or kwargs.get("new_text") or ""),
                       origem=f"conversa {ctx.id}", bloqueio=fora_de_conversa(ctx, _rotina))
        return Response(message=msg, break_loop=False)

"""Tool `decisao`: record, list and revoke the person's decisions (helpers/decisoes.py), so a settled question is
never asked again."""

import importlib.util
import sys
import time
from pathlib import Path

from helpers.tool import Response, Tool

DONO = "matheus"


def _decisoes():
    nome = "memoria_pessoal_decisoes"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "decisoes.py"
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
    """The person speaking (same rule as the memory block of every turn)."""
    falante = (context.get_data("usuario") or "").strip().lower()
    if falante:
        return falante
    sep = sys.modules.get("login_usuarios_separacao")
    return ((sep.dono_contexto(context) if sep else context.get_data("dono")) or DONO).strip().lower()


def executar(d, login: str, acao: str, tema: str = "", decisao: str = "", tipo: str = "decisao", citacao: str = "",
             id: str = "", busca: str = "", motivo: str = "", origem: str = "", por: str = "agente") -> str:
    acao = str(acao or "listar").strip().lower()
    if acao in ("registrar", "anotar", "salvar", "mudar"):
        try:
            r = d.registrar(login, tema, decisao, tipo=tipo, citacao=citacao, origem=origem, por=por)
        except d.DecisaoInvalida as exc:
            return f"Não registrei: {exc}."
        if r["efeito"] == "igual":
            return f"Já estava registrado assim (#{r['id']} {r['tema']}): nada mudou. Não precisa avisar."
        troca = (f" Substituiu a anterior (#{r['anterior']['id']}): \"{r['anterior']['valor']}\"."
                 if r["efeito"] == "substituiu" else "")
        sem_citacao = ("" if r.get("citacao") else
                       " (Sem as palavras da pessoa em `citacao`: se a decisão veio de uma mensagem, registre de novo com ela.)")
        return (f"Registrado #{r['id']} {r['tema']}: {r['valor']}.{troca}{sem_citacao} "
                f"Termine sua resposta com \"Anotado: {r['valor']}\".")
    if acao in ("revogar", "desfazer", "cancelar"):
        x = d.revogar(login, id or tema, motivo=motivo, por=por)
        if not x:
            return f"Nenhuma decisão em vigor com {'#' + str(id) if id else 'tema ' + repr(tema)}. Use acao \"listar\"."
        return f"Revogada #{x['id']} {x['tema']} (\"{x['valor']}\"). Termine sua resposta com \"Anotado: deixa de valer {x['valor']}\"."
    if acao in ("historico", "histórico"):
        versoes = d.historico(login, tema)
        if not versoes:
            return f"Nada registrado sobre {tema!r}."
        fim = lambda x: f" em {time.strftime('%d/%m', time.localtime(x['fim_em']))}" if x.get("fim_em") else ""  # noqa: E731
        return "\n".join(f"{d.linha(x)} [{x['estado']}{fim(x)}]" for x in versoes)
    achadas = d.buscar(login, busca or tema)
    if not achadas:
        return "Nenhuma decisão em vigor" + (f" sobre {busca or tema!r}" if busca or tema else "") + "."
    return "\n".join(d.linha(x) + (f" — palavras: \"{x['citacao']}\"" if x.get("citacao") else "") for x in achadas)


class Decisao(Tool):
    async def execute(self, acao: str = "listar", tema: str = "", decisao: str = "", tipo: str = "decisao",
                      citacao: str = "", id: str = "", busca: str = "", motivo: str = "", **kwargs) -> Response:
        origem = f"conversa {self.agent.context.id}"
        msg = executar(_decisoes(), quem(self.agent.context), acao, tema=tema, decisao=decisao, tipo=tipo,
                       citacao=citacao, id=str(id or ""), busca=busca, motivo=motivo, origem=origem, por="agente")
        return Response(message=msg, break_loop=False)

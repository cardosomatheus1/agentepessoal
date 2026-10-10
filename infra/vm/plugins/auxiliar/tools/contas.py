"""Tool `contas`: bills and due dates found in e-mail; reminders go out on their own (3 days, 1 day, the day)."""

import importlib.util
import sys
from pathlib import Path

from helpers.tool import Response, Tool


def aux():
    nome = "auxiliar_helper"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "auxiliar.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def dono(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return (sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")) or "matheus"


class Contas(Tool):
    async def execute(self, acao: str = "listar", descricao: str = "", vencimento: str = "", valor: str = "",
                      moeda: str = "BRL", fonte: str = "", id: str = "", **kwargs) -> Response:
        a = aux()
        login = dono(self.agent.context)
        acao = str(acao or "listar").lower()
        if acao == "salvar":
            conta, erro = a.salvar_conta(login, descricao, vencimento, valor, moeda, fonte, id)
            if erro:
                return Response(message=erro, break_loop=False)
            return Response(message=f"Conta [{conta['id']}] registrada: {a.linha_conta(conta)}. O lembrete sai sozinho "
                                    "3 dias antes, na véspera e no dia.", break_loop=False)
        if acao in ("paga", "ignorar"):
            ok = a.fechar_conta(login, id, "paga" if acao == "paga" else "ignorada")
            return Response(message="Feito." if ok else "Conta não encontrada (ou já fechada).", break_loop=False)
        if acao == "listar":
            itens = a.contas_abertas(login, 60)
            return Response(message="\n".join(f"- [{c['id']}] {a.linha_conta(c)}" for c in itens) or "(nenhuma conta aberta)",
                            break_loop=False)
        return Response(message="acao: salvar | listar | paga | ignorar", break_loop=False)

"""Tool `reuniao`: schedule a briefing 30 min before a meeting and a "how did it go?" right after it."""

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


class Reuniao(Tool):
    async def execute(self, acao: str = "agendar", evento_id: str = "", titulo: str = "", inicio: str = "", fim: str = "",
                      participantes: str = "", local: str = "", **kwargs) -> Response:
        a = aux()
        login = dono(self.agent.context)
        acao = str(acao or "agendar").lower()
        if acao == "agendar":
            return Response(message=await a.agendar_reuniao(login, evento_id, titulo, inicio, fim, participantes, local),
                            break_loop=False)
        if acao == "pos_registrado":
            ok = a.registrar_pos(login, evento_id)
            return Response(message="Pós-reunião registrado." if ok else "Reunião não encontrada.", break_loop=False)
        if acao == "listar":
            agora = a.agora().timestamp()
            itens = [r for r in a.carregar(login)["reunioes"] if r["fim_ts"] > agora - 86400]
            return Response(message="\n".join(f"- [{r['evento_id']}] {r['inicio_txt']} {r['titulo']}" for r in itens)
                            or "(nenhuma)", break_loop=False)
        return Response(message="acao: agendar | listar | pos_registrado", break_loop=False)

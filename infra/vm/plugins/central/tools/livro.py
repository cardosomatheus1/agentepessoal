"""Tool `livro`: what the agent did (from the action ledger), so "o que você fez hoje?" is answered from records, not
from memory."""

import datetime as dt
import importlib.util
import sys
import time
from pathlib import Path

from helpers.tool import Response, Tool

DONO = "matheus"
FUSO = "America/Bahia"


def _livro():
    nome = "central_livro"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "livro.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def inicio_do_dia(dias_atras: int = 0, agora: float | None = None) -> float:
    from zoneinfo import ZoneInfo

    hoje = dt.datetime.fromtimestamp(agora or time.time(), ZoneInfo(FUSO)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (hoje - dt.timedelta(days=dias_atras)).timestamp()


def executar(livro, login: str, acao: str = "hoje", dias: int = 0) -> str:
    acao = str(acao or "hoje").lower()
    if acao == "conferir":
        achados = livro.conferir(login)
        return "\n".join(a["texto"] for a in achados) or "Conferência: nada fora do normal no livro (últimas 24 h)."
    dias = max(0, min(int(dias or 0), 30))
    desde = inicio_do_dia(dias)
    titulo = "Hoje" if not dias else f"Desde {time.strftime('%d/%m', time.localtime(desde))}"
    return f"{titulo}, pelo livro de ações:\n" + livro.resumo(login, desde)


class Livro(Tool):
    async def execute(self, acao: str = "hoje", dias: int = 0, **kwargs) -> Response:
        ctx = self.agent.context
        login = (ctx.get_data("usuario") or ctx.get_data("dono") or DONO).strip().lower()
        return Response(message=executar(_livro(), login, acao, dias), break_loop=False)

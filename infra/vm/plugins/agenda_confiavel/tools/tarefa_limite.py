"""End date and history of scheduled tasks (like Dots' Scheduled tab)."""

import importlib.util
import sys
import time
from datetime import datetime
from pathlib import Path

from helpers.tool import Response, Tool


def limites():
    nome = "agenda_limites"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers_limites.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


class TarefaLimite(Tool):
    async def execute(self, uuid: str = "", acao: str = "ver", termina_em: str = "", **kwargs) -> Response:
        L = limites()
        try:
            dados = L.carregar()
        except L.LimitesIlegiveis as exc:
            return Response(message=f"Não consegui ler os limites das tarefas ({exc}); nada foi mudado.", break_loop=False)
        uuid = str(uuid or "").strip()
        if not uuid:
            return Response(message="Informe `uuid` da tarefa (scheduler list_tasks mostra).", break_loop=False)
        acao = str(acao or "ver").lower()
        if acao == "permanente":
            L.definir(uuid, {"ate": None, "permanente": True})
            return Response(message=f"Tarefa {uuid} sem data de fim.", break_loop=False)
        if acao in ("terminar_em", "fim", "ate"):
            texto = str(termina_em or "").strip().lower()
            try:
                if texto.endswith(("d", "dias", "dia")):
                    ate = time.time() + float(texto.split("d")[0].strip()) * 86400
                else:
                    ate = datetime.fromisoformat(texto).timestamp()
            except Exception:
                return Response(message="`termina_em`: '7d' ou uma data '2026-10-31'.", break_loop=False)
            L.definir(uuid, {"ate": ate, "permanente": False})
            return Response(message=f"Tarefa {uuid} termina em {datetime.fromtimestamp(ate):%d/%m %H:%M} (é desativada sozinha).",
                            break_loop=False)
        reg = dados.get(uuid, {})
        fim = "sem fim" if reg.get("permanente") or uuid in L.EXISTENTES else (
            f"até {datetime.fromtimestamp(reg['ate']):%d/%m %H:%M}" if reg.get("ate") else "30 dias após criar (padrão)")
        hist = L.historico(uuid)
        linhas = [f"Tarefa {uuid}: {fim}. Últimas {len(hist)} rodadas:"] + [
            f"- {h['quando'][:16]}: {h['resultado'][:160]}" for h in hist[-10:]]
        return Response(message="\n".join(linhas), break_loop=False)

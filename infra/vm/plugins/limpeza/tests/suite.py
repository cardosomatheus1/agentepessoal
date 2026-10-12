"""Tests of the cleanup rules (no model calls). Run with implantar.py (staging copy) or inside the container."""
import datetime as dt
import importlib.util
import sys
import time
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class Falha(Exception):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _carregar(nome: str, arquivo: Path):
    try:
        import helpers.extension  # noqa: F401  (inside the container)
    except Exception:
        sys.modules.setdefault("helpers", types.ModuleType("helpers"))
        ext = types.ModuleType("helpers.extension")
        ext.Extension = type("Extension", (), {})
        sys.modules["helpers.extension"] = ext
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Vivo:
    def __init__(self, vivo=True, erro=False):
        self.vivo, self.erro = vivo, erro

    def is_alive(self):
        if self.erro:
            raise RuntimeError("estado desconhecido")
        return self.vivo


class Suite:
    def __init__(self):
        self.dr = _carregar("limpeza_destravar_teste", RAIZ / "extensions" / "python" / "job_loop" / "_41_destravar_rotinas.py")
        self.resultados = []

    def _tarefa(self, uuid, estado, atualizada_min, ultima_min=None, agendada=True):
        agora = dt.datetime.now(dt.timezone.utc)
        return types.SimpleNamespace(
            uuid=uuid, name=uuid, state=estado, context_id=uuid, schedule={"minute": "23"} if agendada else None,
            updated_at=agora - dt.timedelta(minutes=atualizada_min),
            last_run=None if ultima_min is None else agora - dt.timedelta(minutes=ultima_min))

    def _soltas(self, tarefas, rodando=None, do_chat=None):
        return [s["tarefa"] for s in self.dr.destravar(tarefas, rodando or {}, lambda cid: (do_chat or {}).get(cid),
                                                        time.time(), "running", "error")]

    def t_rodada_rodando_nao_e_destravada(self):
        # 12/10: the search started at 9h23 (previous run the day before) and was put back to idle at 9h29, 9h32 and
        # 9h42; each time the scheduler started another copy in the same chat
        buscar = self._tarefa("buscar", "running", atualizada_min=8, ultima_min=1444)
        ok(self._soltas([buscar]) == [], "rodada que começou há 8 min não é destravada, mesmo com a anterior há 24 h")
        longa = self._tarefa("longa", "running", atualizada_min=180, ultima_min=1444)
        ok(self._soltas([longa], rodando={"longa": Vivo()}) == [],
           "rodada que o agendador ainda segura (DeferredTask vivo) nunca é destravada, por mais longa que seja")
        ok(self._soltas([longa], do_chat={"longa": Vivo()}) == [], "rodada viva no chat também não")
        ok(self._soltas([longa], rodando={"longa": Vivo(erro=True)}) == [], "na dúvida (is_alive falhou), deixa quieta")

    def t_rodada_presa_depois_de_reiniciar_volta(self):
        presa = self._tarefa("presa", "running", atualizada_min=120, ultima_min=900)
        ok(self._soltas([presa]) == ["presa"], "marcada como rodando há 2 h sem nada rodando (reinício) volta a ociosa")
        ok(self._soltas([presa], rodando={"presa": Vivo(vivo=False)}) == ["presa"], "DeferredTask morto não segura")
        sem_data = types.SimpleNamespace(uuid="x", name="x", state="running", context_id="", schedule=None,
                                         updated_at=None, last_run=None)
        ok(self._soltas([sem_data]) == ["x"], "sem data nenhuma conta como presa")

    def t_erro_volta_a_rodar_no_proximo_horario(self):
        erro = self._tarefa("erro", "error", atualizada_min=10, ultima_min=10)
        recente = self._tarefa("recente", "error", atualizada_min=2, ultima_min=2)
        avulsa = self._tarefa("avulsa", "error", atualizada_min=60, ultima_min=60, agendada=False)
        ociosa = self._tarefa("ociosa", "idle", atualizada_min=600, ultima_min=600)
        ok(self._soltas([erro, recente, avulsa, ociosa]) == ["erro"],
           "só a recorrente em erro há mais de 5 min volta; tarefa avulsa e ociosa ficam como estão")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados), "resultados": self.resultados}

"""Tests of the cleanup rules (no model calls). Run with implantar.py (staging copy) or inside the container."""
import datetime as dt
import importlib.util
import os
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


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


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

    def t_arquivar_so_conversas_paradas_e_soltas(self):
        a = _carregar("limpeza_arquivar_teste", RAIZ / "helpers" / "arquivar.py")
        agora = 1_800_000_000
        velho, novo = agora - 8 * 86400, agora - 2 * 86400
        itens = [{"id": "parada", "mtime": velho, "data": {}},
                 {"id": "recente", "mtime": novo, "data": {}},
                 {"id": "celular", "mtime": velho, "data": {"whatsapp_de": "matheus"}},
                 {"id": "gatilhos", "mtime": velho, "data": {"gatilhos_de": "matheus"}},
                 {"id": "rodada", "mtime": velho, "data": {}, "tem_tarefa": True},
                 {"id": "rodando", "mtime": velho, "data": {}, "rodando": True}]
        ok(a.escolher(itens, agora) == ["parada"], f"só a parada há 7+ dias e solta: {a.escolher(itens, agora)}")
        ext = (RAIZ / "extensions" / "python" / "job_loop" / "_42_arquivar_conversas.py").read_text(encoding="utf-8")
        ok(ext.index("copytree") < ext.index("AgentContext.remove"), "copia antes de tirar do agente")

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

    def t_depois_de_reiniciar_volta_na_hora(self):
        # 12/10: copies of a round frozen in a paused chat were killed by restarting the agent; the round stays
        # "running" with nothing running it: it must not wait 90 min (it would miss its next time)
        agora = time.time()
        antes = self._tarefa("antes", "running", atualizada_min=20)
        depois = self._tarefa("depois", "running", atualizada_min=2)
        soltas = [s["tarefa"] for s in self.dr.destravar([antes, depois], {}, lambda cid: None, agora, "running", "error",
                                                         None, {}, agora - 5 * 60)]
        ok(soltas == ["antes"], f"marcada como rodando antes do reinício volta já; a que começou depois, não: {soltas}")

    def t_erro_volta_a_rodar_no_proximo_horario(self):
        erro = self._tarefa("erro", "error", atualizada_min=10, ultima_min=10)
        recente = self._tarefa("recente", "error", atualizada_min=2, ultima_min=2)
        avulsa = self._tarefa("avulsa", "error", atualizada_min=60, ultima_min=60, agendada=False)
        ociosa = self._tarefa("ociosa", "idle", atualizada_min=600, ultima_min=600)
        ok(self._soltas([erro, recente, avulsa, ociosa]) == ["erro"],
           "só a recorrente em erro há mais de 5 min volta; tarefa avulsa e ociosa ficam como estão")

    def t_erro_de_conexao_roda_de_novo_na_hora(self):
        # 12/10 review: a round lost because the proxy was not up yet waited for its next time (hours)
        def com_erro(uuid, texto, minutos):
            t = self._tarefa(uuid, "error", atualizada_min=minutos, ultima_min=minutos)
            t.last_result = texto
            return t

        conexao = com_erro("conexao", "ERROR: litellm.APIConnectionError: Connection error.", 12)
        outro = com_erro("outro", "ERROR: KeyError: 'acao'", 12)
        velha = com_erro("velha", "ERROR: Connection refused", 200)
        repetidas = {}
        agir = lambda: {s["tarefa"]: s.get("acao") for s in self.dr.destravar(  # noqa: E731
            [conexao, outro, velha], {}, lambda cid: None, time.time(), "running", "error", None, {}, 0.0, repetidas)}
        eq(agir(), {"conexao": "repetir", "outro": None, "velha": None},
           "queda de conexão recente roda de novo já; outro erro e falha antiga só voltam a ociosa")
        eq(agir(), {"conexao": None, "outro": None, "velha": None}, "a mesma falha não é repetida duas vezes")

    def t_rodada_pausada_e_retomada_ou_cancelada(self):
        # 12/10: the loop detector paused the search round's chat; nobody resumes a scheduled round, so it stayed stuck
        dr, agora = self.dr, time.time()
        buscar = self._tarefa("buscar", "running", atualizada_min=30)
        viva = {"buscar": Vivo()}
        pausas = {}
        def rodar(minutos):
            return self.dr.destravar([buscar], viva, lambda cid: None, agora + minutos * 60, "running", "error",
                                     lambda cid: True, pausas)
        eq = lambda a, b, m: ok(a == b, f"{m}: {a!r}")  # noqa: E731
        eq(rodar(0), [], "acabou de pausar: espera")
        eq(rodar(5), [], "5 min pausada: ainda espera (alguém pode estar olhando)")
        r = rodar(11)
        eq([x["acao"] for x in r], ["retomar"], "pausada há mais de 10 min: retoma uma vez (a execução viva não impede)")
        eq(rodar(12), [], "depois de retomar, conta de novo")
        r = rodar(23)
        eq([x["acao"] for x in r], ["cancelar"], "pausou de novo em menos de 2 h: cancela a execução (volta no próximo horário)")
        ok(dr.destravar([buscar], viva, lambda cid: None, agora + 30 * 60, "running", "error", lambda cid: False, pausas) == [],
           "sem pausa, execução viva: nada a fazer")
        ociosa = self._tarefa("buscar", "idle", atualizada_min=1)
        pausas2 = {"buscar": {"desde": agora - 3600}}
        dr.destravar([ociosa], {}, lambda cid: None, agora, "running", "error", lambda cid: True, pausas2)
        ok("desde" not in pausas2.get("buscar", {}), "a pausa é da execução: a próxima começa a contar do zero")
        pausas3 = {"velha": {"retomada": agora - 3 * 3600}}
        dr.destravar([], {}, lambda cid: None, agora, "running", "error", lambda cid: True, pausas3)
        ok(pausas3 == {}, "registro velho some")

    def t_intervalo_vale_mesmo_recarregando_o_modulo(self):
        # 12/10 review: job-loop extensions are loaded again on every pass, so the "every 10 minutes" kept in a module
        # variable ran every minute; the time now lives in a marker file
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="limpeza-marca-"))
        try:
            for arquivo in ("_40_limpar_navegador.py", "_41_destravar_rotinas.py"):
                caminho = RAIZ / "extensions" / "python" / "job_loop" / arquivo
                m1 = _carregar("limpeza_marca_1", caminho)
                marca = tmp / arquivo
                ok(m1._na_hora(marca, m1.INTERVALO), f"{arquivo}: a primeira volta roda")
                m2 = _carregar("limpeza_marca_2", caminho)  # the next pass: a fresh module
                ok(not m2._na_hora(marca, m2.INTERVALO), f"{arquivo}: a volta seguinte, com o módulo recarregado, não roda")
                antes = time.time() - m2.INTERVALO - 1
                os.utime(marca, (antes, antes))
                ok(m2._na_hora(marca, m2.INTERVALO), f"{arquivo}: passado o intervalo, roda de novo")
                ok(not hasattr(m2, "_ultima"), f"{arquivo}: nada de relógio em variável do módulo")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados), "resultados": self.resultados}

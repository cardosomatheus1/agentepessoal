"""Tests of the round catch-up (no model calls). Run with implantar.py (staging copy) or inside the container."""
import importlib.util
import sys
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
        self.rr = _carregar("agenda_recuperar_teste", RAIZ / "extensions" / "python" / "job_loop" / "_50_recuperar_rodadas.py")
        self.resultados = []

    def t_nao_inicia_copia_de_rodada_viva(self):
        # 12/10: the cleanup put the running search back to idle and this catch-up started 3 copies in the same chat
        ag = types.SimpleNamespace(_running_deferred_tasks={"buscar": Vivo(), "morta": Vivo(vivo=False), "duvida": Vivo(erro=True)})
        ok(self.rr.rodando(ag, "buscar"), "rodada que o agendador segura viva não é recuperada de novo")
        ok(self.rr.rodando(ag, "duvida"), "na dúvida, não inicia cópia")
        ok(not self.rr.rodando(ag, "morta"), "execução morta não segura a recuperação")
        ok(not self.rr.rodando(ag, "outra"), "rodada sem execução pode ser recuperada")
        ok(not self.rr.rodando(types.SimpleNamespace(), "x"), "agendador sem o registro (versão antiga) não quebra")

    def _limites(self):
        import tempfile

        L = _carregar("agenda_limites_teste", RAIZ / "helpers_limites.py")
        pasta = Path(tempfile.mkdtemp(prefix="agenda-teste-"))
        self._tmp.append(pasta)
        L.PASTA, L.LIMITES, L.HISTORICO = pasta, pasta / "limites.json", pasta / "historico"
        return L

    def t_limites_ilegiveis_nunca_desligam_rotina(self):
        # 12/10 review: an unreadable limites.json was read as "no limits" and every routine marked permanent
        # would be switched off at 30 days
        import datetime as dt
        import time

        L = self._limites()
        velha = types.SimpleNamespace(uuid="F9Ku9frw", state="idle",
                                      created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=40))
        L.definir("F9Ku9frw", {"ate": None, "permanente": True})
        eq = lambda a, b, m: ok(a == b, f"{m}: {a!r}")  # noqa: E731
        eq(L.a_desligar([velha], L.carregar(), time.time(), "disabled", "running"), [], "permanente não desliga")
        L.LIMITES.write_text('{"F9Ku9frw": {"ate": nu', encoding="utf-8")
        try:
            L.carregar()
            raise Falha("arquivo ilegível devia dar erro, não 'sem limites'")
        except L.LimitesIlegiveis:
            pass
        eq(L.a_desligar([velha], None, time.time(), "disabled", "running"), [], "limites desconhecidos: nada é desligado")
        eq(L.a_desligar([velha], {}, time.time(), "disabled", "running"), [velha],
           "sem registro (arquivo lido e vazio), a de 40 dias vence como antes")
        try:
            L.definir("outra", {"ate": None, "permanente": True})
            raise Falha("mudar um limite por cima de um arquivo ilegível devia dar erro")
        except L.LimitesIlegiveis:
            pass
        ok(L.LIMITES.read_text(encoding="utf-8") == '{"F9Ku9frw": {"ate": nu', "o arquivo ilegível ficou como estava")

    def t_historico_sobrevive_a_linha_cortada(self):
        L = self._limites()
        L.HISTORICO.mkdir(parents=True)
        (L.HISTORICO / "x.jsonl").write_text('{"quando": "a", "resultado": "ok"}\n{"quando": "b", "resul', encoding="utf-8")
        L.registrar_rodada("x", "c", "feito")
        ok([h["quando"] for h in L.historico("x")] == ["a", "c"], f"linha cortada é pulada: {L.historico('x')}")
        for i in range(30):
            L.registrar_rodada("x", f"r{i}", "ok")
        ok(len(L.historico("x")) == 20, "guarda só as últimas 20")
        ok(not list(L.HISTORICO.glob(".*.tmp")), "nenhum temporário largado")

    async def rodar(self, so=""):
        import shutil

        self._tmp = []
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        for pasta in self._tmp:
            shutil.rmtree(pasta, ignore_errors=True)
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados), "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])

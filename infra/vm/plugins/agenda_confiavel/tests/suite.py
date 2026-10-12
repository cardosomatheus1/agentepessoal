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

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados), "resultados": self.resultados}

"""Tests of the radar monitors' safe writes (temporary folder only; never the live file).
Run with implantar.py (staging copy) or inside the container."""

import importlib.util
import shutil
import sys
import tempfile
import threading
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LOGIN = "teste_radar"


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def _carregar_ferramenta():
    """The tool imports helpers.tool (heavy: Agent Zero); a stand-in only while it loads."""
    tool = types.ModuleType("helpers.tool")
    tool.Tool = type("Tool", (), {})
    tool.Response = type("Response", (), {"__init__": lambda self, **kw: self.__dict__.update(kw)})
    antes = {k: sys.modules.get(k) for k in ("helpers", "helpers.tool")}
    sys.modules.setdefault("helpers", types.ModuleType("helpers"))
    sys.modules["helpers.tool"] = tool
    try:
        spec = importlib.util.spec_from_file_location("radar_monitor_teste", RAIZ / "tools" / "monitor.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        for k, v in antes.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class Suite:
    def __init__(self):
        self.m = _carregar_ferramenta()
        self.resultados = []

    def _pasta_nova(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="radar-teste-"))
        self.m.PASTA = self._tmp

    def t_criar_listar_remover(self):
        m = self.m
        r = m.executar(LOGIN, "criar", "gmail", "e-mail da contabilidade com 'guia'", "me avisar")
        ok(r.startswith("Monitor ") and "criado" in r, r)
        mid = m.carregar(LOGIN)["monitores"][0]["id"]
        ok(mid in m.executar(LOGIN, "listar"), "aparece na lista")
        eq(m.executar(LOGIN, "remover", id=mid), "Removido.", "removido")
        eq(m.executar(LOGIN, "listar"), "Nenhum monitor ativo.", "lista vazia")
        ok(not list(m.PASTA.glob(".*.tmp")), "nenhum temporário largado")

    def t_marcar_avisados(self):
        m = self.m
        mid = m.executar(LOGIN, "criar", "gmail", "fatura", "me avisar").split()[1]
        ok("2 id(s) marcado" in m.executar(LOGIN, "marcar", id="msg1, msg2"), "marca os ids tratados")
        ok("1 id(s) marcado(s) como avisados (1 já" in m.executar(LOGIN, "marcar", id="msg2 msg3"), "não duplica")
        av = m.executar(LOGIN, "avisados")
        ok(all(x in av for x in ("msg1", "msg2", "msg3")), f"lista os avisados: {av}")
        ok(mid in m.executar(LOGIN, "listar"), "os monitores ficam como estavam")
        ok("Diga em `id`" in m.executar(LOGIN, "marcar"), "sem ids, pede")

    def t_arquivo_ilegivel_nao_apaga_monitores(self):
        m = self.m
        m.executar(LOGIN, "criar", "gmail", "boleto da escola", "me avisar")
        arq = m._arquivo(LOGIN)
        arq.write_text('{"monitores": [{"id": "ab', encoding="utf-8")
        try:
            m.executar(LOGIN, "criar", "gmail", "outro", "me avisar")
            raise Falha("criar por cima de um arquivo ilegível devia dar erro")
        except m.EstadoIlegivel:
            pass
        eq(arq.read_text(encoding="utf-8"), '{"monitores": [{"id": "ab', "o arquivo não foi sobrescrito")

    def t_gravacoes_simultaneas(self):
        m = self.m
        erros = []

        def criar(p):
            try:
                for i in range(10):
                    m.executar(LOGIN, "criar", "gmail", f"condição {p} {i}", "me avisar")
            except Exception as exc:  # pragma: no cover
                erros.append(repr(exc))

        fios = [threading.Thread(target=criar, args=(p,)) for p in ("a", "b", "c")]
        [x.start() for x in fios]
        [x.join() for x in fios]
        eq(erros, [], "sem erro")
        eq(len(m.carregar(LOGIN)["monitores"]), 30, "os 30 monitores ficaram")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            self._pasta_nova()
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
            finally:
                shutil.rmtree(self._tmp, ignore_errors=True)
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])

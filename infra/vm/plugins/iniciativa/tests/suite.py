"""Tests of the initiative's safe writes (temporary folder only; no model calls, never the live file).
Run with implantar.py (staging copy) or inside the container."""

import importlib.util
import shutil
import sys
import tempfile
import threading
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LOGIN = "teste_ini"


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Suite:
    def __init__(self):
        self.i = _carregar("iniciativa_teste", RAIZ / "helpers" / "iniciativa.py")
        self.resultados = []

    def _pasta_nova(self):
        if getattr(self, "_tmp", None):
            shutil.rmtree(self._tmp, ignore_errors=True)
        self._tmp = Path(tempfile.mkdtemp(prefix="iniciativa-teste-"))
        self.i.PASTA = self._tmp

    def t_registrar_reagir_aprender_e_limite(self):
        i = self.i
        iid = i.registrar(LOGIN, "Planilha de custos pronta", "Montei a planilha…", "adiantei")
        eq(i.reagir(LOGIN, iid, "bora")["reacao"], "bora", "reação guardada")
        i.aprender(LOGIN, "Não mandar notícia de IA genérica")
        i.aprender(LOGIN, "Não mandar notícia de IA genérica")
        eq(i.carregar(LOGIN)["aprendizados"], ["Não mandar notícia de IA genérica"], "aprendizado sem repetir")
        pode, motivo = i.pode_enviar(LOGIN)
        ok(not pode and "100 min" in motivo, f"intervalo entre iniciativas respeitado: {motivo}")
        ok(not list(i.PASTA.glob(".*.tmp")), "nenhum temporário largado")

    def t_arquivo_ilegivel_nao_apaga_preferencias(self):
        i = self.i
        i.aprender(LOGIN, "Prefere receber de manhã")
        arq = i.arquivo(LOGIN)
        arq.write_text('{"enviadas": [], "aprendizados": ["Prefe', encoding="utf-8")
        try:
            i.aprender(LOGIN, "Outra preferência")
            raise Falha("gravar por cima de um arquivo ilegível devia dar erro")
        except i.EstadoIlegivel:
            pass
        eq(arq.read_text(encoding="utf-8"), '{"enviadas": [], "aprendizados": ["Prefe', "o arquivo não foi sobrescrito")

    def t_gravacoes_simultaneas_nao_se_apagam(self):
        i = self.i
        erros = []

        def gravar(prefixo):
            try:
                for n in range(12):
                    i.aprender(LOGIN, f"preferência {prefixo} {n}")
            except Exception as exc:  # pragma: no cover
                erros.append(repr(exc))

        fios = [threading.Thread(target=gravar, args=(p,)) for p in ("a", "b", "c")]
        [x.start() for x in fios]
        [x.join() for x in fios]
        eq(erros, [], "sem erro")
        eq(len(i.carregar(LOGIN)["aprendizados"]), 36, "os 36 aprendizados ficaram (nenhuma gravação apagou a outra)")

    async def rodar(self, so=""):
        try:
            for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
                self._pasta_nova()
                try:
                    getattr(self, nome)()
                    self.resultados.append({"teste": nome, "ok": True})
                except Exception as exc:
                    self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                            "onde": traceback.format_exc().splitlines()[-3:]})
        finally:
            shutil.rmtree(getattr(self, "_tmp", ""), ignore_errors=True)
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])

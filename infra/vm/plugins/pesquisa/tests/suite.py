"""Tests of the research plugin that need no network (the ledger record). Run with implantar.py (staging copy),
inside the container, or from the repository root: python3 infra/vm/plugins/pesquisa/tests/suite.py"""

import importlib.util
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


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
        self.resultados = []

    def t_pesquisa_no_livro(self):
        # 12/10 review §6: the research's result file is recorded in the ledger
        lp = _carregar("pesquisa_livro_teste", RAIZ / "helpers" / "livro_pesquisa.py")
        central = RAIZ.parent / "central" / "helpers" / "livro.py"
        if not central.exists():
            central = Path("/a0/usr/plugins/central/helpers/livro.py")
        livro = _carregar("central_livro_pesquisa_teste", central)
        tmp = Path(tempfile.mkdtemp(prefix="pesquisa-livro-"))
        try:
            livro.PASTA, livro.BANCO = tmp, tmp / "agente.db"
            arquivo = "/a0/usr/workdir/pesquisas/20261012-150000/sintese.md"
            ok(lp.registrar(livro, "pessoa_pesquisa", "Qual lava e seca 127 V\n compensa?", arquivo, 9, "ctx9"), "registrado")
            r = livro.do_periodo("pessoa_pesquisa", 0)[0]
            eq((r["verbo"], r["alvo"], r["fase"]), ("pesquisa", f"arquivo:{arquivo}", "executada"), "pesquisa com o arquivo")
            eq(r["conteudo_previa"], "Qual lava e seca 127 V compensa?", "a pergunta, numa linha")
            ok("9 fontes" in r["resultado"], "quantas fontes")
            eq(lp.registrar(None, "pessoa_pesquisa", "x", arquivo, 1), "", "sem livro: nada, sem erro")
            eq(lp.registrar(livro, "teste_pesquisa", "x", arquivo, 1), "", "login de teste não vai ao livro")
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
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])

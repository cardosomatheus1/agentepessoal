"""Tests of the action ledger and the Conferência rules (temporary database only; no model, no network).
Run with implantar.py (staging copy) or inside the container."""

import importlib.util
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LOGIN = "pessoa_teste"  # "teste_*" logins are never recorded


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def _carregar(nome: str, arquivo: Path, stubs: dict | None = None):
    antes = {k: sys.modules.get(k) for k in (stubs or {})}
    sys.modules.update(stubs or {})
    try:
        spec = importlib.util.spec_from_file_location(nome, arquivo)
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
        self.l = _carregar("central_livro_teste", RAIZ / "helpers" / "livro.py")
        self.resultados = []

    def _banco_novo(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="livro-teste-"))
        self.l.PASTA, self.l.BANCO = self._tmp, self._tmp / "agente.db"

    def _dm(self, alvo, texto, fase="executada", em=None, chave="prosp:x"):
        return self.l.registrar(fase, LOGIN, "prospeccao", "instagram", "dm", f"instagram:@{alvo}", texto, chave=chave, em=em)

    def t_so_acrescenta(self):
        l = self.l
        aid = self._dm("zen.marmitas", "Oi, pessoal da Zen!")
        ok(aid, "registrado")
        for sql in ("UPDATE acao SET fase = 'falhou'", "DELETE FROM acao"):
            try:
                with sqlite3.connect(l.BANCO) as con:
                    con.execute(sql)
                raise Falha(f"o livro devia recusar: {sql}")
            except sqlite3.DatabaseError as exc:
                ok("só acrescenta" in str(exc), f"recusa com o motivo: {exc}")
        eq(len(l.do_periodo(LOGIN, 0)), 1, "a linha continua lá")
        eq(l.registrar("executada", "teste_pro", "prospeccao", "instagram", "dm", "instagram:@x", "oi"), "",
           "login de teste não entra")
        eq(l.registrar("talvez", LOGIN, "prospeccao", "instagram", "dm", "instagram:@x", "oi"), "", "fase desconhecida não entra")

    def t_nunca_levanta_erro(self):
        l = self.l
        l.BANCO = self._tmp  # a folder, not a database file
        eq(self._dm("x", "oi"), "", "banco inutilizável: não registra e não quebra")
        eq(l.do_periodo(LOGIN, 0), [], "leitura também não quebra")
        eq(l.conferir(LOGIN), [], "conferência também não")

    def t_conferencia_acha_mensagem_repetida(self):
        l, agora = self.l, time.time()
        self._dm("zen.marmitas", "Oi, pessoal da Zen! Vi a marmita…", em=agora - 3600, chave="prosp:a1")
        self._dm("zen.marmitas", "Oi,  pessoal da Zen!  Vi a marmita…", em=agora - 600, chave="prosp:a2")
        self._dm("zen.marmitas", "Outro texto", em=agora - 500, chave="prosp:a3")
        self._dm("annasaude", "Oi, pessoal da Anna!", fase="falhou", em=agora - 400, chave="prosp:a4")
        self._dm("annasaude", "Oi, pessoal da Anna!", em=agora - 300, chave="prosp:a5")
        self._dm("velho", "Oi de novo", em=agora - 30 * 3600, chave="prosp:a6")
        self._dm("velho", "Oi de novo", em=agora - 200, chave="prosp:a7")
        achados = l.conferir(LOGIN, agora)
        eq(len(achados), 1, f"só a Zen (mesmo texto 2× em 24 h); falha seguida de envio e envio de ontem não contam: {achados}")
        ok("@zen.marmitas" in achados[0]["texto"] and "2 vezes" in achados[0]["texto"], achados[0]["texto"])
        ok(l.novo_alerta(achados[0]["chave"], LOGIN, achados[0]["texto"]), "primeira vez: avisa")
        ok(not l.novo_alerta(achados[0]["chave"], LOGIN, achados[0]["texto"]), "segunda vez: não avisa de novo")
        self._dm("zen.marmitas", "Oi, pessoal da Zen! Vi a marmita…", em=agora - 100, chave="prosp:a8")
        nova = l.conferir(LOGIN, agora)[0]["chave"]
        ok(nova != achados[0]["chave"] and l.novo_alerta(nova, LOGIN, "x"), "uma terceira vez é achado novo")

    def t_resumo_do_dia(self):
        l, agora = self.l, time.time()
        self._dm("zen.marmitas", "Oi, pessoal da Zen!", em=agora - 50)
        l.registrar("executada", LOGIN, "prospeccao", "instagram", "seguir_curtir", "instagram:@nati.doces_", em=agora - 40)
        l.registrar("falhou", LOGIN, "prospeccao", "instagram", "dm", "instagram:@annasaude", "Oi", resultado="script falhou",
                    em=agora - 30)
        r = l.resumo(LOGIN, agora - 3600)
        ok("mensagens no Direct feitos: 1" in r and "seguir e curtir feitos: 1" in r and "falhou: 1" in r, r)
        ok("@nati.doces_" in r and "script falhou" in r, r)
        eq(l.resumo(LOGIN, agora + 10), "Nada registrado no livro nesse período.", "período vazio")

    def t_ferramenta(self):
        stubs = {"helpers": types.ModuleType("helpers"), "helpers.tool": types.ModuleType("helpers.tool")}
        stubs["helpers.tool"].Tool = type("Tool", (), {})
        stubs["helpers.tool"].Response = type("Response", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
        f = _carregar("central_tool_teste", RAIZ / "tools" / "livro.py", stubs)
        self._dm("zen.marmitas", "Oi, pessoal da Zen!")
        ok(f.executar(self.l, LOGIN, "hoje").startswith("Hoje, pelo livro de ações:"), "hoje")
        ok("nada fora do normal" in f.executar(self.l, LOGIN, "conferir"), "conferir sem achado")
        ok(f.inicio_do_dia(1) < f.inicio_do_dia(0) <= time.time(), "início do dia no fuso da Bahia")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            self._banco_novo()
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

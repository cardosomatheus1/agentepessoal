"""Tests of channels (temporary folder only). Run with implantar.py or locally."""

import importlib.util
import os
import sys
import tempfile
import traceback
import types
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


def _carregar(nome, arquivo):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Suite:
    def __init__(self):
        self.resultados = []

    def _c(self):
        os.environ["CANAIS_PASTA"] = tempfile.mkdtemp(prefix="canais-teste-")
        return _carregar("canais_teste", RAIZ / "helpers" / "canais.py")

    def t_criar_listar_atualizar(self):
        c = self._c()
        ok(not c.novo("matheus", "R", "curto")["ok"], "nome e propósito de verdade")
        r = c.novo("matheus", "#Raiz", "Raiz Connect: sistema de gestão para food service, prospecção e posts")
        ok(r["ok"] and r["canal"]["nome"] == "Raiz", f"sem o # no nome: {r}")
        ok(not c.novo("matheus", "raiz", "outro propósito qualquer aqui")["ok"], "nome repetido")
        c.atualizar("matheus", r["canal"]["id"], conversa="ctx1", proposito="Raiz: novo foco em pizzaria e hamburgueria")
        eq([(x["nome"], x["conversa"]) for x in c.listar("matheus")], [("Raiz", "ctx1")], "lista com a conversa")
        ok("pizzaria" in c.listar("matheus")[0]["proposito"], "propósito novo")
        eq(c.listar("outra"), [], "cada pessoa os seus")
        eq(c.atualizar("matheus", "naoexiste", proposito="x" * 20), None, "canal inexistente")

    def t_instrucao_e_boas_vindas(self):
        c = self._c()
        canal = {"nome": "NEXOS", "proposito": "IA Business: stories, deploy e pilotos"}
        i = c.instrucao(canal)
        ok("#NEXOS" in i and "IA Business" in i and "mesma das outras conversas" in i, i)
        b = c.boas_vindas(canal)
        ok("3 tarefas" in b and "Não faça nenhuma delas ainda" in b, "sugere 3 tarefas e pergunta, sem fazer")

    async def t_extensao_poe_o_proposito_so_no_canal(self):
        stubs = {"agent": types.ModuleType("agent"), "helpers": types.ModuleType("helpers"),
                 "helpers.extension": types.ModuleType("helpers.extension")}
        stubs["agent"].LoopData = lambda: None

        class Extension:
            def __init__(self, agent=None, **k):
                self.agent = agent
        stubs["helpers.extension"].Extension = Extension
        antes = {n: sys.modules.get(n) for n in stubs}
        sys.modules.update(stubs)
        try:
            ext = _carregar("canal_ext_teste", RAIZ / "extensions" / "python" / "system_prompt" / "_29_canal.py")
            for dados, esperado in (({"canal": {"nome": "Raiz", "proposito": "Raiz Connect e a prospecção"}}, 1), ({}, 0)):
                ctx = types.SimpleNamespace(get_data=lambda k, d=dados: d.get(k))
                partes = []
                await ext.CanalPrompt(types.SimpleNamespace(number=0, context=ctx)).execute(system_prompt=partes)
                eq(len(partes), esperado, f"canal {bool(dados)}")
        finally:
            for n, m in antes.items():
                sys.modules.pop(n, None) if m is None else sys.modules.__setitem__(n, m)

    async def rodar(self, so: str = "") -> dict:
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                r = getattr(self, nome)()
                if hasattr(r, "__await__"):
                    await r
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc()[-600:]})
        passou = sum(1 for r in self.resultados if r["ok"])
        return {"passou": passou, "total": len(self.resultados), "resultados": self.resultados}

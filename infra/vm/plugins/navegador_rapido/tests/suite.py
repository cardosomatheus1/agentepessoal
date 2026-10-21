"""Tests of the browser fixes that run without Agent Zero. The page script runs in a real Chromium when Playwright is
installed (locally and on the VM); in CI, without it, that test only checks the script is well formed.
Run: python3 infra/vm/plugins/navegador_rapido/tests/suite.py"""

import asyncio
import importlib.util
import os
import sys
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


def _correcoes():
    spec = importlib.util.spec_from_file_location("navegador_rapido_correcoes_teste", RAIZ / "helpers" / "correcoes.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# 21/10, 99Food login: one password field per login tab, only the e-mail tab's is visible
PAGINA = """<form><input id=a type=password style="display:none"><input id=b type=password>
<input id=c type=text><button id=d style="visibility:hidden">Entrar</button><button id=e>Entrar</button></form>
<div class=x>um</div><div class=x>dois</div>"""


class _Pagina:
    def __init__(self, devolve=None, erro=None):
        self.devolve, self.erro, self.chamadas = devolve, erro, []

    async def evaluate(self, script, arg=None, isolated_context=False):
        self.chamadas.append(arg)
        if self.erro:
            raise self.erro
        return self.devolve


class Suite:
    def __init__(self):
        self.resultados = []

    async def t_alvo_visivel_na_pagina(self):
        c = _correcoes()
        ok(c.ALVO_VISIVEL.startswith("(sel) =>") and c.ALVO in c.ALVO_VISIVEL, "o script recebe o seletor")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return
        exe = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        if not Path(exe).exists():
            return
        async with async_playwright() as p:
            b = await p.chromium.launch(executable_path=exe, headless=True)
            pg = await b.new_page()
            await pg.set_content(PAGINA)
            novo = await pg.evaluate(c.ALVO_VISIVEL, "input[type=password]")
            eq(novo, '[data-a0-alvo="1"]', "o primeiro campo de senha está escondido: troca pelo visível")
            eq(await pg.evaluate(f"document.querySelector('{novo}').id"), "b", "marcou o campo que aparece")
            eq(await pg.evaluate(c.ALVO_VISIVEL, "button"), '[data-a0-alvo="1"]', "botão escondido antes do visível")
            eq(await pg.evaluate("document.querySelectorAll('[data-a0-alvo]').length"), 1, "só um marcado de cada vez")
            eq(await pg.evaluate("document.querySelector('[data-a0-alvo]').id"), "e", "o botão visível")
            eq(await pg.evaluate(c.ALVO_VISIVEL, "input[type=text]"), "", "um só: deixa como está")
            eq(await pg.evaluate(c.ALVO_VISIVEL, "#b, #c"), "", "o primeiro já é o visível: deixa como está")
            eq(await pg.evaluate(c.ALVO_VISIVEL, "div.x"), "", "seletor de leitura (não é campo) fica como está")
            eq(await pg.evaluate(c.ALVO_VISIVEL, "[[["), "", "seletor inválido não quebra")
            await b.close()

    async def t_content_usa_o_alvo_visivel(self):
        c = _correcoes()
        recebidos = []

        class Core:
            async def content(self, browser_id=None, payload=None):
                recebidos.append(payload)
                return {"ok": True}

            async def ensure_started(self):
                pass

            def _resolve_browser_id(self, bid):
                return bid

            def _page(self, bid):
                return self.pagina

        c._alvo_visivel(Core)
        ok(getattr(Core, c.MARK_ALVO), "marca que já aplicou")
        core = Core()
        core.pagina = _Pagina(devolve='[data-a0-alvo="1"]')
        eq(await core.content(1, {"selector": "input[type=password]"}), {"ok": True}, "devolve o original")
        eq(recebidos[-1], {"selector": '[data-a0-alvo="1"]'}, "lê o campo visível")
        eq(core.pagina.chamadas, ["input[type=password]"], "perguntou à página pelo seletor pedido")
        core.pagina = _Pagina(devolve="")
        await core.content(1, {"selector": "main"})
        eq(recebidos[-1], {"selector": "main"}, "sem troca, segue o seletor pedido")
        await core.content(1, None)
        eq(recebidos[-1], None, "sem seletor não pergunta nada")
        eq(core.pagina.chamadas, ["main"], "nenhuma pergunta extra sem seletor")
        core.pagina = _Pagina(erro=RuntimeError("página fechou"))
        await core.content(1, {"selector": "input"})
        eq(recebidos[-1], {"selector": "input"}, "erro na conferência não bloqueia a leitura")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                r = getattr(self, nome)()
                if hasattr(r, "__await__"):
                    await r
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])

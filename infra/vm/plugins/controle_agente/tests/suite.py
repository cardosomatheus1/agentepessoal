"""Tests of controle_agente that need no running agent. Run with implantar.py (staging copy) or from the repository
root: python3 infra/vm/plugins/controle_agente/tests/suite.py"""

import importlib.util
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Suite:
    def __init__(self):
        self.resultados = []

    def t_clique_em_referencia_que_sumiu(self):
        c = _carregar("controle_clique_teste", RAIZ / "helpers" / "clique.py")
        erro = ('Browser click failed: Page.evaluate: BrowserPageContentReferenceError: Browser page content could not find '
                'reference "button 21".')
        ok(c.dica("browser", erro), "o clique que falhou ganha a saída")
        ok(c.dica("browser", 'BrowserDomHelperSelectorError: Browser DOM helper could not resolve selector "x"'), "seletor também")
        ok(not c.dica("browser", "clicked"), "clique que deu certo: nada")
        ok(not c.dica("code_execution_tool", erro), "só no navegador")
        ok(not c.dica("browser", erro + c.DICA), "não repete a dica")
        ext = (RAIZ / "extensions" / "python" / "tool_execute_after" / "_11_clique_que_sumiu.py").read_text(encoding="utf-8")
        ok("clique.dica(" in ext, "a extensão usa a regra")

    async def rodar(self, so: str = "") -> dict:
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc()[-600:]})
        passou = sum(1 for r in self.resultados if r["ok"])
        return {"passou": passou, "total": len(self.resultados), "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio
    r = asyncio.run(Suite().rodar())
    print(f"{r['passou']}/{r['total']}")

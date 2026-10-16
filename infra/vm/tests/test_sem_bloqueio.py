"""No plugin calls the phone bridge (`….enviar(…)`, a blocking HTTP call that waits on Telegram) or the prospecting
reviewer straight from async code: that froze every other chat while it waited (12/10 review). They go through
`await asyncio.to_thread(…)`. Run from the repository root: python3 infra/vm/tests/test_sem_bloqueio.py"""

import ast
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
BLOQUEANTES = re.compile(r"(^|\.)(enviar|_chamar_revisor|revisar_textos|propor|comentar|processar_direct)$")


class Achar(ast.NodeVisitor):
    def __init__(self):
        self.pilha, self.achados = [], []

    def _func(self, no, assincrona):
        self.pilha.append(assincrona)
        self.generic_visit(no)
        self.pilha.pop()

    def visit_AsyncFunctionDef(self, no):
        self._func(no, True)

    def visit_FunctionDef(self, no):
        self._func(no, False)

    def visit_Lambda(self, no):
        self._func(no, False)

    def visit_Await(self, no):  # `await x.enviar(…)` is a coroutine (e.g. the WhatsApp Web driver), not a blocking call
        if isinstance(no.value, ast.Call):
            no.value._aguardada = True
        self.generic_visit(no)

    def visit_Call(self, no):
        if self.pilha and self.pilha[-1] and not getattr(no, "_aguardada", False) and BLOQUEANTES.search(ast.unparse(no.func)):
            self.achados.append(no.lineno)
        self.generic_visit(no)


def main() -> int:
    falhas = []
    for arquivo in sorted((RAIZ / "infra" / "vm" / "plugins").rglob("*.py")):
        if "/tests/" in str(arquivo):
            continue
        a = Achar()
        a.visit(ast.parse(arquivo.read_text(encoding="utf-8")))
        falhas += [f"{arquivo.relative_to(RAIZ)}:{linha}" for linha in a.achados]
    for f in falhas:
        print("BLOQUEIA O LAÇO", f)
    print("sem bloqueio:", "ok" if not falhas else f"{len(falhas)} chamada(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

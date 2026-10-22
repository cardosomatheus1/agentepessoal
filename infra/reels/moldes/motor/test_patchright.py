"""On the agent VM there is only patchright, which evaluates in an isolated world by default: the motor must evaluate
in the page's own world, where the template sets window.MOTOR_PRONTO (22/10: every render there stopped at 60 s)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import _mundo_da_pagina  # noqa: E402


class Page:
    def evaluate(self, expression, arg=None, *, isolated_context=True):
        return (expression, arg, isolated_context)


_mundo_da_pagina(Page)
_mundo_da_pagina(Page)  # twice: still one wrapper
falhas = 0
for nome, cond in (("no mundo da página por padrão", Page().evaluate("window.MOTOR_PRONTO") == ("window.MOTOR_PRONTO", None, False)),
                   ("o argumento passa", Page().evaluate("f", 3)[1] == 3),
                   ("isolado só se pedir", Page().evaluate("x", isolated_context=True)[2] is True)):
    print(("ok  " if cond else "FALHOU ") + nome)
    falhas += not cond
sys.exit(1 if falhas else 0)

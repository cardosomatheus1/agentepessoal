"""12/10 evening: two rounds gave up ("PRECISA DE VOCÊ") because a browser click used a reference the page had already
re-rendered (Instagram rebuilds the profile after loading) and the agent retried the same reference. Any browser task
can hit this, so the hint rides on the failed click's own result."""

import re

SUMIU = re.compile(r"could not find reference|could not resolve selector|element is not attached|"
                   r"element is detached|stale element", re.I)

DICA = ("\n\n↻ A página mudou depois que você a leu (ela se redesenha ao carregar): essa referência não existe mais. "
        "Não repita o mesmo clique. Leia a página de novo (`browser` content) e use a referência nova; se o elemento "
        "tem texto visível, clique por ele (selector `text=Mensagem`, por exemplo) ou rode um `evaluate` que acha pelo "
        "texto. Só desista depois de recarregar a página uma vez.")


def dica(tool_name: str, mensagem: str) -> str:
    """The hint to add to a failed browser click, or ''."""
    if tool_name != "browser" or not SUMIU.search(mensagem or "") or "↻ A página mudou" in (mensagem or ""):
        return ""
    return DICA

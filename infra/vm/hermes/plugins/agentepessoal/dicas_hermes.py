"""Dicas no resultado de uma ferramenta que falhou de um jeito conhecido (27/10, histórico de 7 dias): o modelo lê a dica
junto do erro e não repete a mesma chamada.

- browser_click / browser_type: 33 de 61 cliques e 14 de 33 digitações deram "Unknown ref: eN": a página mudou (ou a
  lista de refs foi refeita) e a ref antiga não existe mais. A dica manda ler a tela de novo antes de tentar.

Roda dentro do gancho `transform_tool_result` do cofre (cofre_hermes.DEPOIS), depois da máscara: no Hermes só o
primeiro gancho que devolve texto vale, então os dois não podem ser ganchos separados.
"""
import re

REF_SUMIU = re.compile(r"Unknown ref:\s*(@?e\d+)", re.I)
DICA_REF = ("\n\n⚠️ A ref {ref} não existe mais: a página mudou ou as refs foram refeitas. Rode `browser_snapshot` agora "
            "e use a ref NOVA do elemento; não repita {ref}.")


def dica(tool_name: str, resultado: str, kw=None) -> str:
    if tool_name in ("browser_click", "browser_type", "browser_press", "browser_hover", "browser_select"):
        m = REF_SUMIU.search(resultado[:2000])
        if m and "browser_snapshot` agora" not in resultado:
            return resultado + DICA_REF.format(ref=m.group(1))
    return resultado


def registrar(cofre) -> None:
    if dica not in cofre.DEPOIS:
        cofre.DEPOIS.append(dica)

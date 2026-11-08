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


# 06-07/11 (5×): o agente esperava 12-15 s dentro do script do browser_console, que desiste em 10 s (Runtime.evaluate no
# supervisor do Hermes), e o erro era só "TimeoutError: ": ele repetia a mesma espera.
CONSOLE_TEMPO = re.compile(r'"success":\s*false[^}]*"error":\s*"TimeoutError')
DICA_CONSOLE = ("\n\n⚠️ O browser_console desiste em 10 s: não espere dentro do script (setTimeout ou laço de 10 s ou mais). "
                "Espere com `terminal` (`sleep N`) e depois rode no console só a leitura, sem espera.")


def dica(tool_name: str, resultado: str, kw=None) -> str:
    if tool_name in ("browser_click", "browser_type", "browser_press", "browser_hover", "browser_select"):
        m = REF_SUMIU.search(resultado[:2000])
        if m and "browser_snapshot` agora" not in resultado:
            return resultado + DICA_REF.format(ref=m.group(1))
    if tool_name == "browser_console" and CONSOLE_TEMPO.search(resultado[:2000]) and "desiste em 10 s" not in resultado:
        return resultado + DICA_CONSOLE
    return resultado


def registrar(cofre) -> None:
    if dica not in cofre.DEPOIS:
        cofre.DEPOIS.append(dica)

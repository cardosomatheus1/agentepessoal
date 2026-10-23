"""Ferramentas do operador que falam com o Agent Zero (A0): desde a virada de 23/10 o agente é o Hermes e o A0 fica
PARADO só para a volta (até 30/10; docs/MIGRACAO_HERMES.md). Estas ferramentas não fazem nada com o A0 parado e, ligadas
por engano, poderiam religá-lo pela interface dele (as rotinas rodariam nos dois). Por isso param aqui, dizendo o que
usar no lugar; só rodam com A0_LEGADO=1 (depois de `python3 infra/operador/virada.py voltar`)."""
import os
import sys


def parar(nome: str, no_lugar: str) -> None:
    if os.environ.get("A0_LEGADO") == "1":
        return
    print(f"{nome}: LEGADO do Agent Zero (parado desde a virada ao Hermes, 23/10).\n"
          f"No lugar: {no_lugar}\n(Depois de voltar ao A0 com virada.py voltar: A0_LEGADO=1 para usar.)", file=sys.stderr)
    raise SystemExit(3)

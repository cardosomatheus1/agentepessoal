"""Run, outside the VM, every plugin test suite that does not need a running Agent Zero (CI and before a commit).
Usage, from the repository root:  python3 infra/operador/rodar_suites_locais.py [plugin ...]

Suites only touch "teste_*" logins or temporary folders; some write under /a0/usr (in CI it is created empty).
Exit code 1 if any test fails. auxiliar needs the live scheduler: it runs on the VM (implantar.py / rodar_testes.py)."""

import asyncio
import importlib.util
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SO_NA_VM = {"auxiliar"}


def main() -> int:
    os.environ.setdefault("CI", "1")  # suites skip what needs the agent itself (e.g. prospeccao t_botoes)
    pedidos = set(sys.argv[1:])
    falhas = total = 0
    for suite in sorted((RAIZ / "infra" / "vm" / "plugins").glob("*/tests/suite.py")):
        plugin = suite.parents[1].name
        if plugin in SO_NA_VM or (pedidos and plugin not in pedidos):
            continue
        spec = importlib.util.spec_from_file_location(f"suite_{plugin}", suite)
        m = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(m)
            r = asyncio.run(m.Suite().rodar(""))
        except Exception as exc:
            print(f"✗ {plugin}: a suíte não carregou ({type(exc).__name__}: {exc})")
            falhas += 1
            continue
        total += r["total"]
        ruins = [x for x in r["resultados"] if not x["ok"]]
        falhas += len(ruins)
        print(f"{'✓' if not ruins else '✗'} {plugin}: {r['passou']}/{r['total']}")
        for x in ruins:
            print(f"    ✗ {x['teste']}: {str(x.get('erro', ''))[:300]}")
    print(f"TOTAL {total - falhas}/{total}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

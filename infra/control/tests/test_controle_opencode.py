"""Página de controle: "Abrir OpenCode" (23/10) só aparece com a VM ligada e o túnel do OpenCode respondendo.
Run from the repository root: python3 infra/control/tests/test_controle_opencode.py"""

import importlib.util
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def main() -> int:
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.update(INSTANCE_ID="i-1", PASSWORD_SHA256="0" * 64)
    sys.path.insert(0, str(RAIZ / "infra" / "control"))
    spec = importlib.util.spec_from_file_location("index_teste", RAIZ / "infra" / "control" / "index.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    falhas = []
    params = {m.URL_PARAM: "https://a.trycloudflare.com", m.PHONE_PARAM: "https://b.trycloudflare.com",
              m.OPENCODE_PARAM: "https://c.trycloudflare.com"}
    m._param = params.get
    vivos = {"https://a.trycloudflare.com", "https://c.trycloudflare.com"}
    m._reachable = lambda url: url in vivos
    m._state = lambda: "running"
    s = m._status()
    if s["opencode_url"] != "https://c.trycloudflare.com" or s["phone_url"]:
        falhas.append(f"ligada e respondendo: {s}")
    vivos.discard("https://c.trycloudflare.com")  # túnel caído (530): o botão some
    if m._status()["opencode_url"]:
        falhas.append("túnel do OpenCode fora: sem botão")
    m._state = lambda: "stopped"
    if m._status()["opencode_url"]:
        falhas.append("VM desligada: sem botão")
    if 'id="opencode"' not in m.PAGE or '$("opencode").href=s.opencode_url' not in m.PAGE:
        falhas.append("página sem o botão Abrir OpenCode")
    print(f"TESTES {'ok' if not falhas else 'FALHOU'}")
    for f in falhas:
        print("  ✗", f)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

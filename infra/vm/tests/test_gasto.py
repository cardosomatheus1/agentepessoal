"""/gasto prices each model by its own rate (12/10 review: Haiku and Nova were priced as Luna). Temporary usage log
only. Run from the repository root: python3 infra/vm/tests/test_gasto.py (boto3 needed for the import, no AWS call)."""

import importlib.util
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def main() -> int:
    spec = importlib.util.spec_from_file_location("ponte_gasto_teste", RAIZ / "infra" / "vm" / "ponte_whatsapp.py")
    p = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)
    tmp = Path(tempfile.mkdtemp(prefix="gasto-"))
    falhas = []
    try:
        agora = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        linhas = [  # one million output tokens each, nothing else: the cost is the output price
            {"em": agora, "modelo": "openai.gpt-6-luna", "entrada": 0, "saida": 1_000_000},
            {"em": agora, "modelo": "openai.gpt-6.1-sol", "entrada": 0, "saida": 1_000_000},
            {"em": agora, "modelo": "us.anthropic.claude-haiku-5-5", "entrada": 0, "saida": 1_000_000},
            {"em": agora, "modelo": "us.amazon.nova-pro-v1:0", "entrada": 0, "saida": 1_000_000},
            # cache: 1 M read + 1 M written on Haiku
            {"em": agora, "modelo": "us.anthropic.claude-haiku-5-5", "entrada": 2_000_000, "cache": 1_000_000,
             "cache_gravado": 1_000_000, "saida": 0},
        ]
        p.USO = tmp / "uso.jsonl"
        p.USO.write_text("\n".join(json.dumps(l) for l in linhas) + "\n")
        hoje, mes = p.gasto()
        esperado = 0.55 + 11.0 + 2.75 + 1.60 + (0.055 + 0.1375)
        if abs(hoje - esperado) > 1e-6 or abs(mes - esperado) > 1e-6:
            falhas.append(f"gasto: esperado US$ {esperado:.4f}, veio hoje {hoje:.4f} / mês {mes:.4f}")
        if p.preco("us.amazon.nova-2-lite-v1:0") != p.PRECOS["luna"]:
            falhas.append("modelo sem preço próprio cai no da Luna")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for f in falhas:
        print("FALHA", f)
    print("gasto:", "ok" if not falhas else f"{len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

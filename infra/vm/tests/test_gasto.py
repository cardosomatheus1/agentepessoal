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
            # 20/10: Sonnet 5.5 for Matheus — its own price, not the Luna fallback
            {"em": agora, "modelo": "us.anthropic.claude-sonnet-5-5", "entrada": 1_000_000, "cache": 1_000_000, "saida": 1_000_000},
            # cache: 1 M read + 1 M written on Haiku
            {"em": agora, "modelo": "us.anthropic.claude-haiku-5-5", "entrada": 2_000_000, "cache": 1_000_000,
             "cache_gravado": 1_000_000, "saida": 0},
        ]
        p.USO = tmp / "uso.jsonl"
        p.USO.write_text("\n".join(json.dumps(l) for l in linhas) + "\n")
        hoje, mes = p.gasto()
        esperado = 0.55 + 11.0 + 2.75 + 1.60 + (0.055 + 0.1375) + (0.20 + 10.0)
        if abs(hoje - esperado) > 1e-6 or abs(mes - esperado) > 1e-6:
            falhas.append(f"gasto: esperado US$ {esperado:.4f}, veio hoje {hoje:.4f} / mês {mes:.4f}")
        # 15/10 guests: spending per person (the proxy logs X-A0-Dono) and the guest's daily limit
        mais = [{"em": agora, "modelo": "openai.gpt-6.1-sol", "entrada": 0, "saida": 400_000, "dono": "ilia"},
                {"em": agora, "modelo": "openai.gpt-6.1-sol", "entrada": 0, "saida": 100_000, "dono": "matheus"}]
        p.USO.write_text("\n".join(json.dumps(l) for l in linhas + mais) + "\n")
        so_ilia, _ = p.gasto("ilia")
        if abs(so_ilia - 4.4) > 1e-6:
            falhas.append(f"gasto só do Ilia: esperado 4.40, veio {so_ilia:.4f}")
        if abs(p.gasto()[0] - (esperado + 5.5)) > 1e-6:
            falhas.append("sem dono, o total soma todo mundo")
        if p.limite_convidado("ilia") or p.limite_convidado("matheus"):
            falhas.append("abaixo do teto (US$ 4.40 de 5), a mensagem do convidado passa; o dono nunca tem teto")
        mais.append({"em": agora, "modelo": "openai.gpt-6.1-sol", "entrada": 0, "saida": 100_000, "dono": "ilia"})
        p.USO.write_text("\n".join(json.dumps(l) for l in linhas + mais) + "\n")
        if "limite de uso de hoje" not in p.limite_convidado("ilia") or p.limite_convidado("matheus"):
            falhas.append("passou de US$ 5 no dia: o convidado é avisado e a mensagem não vai ao agente")
        if "de US$ 5 por dia" not in p.texto_gasto("ilia") or "Hoje: US$ 5.50" not in p.texto_gasto("ilia"):
            falhas.append(f"/gasto do convidado mostra só o dele: {p.texto_gasto('ilia')!r}")
        # 16/10: guests' scheduled tasks stop too — the agent reads <login>/limite_hoje.txt
        marcas = tmp / "marcas"
        (marcas / "will").mkdir(parents=True)
        (marcas / "will" / "limite_hoje.txt").write_text("2026-10-15")
        estado = p.marcar_limites(marcas)
        if not (estado.get("ilia") and (marcas / "ilia" / "limite_hoje.txt").read_text().count("-") == 2
                and estado.get("will") is False and not (marcas / "will" / "limite_hoje.txt").exists()):
            falhas.append(f"marca de limite: quem passou ganha a data de hoje, quem não passou fica sem: {estado}")
        spec_c = importlib.util.spec_from_file_location(
            "convidados_gasto_teste", RAIZ / "infra" / "vm" / "plugins" / "login_usuarios" / "helpers" / "convidados.py")
        c = importlib.util.module_from_spec(spec_c)
        spec_c.loader.exec_module(c)
        if {k: v["teto_dia_usd"] for k, v in c.CONVIDADOS.items()} != p.CONVIDADOS_TETO:
            falhas.append("tetos da ponte e do plugin login_usuarios diferentes")
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

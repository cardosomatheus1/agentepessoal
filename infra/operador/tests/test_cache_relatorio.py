"""Prompt-cache report (cache_relatorio.py) over a synthetic usage log: totals, cost equal to /gasto and the cause of
each cache miss. No AWS. Run from the repository root: python3 infra/operador/tests/test_cache_relatorio.py"""

import datetime as dt
import importlib.util
import json
import sys
import tempfile
import time
import types
from pathlib import Path

AQUI = Path(__file__).resolve()
RAIZ = AQUI.parents[3]


def _carregar(nome, arquivo):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    r = _carregar("cache_relatorio_teste", RAIZ / "infra" / "operador" / "cache_relatorio.py")
    falhas = []

    def ok(cond, msg):
        if not cond:
            falhas.append(msg)

    base = dt.datetime.now(dt.timezone.utc).timestamp() - 3 * 3600

    def em(minutos):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(base + minutos * 60))

    I1, I2 = {"n": 9000, "ini": "aaaa", "todo": "a1"}, {"n": 9100, "ini": "aaaa", "todo": "a2"}
    F1, F2 = {"n": 40000, "ini": "ffff", "todo": "f1"}, {"n": 40000, "ini": "fff2", "todo": "f2"}
    P1 = {"n": 300, "ini": "pppp", "todo": "p1"}
    rot = {"conversa": "ctxR", "rotina": "HL76nfIg", "agente": 0, "papel": "chat", "modelo": "openai.gpt-6-luna",
           "api": "responses", "cache_retention": "24h", "dono": "matheus"}
    conv = {"conversa": "ctxM", "agente": 0, "papel": "chat", "modelo": "us.anthropic.claude-sonnet-5-5",
            "api": "converse", "dono": "matheus"}
    linhas = [
        # before the window: only the base of comparison for the first call inside it
        {**rot, "em": em(-600), "status": 200, "entrada": 50000, "cache": 0, "cache_gravado": 50000, "saida": 10,
         "instrucoes": I1, "ferramentas": F1, "primeira": P1, "mensagens": 4},
        # routine: read, then a miss because the tools changed, then a miss with nothing changed at the start
        {**rot, "em": em(0), "status": 200, "entrada": 50000, "cache": 45000, "cache_gravado": 5000, "saida": 10,
         "instrucoes": I1, "ferramentas": F1, "primeira": P1, "mensagens": 6},
        {**rot, "em": em(1), "status": 200, "entrada": 50000, "cache": 0, "cache_gravado": 50000, "saida": 10,
         "instrucoes": I1, "ferramentas": F2, "primeira": P1, "mensagens": 8},
        {**rot, "em": em(2), "status": 200, "entrada": 50000, "cache": 1000, "cache_gravado": 49000, "saida": 10,
         "instrucoes": I1, "ferramentas": F2, "primeira": P1, "mensagens": 10},
        # Matheus's chat on Claude: 1 h writes, then 20 min later a read (1 h cache alive), then summarized history
        {**conv, "em": em(10), "status": 200, "entrada": 60000, "cache": 0, "cache_gravado": 60000,
         "cache_gravado_1h": 60000, "saida": 100, "instrucoes": I1, "ferramentas": F1, "primeira": P1, "mensagens": 20},
        {**conv, "em": em(30), "status": 200, "entrada": 61000, "cache": 60000, "cache_gravado": 1000,
         "cache_gravado_1h": 1000, "saida": 100, "instrucoes": I1, "ferramentas": F1, "primeira": P1, "mensagens": 22},
        {**conv, "em": em(31), "status": 200, "entrada": 40000, "cache": 0, "cache_gravado": 40000,
         "cache_gravado_1h": 40000, "saida": 100, "instrucoes": I2, "ferramentas": F1, "primeira": P1, "mensagens": 5},
        # the same chat 3 h later in a 5-minute line (no 1 h write before): expired
        {**conv, "em": em(170), "status": 200, "entrada": 41000, "cache": 0, "cache_gravado": 41000, "saida": 100,
         "instrucoes": I2, "ferramentas": F1, "primeira": P1, "mensagens": 7},
        # an old line without tracking (before the deploy) and a failed call (not counted)
        {"em": em(5), "modelo": "openai.gpt-6-luna", "status": 200, "entrada": 30000, "cache": 0, "cache_gravado": 30000,
         "saida": 5},
        {**conv, "em": em(6), "status": 400, "entrada": 99999, "cache": 0, "cache_gravado": 0, "saida": 0},
        {"em": em(7), "modelo": "openai.gpt-6-luna", "status": 200, "entrada": 500, "cache": 0, "saida": 5},  # tiny
    ]
    cru = [json.dumps(x) for x in linhas] + ["não é json"]
    g = r.analisar(cru, base - 60, {"HL76nfIg": "📡 Radar"})
    ro, co, so = g.get("rotina HL76nfIg"), g.get("conversa ctxM"), g.get(r.origem({}))
    ok(ro and ro["chamadas"] == 3 and ro["falhas"] == 2 and ro["nome"] == "📡 Radar",
       f"rotina: 3 chamadas na janela, 2 falhas, nome da tarefa ({ro})")
    ok(ro and ro["causas"] == {"mudou ferramentas": 1, "nada mudou no começo": 1}, f"causas da rotina: {ro and ro['causas']}")
    ok(co and co["chamadas"] == 4 and co["falhas"] == 3, f"conversa: 4 chamadas (a de erro 400 fica fora), 3 falhas ({co})")
    ok(co and co["causas"] == {"1ª chamada": 1, "mudou instrucoes": 1, "histórico encurtado": 1, "expirou": 1}, f"causas da conversa: {co and co['causas']}")
    ok(co and co["gravado_1h"] == 101000, "gravação de 1 h somada")
    ok(so and so["chamadas"] == 2 and so["causas"] == {"sem rastreio": 1}, f"linha antiga: sem origem e sem causa ({so})")
    # a 20-minute pause on a 1 h line is not an expiry; on a 5 min line it is
    a = {**conv, "em": em(0), "cache_gravado_1h": 10, "instrucoes": I1}
    ok(r.causas({**a, "em": em(20)}, a) == ["nada mudou no começo"], "1 h: 20 min parado ainda não expirou")
    b = {**conv, "em": em(0), "instrucoes": I1}
    ok(r.causas({**b, "em": em(20)}, b) == ["expirou (20 min parado)"], "5 min: 20 min parado expirou")
    gpt = {**rot, "em": em(0)}
    gpt.pop("cache_retention")
    ok(r.causas({**gpt, "em": em(40)}, gpt) == ["expirou (40 min parado)"], "GPT sem 24 h: 30 min")
    ok(r.causas({**rot, "em": em(40)}, {**rot, "em": em(0)}) == ["expirou (40 min parado)"],
       "GPT com 24 h pedido: ainda conta 30 min (o Bedrock aceitou o campo, mas não segurou o cache no teste de 20/10)")
    ok(r.causas(gpt, None) == ["1ª chamada"], "sem chamada anterior")
    # same prices and cost as /gasto
    sys.modules.setdefault("boto3", types.SimpleNamespace(client=lambda *a, **k: None))
    ponte = _carregar("ponte_relatorio_teste", RAIZ / "infra" / "vm" / "ponte_whatsapp.py")
    ok(r.PRECOS == ponte.PRECOS, "tabela de preços igual à do /gasto (ponte_whatsapp.PRECOS)")
    tmp = Path(tempfile.mkdtemp(prefix="relatorio-")) / "uso.jsonl"
    hoje = [{**x, "em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} for x in linhas if x.get("status") == 200]
    tmp.write_text("\n".join(json.dumps(x) for x in hoje) + "\n")
    ponte.USO = tmp
    ok(abs(sum(r.custo(x) for x in hoje) - ponte.gasto()[0]) < 1e-9, "custo igual ao do /gasto")
    ok(abs(r.custo({"modelo": "us.anthropic.claude-sonnet-5-5", "entrada": 1_000_000, "cache_gravado": 1_000_000,
                    "cache_gravado_1h": 1_000_000}) - 4.0) < 1e-9, "gravar 1 h no Sonnet: 2x a entrada (US$ 4/M)")
    t = r.texto(g, 3)
    ok("rotina HL76nfIg «📡 Radar» [matheus]" in t and "falhas: mudou ferramentas 1" in t and "(1 h:" in t,
       f"texto do relatório:\n{t}")
    ok(r.texto(g, 3, top=1).count("chamadas ·") == 1 and "(+2 origens" in r.texto(g, 3, top=1), "corte em --top")
    # on the VM: this file goes base64 and only numbers go in the command line
    enviado = []
    sys.modules["implantar"] = types.SimpleNamespace(vm=lambda cmd, timeout=0: enviado.append(cmd) or "ok")
    ok(r.na_vm(["--horas", "6", "--top", "5"]) == "ok" and "--horas 6 --top 5" in enviado[0]
       and "base64 -d | python3 -" in enviado[0] and r.USO_VM in enviado[0], f"comando na VM: {enviado[:1]}")
    try:
        r.na_vm(["--horas", "1; rm -rf /"])
        ok(False, "--horas que não é número é recusado")
    except ValueError:
        pass
    for f in falhas:
        print("FALHA", f)
    print("cache_relatorio:", "ok" if not falhas else f"{len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

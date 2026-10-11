"""Real test (on the VM host) of more than one request at a time from the phone, with the test login
"teste_par" (its phone messages go to /opt/a0/usr/testes/celular.jsonl, nothing is sent):
1. a long request keeps the main phone chat busy;
2. a new request in the meantime runs in a parallel chat and its answer arrives marked ↪️;
3. a correction ("também…") goes to the running request, which answers with it.
Run: python3 paralelo.py"""

import json
import time
import urllib.request
from pathlib import Path

USR = Path("/opt/a0/usr")
LOGIN = "teste_par"
CAIXA = USR / "testes" / "celular.jsonl"
A0 = "http://127.0.0.1:50080"
falhas = []


def ok(cond, oque):
    print(("OK   " if cond else "FALHA") + " " + oque, flush=True)
    if not cond:
        falhas.append(oque)


def receber(texto: str) -> dict:
    corpo = {"usuario": LOGIN, "texto": texto, "id": f"par-{time.time()}"}
    req = urllib.request.Request(f"{A0}/api/plugins/whatsapp/receber", data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json",
                                          "X-Chave": (USR / "whatsapp" / ".chave").read_text().strip()})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read() or b"{}")


def caixa(desde: float) -> list[str]:
    if not CAIXA.exists():
        return []
    itens = [json.loads(l) for l in CAIXA.read_text().splitlines() if l.strip()]
    return [i["texto"] for i in itens if i["usuario"] == LOGIN and i["em"] >= desde]


desde = time.time()
r1 = receber("Rode no terminal o comando `sleep 70 && echo PRONTO-LONGO` e, quando terminar, me responda só a "
             "palavra que apareceu.")
ok(not r1.get("paralela"), f"1º pedido na conversa principal: {r1}")
time.sleep(15)
r2 = receber("Quanto é 17 vezes 3? Responda só o número.")
ok(r2.get("paralela") is True and r2.get("context") != r1.get("context"), f"2º pedido em paralelo: {r2}")
r3 = receber("também me diga no fim, entre parênteses, o número 4242")
ok(not r3.get("paralela") and r3.get("context") == r1.get("context"), f"correção foi para a tarefa em andamento: {r3}")

fim = time.time() + 300
while time.time() < fim:
    msgs = caixa(desde)
    if any("PRONTO-LONGO" in m for m in msgs) and any(m.startswith("↪️") for m in msgs):
        break
    time.sleep(5)
msgs = caixa(desde)
print("celular:", [m[:90] for m in msgs])
ok(any(m.startswith("⚡") for m in msgs), "avisou que ia fazer em paralelo")
par = [m for m in msgs if m.startswith("↪️")]
ok(par and "51" in par[0], f"resposta paralela 51 marcada com ↪️: {par[:1]}")
longo = [m for m in msgs if "PRONTO-LONGO" in m]
ok(bool(longo), "o pedido longo terminou e respondeu")
ok(longo and "4242" in longo[-1], f"a correção entrou no pedido longo: {longo[-1:]}")
i_par = next((i for i, m in enumerate(msgs) if m.startswith("↪️")), 99)
i_longo = next((i for i, m in enumerate(msgs) if "PRONTO-LONGO" in m), -1)
ok(i_par < i_longo, "a resposta paralela chegou antes de o longo terminar")
print("\nRESULTADO:", "PASSOU" if not falhas else f"{len(falhas)} falha(s): {falhas}")

"""A pergunta do operador com botões (perguntar_matheus.py): ids "op:" que a ponte anota, limites do Telegram e o comando
da VM sem aspas do texto. Rode da raiz: python3 infra/operador/tests/test_perguntar_matheus.py"""
import base64
import importlib.util
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("perguntar_matheus", RAIZ / "operador" / "perguntar_matheus.py")
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)
falhas = []


def ok(cond, msg):
    if not cond:
        falhas.append(msg)


m = pm.montar(["Liberar", "o", "e-mail?", "--botao", "ses:sim=Liberar", "--botao", "ses:nao=Ainda não"])
ok(m["texto"] == "Liberar o e-mail?" and [b["id"] for b in m["botoes"]] == ["op:ses:sim", "op:ses:nao"] and m["app"] is None,
   f"botões de escolha com id op: {m}")
m = pm.montar(["Marque o quadrado", "--app", "Abrir navegador=https://x.example/navegador"])
ok(m["app"] == {"titulo": "Abrir navegador", "url": "https://x.example/navegador"} and not m["botoes"], f"botão de página: {m}")
for ruim, motivo in ((["t", "--botao", "a=1", "--botao", "b=2", "--botao", "c=3", "--botao", "d=4"], "até 3"),
                     (["t", "--botao", "x" * 70 + "=y"], "64 bytes"),
                     (["t", "--app", "a=http://inseguro"], "https"),
                     (["t", "--botao", "a=1", "--app", "b=https://x.example"], "separadas"),
                     (["--botao", "a=1"], "sem texto")):
    try:
        pm.montar(ruim)
        falhas.append(f"devia recusar ({motivo}): {ruim}")
    except ValueError as exc:
        ok(motivo in str(exc), f"motivo certo para {ruim}: {exc}")
c = pm.comando({"texto": "aspas \" e $(rm -rf /) ficam no base64", "botoes": [], "app": None})
ok("rm -rf" not in c and '\\"' not in c.split("-c ", 1)[1][1:-1], "o texto não entra cru no comando")
b64 = re.search(r"b64decode\('([^']+)'\)", c).group(1)
ok(json.loads(base64.b64decode(b64))["texto"].startswith("aspas"), "a mensagem volta inteira do base64")
ok("tipo='resposta'" in c and "sempre=True" in c, "vai como resposta, sem esperar o silêncio nem cair no filtro de repetida")
for f in falhas:
    print("FALHA", f)
print("perguntar_matheus:", "ok" if not falhas else f"{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)

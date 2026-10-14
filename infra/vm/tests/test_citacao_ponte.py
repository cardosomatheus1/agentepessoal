"""A Telegram reply that quotes the agent's message reaches the agent with the quote (14/10: "Pode" quoting the access
code question was read as an answer to the deploy notice). Run from the repository root:
python3 infra/vm/tests/test_citacao_ponte.py (boto3 for the import; no AWS)."""

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("ponte_citacao_teste", RAIZ / "infra" / "vm" / "ponte_whatsapp.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
falhas = []


def ok(cond, msg):
    if not cond:
        falhas.append(msg)


pergunta = "Encontrei a página oficial Solicitar ou alterar código de acesso do Simples Nacional. Você autoriza essa geração/alteração?"
msg = {"text": "Pode", "reply_to_message": {"text": pergunta, "from": {"is_bot": True}}}
t = p.com_citacao(msg, "Pode")
ok(t.startswith("Pode") and "citando à sua mensagem" in t and "código de acesso" in t, t)
ok(p.com_citacao({"text": "Pode"}, "Pode") == "Pode", "sem citação o texto não muda")
parcial = {"text": "isso", "quote": {"text": "Consulta DAS Emitidos"}, "reply_to_message": {"text": pergunta, "from": {"is_bot": True}}}
ok("«Consulta DAS Emitidos»" in p.com_citacao(parcial, "isso"), "citação de um trecho usa só o trecho")
longa = {"text": "ok", "reply_to_message": {"text": "palavra " * 300, "from": {"is_bot": True}}}
ok(len(p.com_citacao(longa, "ok")) < 900, "citação longa é cortada")
dele = {"text": "esse", "reply_to_message": {"caption": "foto da nota", "from": {"is_bot": False}}}
ok("citando à mensagem: «foto da nota»" in p.com_citacao(dele, "esse"), "citação de mensagem dele mesmo (legenda)")

# the whole path: preparar_tg keeps the quote
p.tg = lambda metodo, dados, *a: {}
item = {"usuario": "matheus", "chat": "42", "update": {"update_id": 7, "message": {"message_id": 9, **msg}}}
pronto = p.preparar_tg(item)
ok("código de acesso" in pronto["texto"] and pronto["texto"].startswith("Pode"), pronto["texto"])

print("\n".join("FALHOU: " + f for f in falhas) or "citacao: ok")
sys.exit(1 if falhas else 0)

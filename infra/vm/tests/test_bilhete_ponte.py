"""One-time delivery tickets: the phone bridge (host) stamps each delivery, the whatsapp plugin (container) asks back
before acting, so the agent cannot fake a phone message or an "aprovar" with the shared key (12/10 review).
Run from the repository root: python3 infra/vm/tests/test_bilhete_ponte.py (boto3 needed for the import, no AWS call)."""

import importlib.util
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Resposta:
    def __init__(self, corpo: dict):
        self.corpo = json.dumps(corpo).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.corpo


def main() -> int:
    ponte = _carregar("ponte_bilhete_teste", RAIZ / "infra" / "vm" / "ponte_whatsapp.py")
    plugin = _carregar("whatsapp_ponte_bilhete_teste", RAIZ / "infra" / "vm" / "plugins" / "whatsapp" / "helpers" / "ponte.py")
    falhas = []

    def ok(cond, msg):
        if not cond:
            falhas.append(msg)

    dados = {"usuario": "matheus", "texto": "aprovar ✅", "audio": "", "anexos": ["/a0/usr/x.pdf"], "botao": "",
             "id": "wamid.1", "nome": "Matheus"}
    ok(ponte.CAMPOS_BILHETE == plugin.CAMPOS_BILHETE, "ponte e plugin conferem os mesmos campos")
    ok(ponte.resumo_entrega(dados) == plugin.resumo_entrega(json.loads(json.dumps(dados))),
       "o resumo da entrega é o mesmo dos dois lados (depois do JSON)")

    agora = 1_800_000_000.0
    b = ponte.novo_bilhete(dados, agora)
    ok(not ponte.conferir_bilhete(b, ponte.resumo_entrega({**dados, "texto": "aprovar tudo"}), agora + 1),
       "bilhete de outra mensagem não vale")
    b = ponte.novo_bilhete(dados, agora)
    ok(ponte.conferir_bilhete(b, ponte.resumo_entrega(dados), agora + 1), "bilhete certo vale")
    ok(not ponte.conferir_bilhete(b, ponte.resumo_entrega(dados), agora + 2), "e só uma vez")
    b = ponte.novo_bilhete(dados, agora)
    ok(not ponte.conferir_bilhete(b, ponte.resumo_entrega(dados), agora + ponte.VALIDADE_BILHETE + 1), "vencido não vale")
    ok(not ponte.conferir_bilhete("inventado", ponte.resumo_entrega(dados), agora), "inventado não vale")

    # the bridge stamps what it delivers to the plugin
    enviados = []
    original = ponte.urllib.request.urlopen
    ponte.urllib.request.urlopen = lambda req, timeout=0: enviados.append(json.loads(req.data)) or _Resposta({"ok": True})
    try:
        ponte.entregar(dict(dados))
    finally:
        ponte.urllib.request.urlopen = original
    entregue = enviados[0]
    ok(entregue.get("bilhete") and entregue["texto"] == dados["texto"], f"a entrega leva o bilhete: {entregue}")

    # the plugin asks the bridge (here the bridge's own function stands in for its HTTP endpoint)
    pedidos = []

    def bridge(req, timeout=0):
        corpo = json.loads(req.data)
        pedidos.append((req.full_url, req.headers.get("X-chave")))
        return _Resposta({"ok": ponte.conferir_bilhete(corpo["bilhete"], corpo["resumo"])})

    plugin._abrir = bridge
    plugin.chave = lambda: "k"
    ok(plugin.entrega_da_ponte(json.loads(json.dumps(entregue))), "entrega da ponte passa")
    ok(pedidos and pedidos[0][0].endswith(":8789/conferir"), f"pergunta à ponte: {pedidos}")
    ok(not plugin.entrega_da_ponte(json.loads(json.dumps(entregue))), "a mesma entrega repetida não passa")
    falsa = {k: v for k, v in entregue.items() if k != "bilhete"}
    ok(not plugin.entrega_da_ponte(falsa), "sem bilhete (o agente com a chave) não passa")
    ok(not plugin.entrega_da_ponte({**falsa, "bilhete": "chute"}), "bilhete chutado não passa")
    ok(plugin.entrega_da_ponte({"usuario": "teste_aux", "texto": "oi"}), "login de teste (não fala com ninguém) passa")
    ok(not plugin.entrega_da_ponte({"usuario": "teste_aux", "texto": "oi", "bilhete": "chute"}),
       "mas, vindo com bilhete, o bilhete é conferido")

    def fora_do_ar(req, timeout=0):
        raise OSError("connection refused")

    plugin._abrir = fora_do_ar
    ok(not plugin.entrega_da_ponte({**entregue, "bilhete": ponte.novo_bilhete(dados)}), "ponte fora do ar: não passa")

    for f in falhas:
        print("FALHA", f)
    print("bilhetes:", "ok" if not falhas else f"{len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

"""Manda um pedido ao agente (o Hermes, depois da virada) como o operador, e mostra a resposta. Usage:

    python3 infra/operador/mandar_msg.py arquivo.txt [sessao]     (sessão padrão: operador-<data>; a resposta NÃO vai ao
                                                                    celular de ninguém: só aparece aqui)

Antes (até 23/10) abria a interface do Agent Zero num navegador; o Hermes não tem interface: o pedido vai à API dele
(/v1/runs) pela VM, e um pedido de ok no meio aparece aqui (responda com hermes_ao_vivo.py run ... --aprovar)."""
import base64
import re
import subprocess
import sys
import time
from pathlib import Path

PROGRAMA = r'''
import json, sys, time, urllib.request
chave = open("/opt/hermes/api_key").read().strip()
def api(caminho, corpo=None):
    req = urllib.request.Request("http://127.0.0.1:8642" + caminho, data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Authorization": "Bearer " + chave, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")
texto, sessao = sys.argv[1], sys.argv[2]
r = api("/v1/runs", {"input": texto, "session_id": sessao})
rid = r.get("run_id") or r.get("id")
print("RUN", rid, "SESSAO", sessao)
fim = time.time() + 1500
while time.time() < fim:
    st = api("/v1/runs/" + rid)
    if st.get("status") == "waiting_for_approval":
        print("PEDE_OK", json.dumps(st.get("approval"), ensure_ascii=False)[:600]); break
    if st.get("status") in ("completed", "failed", "cancelled", "stopped"):
        print("ESTADO", st.get("status")); print(str(st.get("output") or "")[-6000:]); break
    time.sleep(3)
'''


def main(argv: list) -> int:
    if not argv:
        print(__doc__)
        return 2
    texto = Path(argv[0]).read_text(encoding="utf-8")
    sessao = argv[1] if len(argv) > 1 else f"operador-{time.strftime('%Y%m%d')}"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", sessao):
        print("sessão: só letras, números, _ e -")
        return 2
    p64 = base64.b64encode(PROGRAMA.encode()).decode()
    t64 = base64.b64encode(texto.encode()).decode()
    cmd = (f"touch /var/lib/agentepessoal/last-activity; echo {p64} | base64 -d > /tmp/mandar_msg.py && "
           f"timeout 1600 python3 /tmp/mandar_msg.py \"$(echo {t64} | base64 -d)\" '{sessao}'; rm -f /tmp/mandar_msg.py")
    vm = Path(__file__).resolve().parent / "vmcmd.py"
    r = subprocess.run([sys.executable, str(vm), cmd], capture_output=True, text=True)
    print(r.stdout.strip())
    return 0 if "ESTADO completed" in r.stdout else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

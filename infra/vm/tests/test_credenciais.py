"""Short-lived credentials for the agent: "/" is the NEXOS Meta secret role, "/voz" the narration role (22/10), any
other path or a caller outside the VM gets 404. Fake STS. Run from the repository root:
python3 infra/vm/tests/test_credenciais.py (needs boto3 for the import)."""

import datetime as dt
import importlib.util
import io
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("credenciais_meta", RAIZ / "infra" / "vm" / "credenciais_meta.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)

assumidos = []


class StsFalso:
    def get_caller_identity(self):
        return {"Account": "111122223333"}

    def assume_role(self, **kw):
        assumidos.append(kw)
        return {"Credentials": {"AccessKeyId": "A", "SecretAccessKey": "S", "SessionToken": "T",
                                "Expiration": dt.datetime(2026, 10, 22, 12, tzinfo=dt.timezone.utc)}}


cm.boto3.client = lambda *a, **k: StsFalso()


def pedir(caminho, ip="172.17.0.2"):
    h = cm.Handler.__new__(cm.Handler)
    h.path, h.client_address, h.wfile = caminho, (ip, 1), io.BytesIO()
    h.request_version, h.requestline, h.command = "HTTP/1.1", f"GET {caminho}", "GET"
    h.send_response = lambda code: setattr(h, "codigo", code)
    h.send_header = lambda *a: None
    h.end_headers = lambda: None
    h.do_GET()
    return h.codigo, json.loads(h.wfile.getvalue())


falhas = 0


def ok(cond, nome):
    global falhas
    print(("ok   " if cond else "FALHA ") + nome)
    falhas += not cond


codigo, corpo = pedir("/voz")
ok(codigo == 200 and corpo["Version"] == 1 and corpo["SessionToken"] == "T", "/voz entrega credencial no formato credential_process")
ok(assumidos[-1]["RoleArn"].endswith(":role/agentepessoal-voz"), "/voz assume só o papel da voz")
pedir("/")
ok(assumidos[-1]["RoleArn"].endswith(":role/agentepessoal-segredo-meta"), "/ continua sendo o segredo da Meta")
n = len(assumidos)
ok(pedir("/admin")[0] == 404 and len(assumidos) == n, "caminho desconhecido: 404, nada assumido")
ok(pedir("/voz", ip="8.8.8.8")[0] == 404 and len(assumidos) == n, "fora da VM: 404")
sys.exit(1 if falhas else 0)

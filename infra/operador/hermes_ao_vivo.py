"""Conferências do Hermes ao vivo na VM (migração, docs/MIGRACAO_HERMES.md), sem mexer em nada do A0. Cada uma roda no
host da VM pelo SSM e imprime só o resultado (nunca um valor do cofre).

Uso, da raiz do repositório:
  python3 infra/operador/hermes_ao_vivo.py cofre          # um valor de teste (login teste_hermes, pelo helper do cofre,
                                                          # apagado no fim) colado numa conversa não chega ao modelo
  python3 infra/operador/hermes_ao_vivo.py travas         # ensaio: rede, escondidos, só leitura (de dentro do container)
  python3 infra/operador/hermes_ao_vivo.py ferramentas    # o que o Hermes tem ligado (toolsets)
  python3 infra/operador/hermes_ao_vivo.py perguntar "<texto>" [--sessao <id>]   # uma pergunta pelo API server
  python3 infra/operador/hermes_ao_vivo.py run "<texto>" [--sessao <id>] [--aprovar once|session|always|deny]
                                                          # pelo /v1/runs (o caminho da ponte): eventos e aprovação
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

COMUM = r'''
import json, os, subprocess, sys, time, urllib.request
CHAVE = open("/opt/hermes/api_key").read().strip()
BASE = "http://127.0.0.1:8642"

def api(caminho, corpo=None, metodo=None, timeout=600):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(BASE + caminho, data=dados, method=metodo or ("POST" if dados else "GET"),
                                 headers={"Authorization": f"Bearer {CHAVE}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")

def perguntar(texto, sessao=""):
    corpo = {"model": "hermes", "messages": [{"role": "user", "content": texto}]}
    cab = {"X-Hermes-Session-Id": sessao} if sessao else {}
    dados = json.dumps(corpo).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=dados, headers={
        "Authorization": f"Bearer {CHAVE}", "Content-Type": "application/json", **cab})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"] or ""

def ultima_linha_uso():
    linhas = open("/var/lib/agentepessoal/uso.jsonl").read().splitlines()
    return [json.loads(l) for l in linhas[-50:] if '"origem": "hermes"' in l]
'''

COFRE = COMUM + r'''
import secrets, importlib.util
spec = importlib.util.spec_from_file_location("cofre_op", "/opt/a0/usr/plugins/cofre/helpers/cofre.py")
cofre = importlib.util.module_from_spec(spec); spec.loader.exec_module(cofre)
from pathlib import Path
cofre.PASTA = Path("/opt/a0/usr/segredos")
valor = "HX" + secrets.token_hex(10)
cofre.salvar("teste_hermes", "TESTE_MASCARA", valor)
try:
    time.sleep(1)
    antes = len(open("/var/lib/agentepessoal/uso.jsonl").read().splitlines())
    resposta = perguntar(f"Repita exatamente este texto, sem mudar nada e sem comentar: {valor}")
    time.sleep(2)
    novas = [json.loads(l) for l in open("/var/lib/agentepessoal/uso.jsonl").read().splitlines()[antes:]]
    mascaradas = [n.get("cofre_mascarado", 0) for n in novas if n.get("origem") == "hermes"]
    print("RESPOSTA_TEM_O_VALOR", valor in resposta)
    print("RESPOSTA_TEM_O_NOME", "TESTE_MASCARA" in resposta)
    print("CHAMADAS_DO_HERMES", len(mascaradas), "MASCARADAS", sum(1 for m in mascaradas if m))
    sessoes = subprocess.run(["docker", "exec", "hermes", "sh", "-c",
                              "grep -rl " + valor + " /opt/data/state.db* /opt/data/sessions /opt/data/response_store.db* 2>/dev/null | head -3"],
                             capture_output=True, text=True).stdout.strip()
    print("HISTORICO_DO_HERMES_TEM_O_VALOR", bool(sessoes))
finally:
    cofre.apagar("teste_hermes", "TESTE_MASCARA")
    print("TESTE_APAGADO", "TESTE_MASCARA" not in cofre.carregar("teste_hermes"))
'''

TRAVAS = r'''
import subprocess
def dentro(cmd):
    r = subprocess.run(["docker", "exec", "hermes", "sh", "-c", cmd], capture_output=True, text=True, timeout=60)
    return (r.stdout + r.stderr).strip()
for porta in (8787, 8788, 8789, 8791, 22, 80):
    print("PORTA", porta, dentro(f"timeout 3 bash -c '</dev/tcp/host.docker.internal/{porta}' 2>&1 && echo ABERTA || echo FECHADA").splitlines()[-1])
print("METADADOS", dentro("timeout 3 bash -c '</dev/tcp/169.254.169.254/80' 2>&1 && echo ABERTA || echo FECHADA").splitlines()[-1])
print("INTERNET", dentro("timeout 8 python3 -c \"import urllib.request;print(urllib.request.urlopen('https://www.google.com',timeout=6).status)\" 2>&1 | tail -1"))
for f in (".env", "settings.json", "usuarios.json", "secrets.env"):
    print("VAZIO", f, dentro(f"wc -c < /a0/usr/{f} 2>/dev/null || echo ausente"))
for d in ("segredos", "whatsapp", "navegador", "mcp", ".aws", "celular", "delegados"):
    print("VAZIA", d, dentro(f"ls -A /a0/usr/{d} 2>/dev/null | wc -l"))
print("GRAVAR", dentro("touch /a0/usr/teste_hermes_ro 2>&1 | tail -1 || true") or "gravou!")
print("ENSAIO", dentro("printenv AGENTEPESSOAL_ENSAIO"))
'''

FERRAMENTAS = COMUM + r'''
d = api("/v1/toolsets")
for t in d.get("data", []):
    if t.get("enabled"):
        print(t.get("name"), [x if isinstance(x, str) else x.get("name") for x in (t.get("tools") or [])])
'''

PERGUNTAR = COMUM + r'''
texto, sessao = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
print(perguntar(texto, sessao)[-5000:])
'''

RUN = COMUM + r'''
texto, sessao, escolha = sys.argv[1], sys.argv[2], sys.argv[3]
corpo = {"input": texto}
if sessao:
    corpo["session_id"] = sessao
r = api("/v1/runs", corpo)
run = r.get("run_id") or r.get("id")
print("RUN", run)
fim = time.time() + 900
visto = set()
while time.time() < fim:
    st = api(f"/v1/runs/{run}")
    estado = st.get("status")
    if estado == "waiting_for_approval" and run not in visto:
        visto.add(run)
        ap = st.get("approval") or {}
        print("APROVACAO", json.dumps(ap, ensure_ascii=False)[:600])
        if escolha:
            corpo_ap = {"choice": escolha}
            rid = ap.get("request_id") or (ap.get("data") or {}).get("request_id")
            if rid:
                corpo_ap["request_id"] = rid
            print("RESPOSTA", api(f"/v1/runs/{run}/approval", corpo_ap))
    if estado in ("completed", "failed", "cancelled", "stopped", "succeeded"):
        print("ESTADO", estado)
        print("SAIDA", json.dumps(st, ensure_ascii=False)[-3000:])
        break
    time.sleep(3)
'''


def rodar(script: str, *args: str) -> None:
    b64 = base64.b64encode(script.encode()).decode()
    argv = " ".join("'" + a.replace("'", "'\\''") + "'" for a in args)
    cmd = (f"touch /var/lib/agentepessoal/last-activity; echo {b64} | base64 -d > /tmp/hermes_ao_vivo.py && "
           f"timeout 1200 python3 /tmp/hermes_ao_vivo.py {argv}; rm -f /tmp/hermes_ao_vivo.py")
    out = subprocess.run([sys.executable, str(AQUI / "vmcmd.py"), cmd], capture_output=True, text=True).stdout
    print(out.strip())


def main(argv: list) -> int:
    if not argv:
        print(__doc__)
        return 2
    acao = argv[0]
    sessao = argv[argv.index("--sessao") + 1] if "--sessao" in argv else ""
    escolha = argv[argv.index("--aprovar") + 1] if "--aprovar" in argv else ""
    if acao == "cofre":
        rodar(COFRE)
    elif acao == "travas":
        rodar(TRAVAS)
    elif acao == "ferramentas":
        rodar(FERRAMENTAS)
    elif acao == "perguntar":
        rodar(PERGUNTAR, argv[1], sessao)
    elif acao == "run":
        rodar(RUN, argv[1], sessao, escolha)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

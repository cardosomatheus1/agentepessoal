"""Tests of the delegates' boxes (infra/vm/caixa_delegados.py and the runners) with no Docker: every flag and mount of
the box, which files may go in and come out, the relay's routes, the firewall order, the engines' configs. Run from
the repository root: python3 infra/vm/tests/test_delegados.py"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
falhas = []


def carregar(nome, caminho):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def checa(cond, msg):
    if not cond:
        falhas.append(msg)


d = carregar("caixa_delegados_teste", RAIZ / "infra" / "vm" / "caixa_delegados.py")
oc = carregar("delegado_openclaw_teste", RAIZ / "infra" / "vm" / "delegado_openclaw.py")

# ---- the box: nothing of the agent inside, no privileges, limits, its own network
for motor in d.MOTORES:
    a = d.argumentos_run("d20261020-180000-abc234", motor, Path("/opt/delegados/tarefas/d20261020-180000-abc234"),
                         "172.30.0.1")
    linha = " ".join(a)
    for preciso in ("--cap-drop ALL", "--security-opt no-new-privileges", "--user 1000:1000", "--network delegados",
                    "--memory 3g", "--memory-swap 3g", "--pids-limit 512", "--cpus 2", "--restart no", "--dns 1.1.1.1",
                    "--label delegado=d20261020-180000-abc234", d.IMAGEM):
        checa(preciso in linha, f"{motor}: caixa sem {preciso!r}")
    checa("--privileged" not in linha and "docker.sock" not in linha and "--network host" not in linha,
          f"{motor}: caixa privilegiada ou com o docker do host")
    volumes = [a[i + 1] for i, x in enumerate(a) if x in ("-v", "--volume", "--mount")]
    for v in volumes:
        origem, destino = v.split(":")[0], v.split(":")[1]
        so_leitura = v.endswith(":ro")
        gravavel_ok = origem.startswith("/opt/delegados/tarefas/d20261020-180000-abc234")
        checa(so_leitura or gravavel_ok, f"{motor}: volume gravável fora da pasta da tarefa: {v}")
        checa(not origem.startswith("/opt/a0/usr/") or origem.startswith("/opt/a0/usr/workdir/agentes/") and so_leitura,
              f"{motor}: só a instalação dos agentes, e só para leitura, vem do /a0/usr: {v}")
        for proibido in ("cofre", "mcp", "/opt/a0/usr/caixa", "/delegados/segredo", "settings.json", "state/openclaw",
                         "/opt/a0/usr:"):
            checa(proibido not in v, f"{motor}: volume proibido {proibido!r}: {v}")
    checa(not any("state/hermes/installs:" in v and "/opt/a0/" in v for v in volumes),
          f"{motor}: o depósito do Hermes vem da camada da tarefa, nunca do original")
    ambiente = [a[i + 1] for i, x in enumerate(a) if x == "-e"]
    checa(not any(k.split("=")[0] in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
                  for k in ambiente), f"{motor}: chave no ambiente")
    checa(f"SEARXNG_URL=http://172.30.0.1:{d.RELAY_PORTA}/searxng" in ambiente, f"{motor}: busca pelo repasse")
    checa(any(e.startswith("PATH=/trabalho/bin:") and "agent-browser" in e for e in ambiente),
          f"{motor}: buscar e agent-browser no PATH")
hermes = " ".join(d.argumentos_run("d20261020-180000-abc234", "hermes", Path("/t"), "172.30.0.1"))
checa("/t/camadas/installs/m:/a0/usr/workdir/agentes/state/hermes/installs" in hermes, "Hermes: depósito em camada")
checa("/t/camadas/runtime/m:/a0/usr/workdir/agentes/runtime/hermes" in hermes, "Hermes: runtime em camada")
checa(hermes.endswith("/caixa/delegado_hermes.py"), "Hermes roda o executor dele")
checa(" ".join(d.argumentos_run("d20261020-180000-abc234", "openclaw", Path("/t"), "172.30.0.1")).endswith(
    "python3 -I /caixa/delegado_openclaw.py"), "OpenClaw roda o executor dele")

atalhos = d.atalhos()
checa(atalhos["agent-browser"].startswith("#!/bin/sh") and d.AGENT_BROWSER in atalhos["agent-browser"],
      "atalho agent-browser aponta para o binário do runtime")
checa("BUSCAR_URL" in atalhos["buscar"], "atalho buscar usa o repasse")

# ---- config: the relay, no secret, the rules of the box told to the delegate
cfg = d.configuracao("hermes", 10, "172.30.0.1")
checa(cfg["base_url"] == f"http://172.30.0.1:{d.RELAY_PORTA}/openai/v1", "modelo só pelo repasse")
checa(cfg["segundos"] == 600, "minutos viram segundos")
texto = json.dumps(cfg)
checa("8787" not in texto and "key" not in texto.lower(), "configuração sem proxy direto nem chave")
for termo in ("/trabalho/saida/", "agent-browser", "buscar", "Não entre em contas", "CAPTCHA"):
    checa(termo in cfg["sistema"], f"o delegado é avisado de {termo!r}")

# ---- the relay: model and search only
for metodo, caminho, rota in (("POST", "/openai/v1/responses", "modelo"), ("POST", "/openai/v1/chat/completions", "modelo"),
                              ("GET", "/openai/v1/models", "modelo"), ("GET", "/searxng/search?q=x&format=json", "searxng"),
                              ("GET", "/buscar?q=x", "buscar"), ("POST", "/arquivos/presign", ""),
                              ("POST", "/arquivos/gcp_token", ""), ("GET", "/health", ""), ("POST", "/bedrock/x", ""),
                              ("GET", "/openai/v1/responses", ""), ("POST", "/openai/v1/../../arquivos/presign", ""),
                              ("POST", "/typesafe/x", "")):
    checa(d.rota_permitida(metodo, caminho) == rota, f"repasse {metodo} {caminho} -> {rota!r}")
chamado = []
d.docker = lambda *a, **k: chamado.append(a) or type("R", (), {"returncode": 0, "stdout": b'{"results": []}'})()
d.buscar_searxng({"q": "a; rm -rf / & b", "format": "json"})
checa(chamado[0][:4] == ("exec", "agent-zero", "curl", "-s") and chamado[0][-1].startswith(
    "http://127.0.0.1:55510/search?q=a%3B+rm+-rf+%2F+%26+b"), f"busca com consulta codificada, comando fixo: {chamado}")
r = d.resumir_busca({"results": [{"title": "T", "url": "https://x", "content": "c" * 900}] * 20})
checa(len(r["resultados"]) == 12 and len(r["resultados"][0]["trecho"]) == 400, "busca resumida")

# ---- firewall: ACCEPT of the relay above the DROP; private ranges and metadata out
regras = d.regras_isolamento("172.30.0.0/16")
checa(regras[0] == ["INPUT", "-s", "172.30.0.0/16", "-p", "tcp", "--dport", str(d.RELAY_PORTA), "-j", "ACCEPT"],
      "repasse aceito")
checa(["INPUT", "-s", "172.30.0.0/16", "-j", "DROP"] in regras, "resto do host bloqueado")
for faixa in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10"):
    checa(["DOCKER-USER", "-s", "172.30.0.0/16", "-d", faixa, "-j", "DROP"] in regras, f"faixa {faixa} bloqueada")
boa = ["-A INPUT -s 172.30.0.0/16 -p tcp -m tcp --dport 8792 -j ACCEPT", "-A INPUT -s 172.30.0.0/16 -j DROP"]
checa(d.ordem_ok(boa, "172.30.0.0/16"), "ordem certa reconhecida")
checa(not d.ordem_ok(list(reversed(boa)), "172.30.0.0/16"), "DROP antes do ACCEPT é recusado")
checa(not d.ordem_ok(boa[1:], "172.30.0.0/16"), "sem ACCEPT é recusado")
fw = (RAIZ / "infra" / "vm" / "firewall.sh").read_text()
checa("network inspect delegados" in fw and "--dport 8792 -j ACCEPT" in fw, "firewall.sh refaz as regras no boot")
checa(fw.index('regra=(INPUT -s "$DELEGADOS" -j DROP)') < fw.index('iptables -I "${aceita[@]}"'),
      "firewall.sh insere o ACCEPT depois do DROP (fica acima)")
checa("8787 8788 8789 8790 8791 8792" in fw, "o celular não alcança o serviço nem o repasse")

# ---- files in: only the agent's work folders, never secrets or links
with tempfile.TemporaryDirectory() as tmp:
    usr = Path(tmp) / "usr"
    d.USR_HOST = usr
    for rel in ("workdir/dados.csv", "uploads/foto.png", "workdir/agentes/state/hermes/config.yaml", "cofre/matheus.json",
                "workdir/sub/.env", "mcp/google/credenciais/a.json", "settings.json", "projects/p/credenciais.json"):
        (usr / rel).parent.mkdir(parents=True, exist_ok=True)
        (usr / rel).write_text("x")
    os.symlink(usr / "cofre" / "matheus.json", usr / "workdir" / "atalho.json")
    checa(d.origem_permitida("/a0/usr/workdir/dados.csv") == usr / "workdir/dados.csv", "arquivo de trabalho entra")
    checa(d.origem_permitida("/a0/usr/uploads/foto.png") == usr / "uploads/foto.png", "upload entra")
    for ruim in ("/a0/usr/workdir/agentes/state/hermes/config.yaml", "/a0/usr/cofre/matheus.json", "/a0/usr/workdir/sub/.env",
                 "/a0/usr/mcp/google/credenciais/a.json", "/a0/usr/settings.json", "/a0/usr/workdir/atalho.json",
                 "/a0/usr/workdir/../cofre/matheus.json", "/etc/passwd", "/a0/usr/projects/p/credenciais.json",
                 "/a0/usr/workdir/nao_existe.csv"):
        try:
            d.origem_permitida(ruim)
            falhas.append(f"arquivo proibido entrou: {ruim}")
        except d.Recusa:
            pass

    # files out: regular files of saida only, into the agent's folder
    pasta = Path(tmp) / "tarefa"
    (pasta / "saida" / "sub").mkdir(parents=True)
    (pasta / "saida" / "relatorio.md").write_text("ok")
    (pasta / "saida" / "sub" / "g r a f.png").write_bytes(b"png")
    os.symlink("/etc/passwd", pasta / "saida" / "senha")
    destino = usr / "workdir" / "delegados" / "d1"
    feitos = d.coletar_saida(pasta, destino)
    nomes = sorted(Path(f["arquivo"]).name for f in feitos)
    checa(nomes == ["g_r_a_f.png", "relatorio.md"], f"saída: só arquivos comuns, nomes seguros ({nomes})")
    checa(all(f["arquivo"].startswith("/a0/usr/workdir/delegados/d1/") for f in feitos), "saída na pasta do agente")
    checa(not (destino / "senha").exists(), "link não sai da caixa")

# ---- tasks: refusals before any box is made
for dados, motivo in (({"motor": "claude", "tarefa": "x"}, "motor"), ({"motor": "hermes", "tarefa": " "}, "vazia"),
                      ({"motor": "hermes", "tarefa": "use AKIAABCDEFGHIJKLMNOP"}, "chave AWS"),
                      ({"motor": "hermes", "tarefa": "token ghp_" + "a" * 36}, "token GitHub"),
                      ({"motor": "openclaw", "tarefa": "x" * (d.TAREFA_MAX + 1)}, "longa"),
                      ({"motor": "hermes", "tarefa": "ok", "arquivos": ["/a0/usr/cofre/x"]}, "arquivo do cofre")):
    try:
        d.iniciar(dados)
        falhas.append(f"tarefa aceita sem poder ({motivo})")
    except d.Recusa:
        pass
for ruim in ("../x", "d1", "d20261020-180000-ABC234; rm -rf /", ""):
    try:
        d.conferir_id(ruim)
        falhas.append(f"id aceito: {ruim!r}")
    except d.Recusa:
        pass
checa(d._ID.match(d.novo_id()), "id novo no formato")

# ---- OpenClaw's config and result
c = oc.configuracao({"base_url": "http://172.30.0.1:8792/openai/v1", "modelo": "m"})
negadas = set(c["tools"]["deny"])
checa({"group:messaging", "group:sessions", "cron", "gateway", "nodes"} <= negadas, "OpenClaw sem mensagens/sessões/agenda")
checa(c["models"]["providers"]["relay"]["baseUrl"].endswith(":8792/openai/v1") and c["models"]["mode"] == "replace",
      "OpenClaw só com o repasse como provedor")
checa(c["plugins"]["enabled"] is False and c["env"]["shellEnv"]["enabled"] is False, "OpenClaw sem plugins nem env do shell")
checa(c["tools"]["fs"]["workspaceOnly"] is True and c["agents"]["defaults"]["workspace"] == "/trabalho", "arquivos só em /trabalho")
bom = oc.resultado(json.dumps({"ok": True, "status": "ok", "final": " Feito ", "model": "m",
                               "toolSummary": {"tools": ["exec", "web_fetch"], "calls": 4, "failures": 0}}), "m")
checa(bom["ok"] and bom["resposta"] == "Feito" and bom["ferramentas"] == ["exec", "web_fetch"], f"resultado OpenClaw: {bom}")
ruim = oc.resultado(json.dumps({"ok": False, "status": "error", "final": ""}), "m")
checa(not ruim["ok"] and ruim["erro"] == "error", "falha do OpenClaw")
checa(not oc.resultado("nada", "m")["ok"], "saída sem JSON")

# ---- deploy and boot
imp = (RAIZ / "infra" / "operador" / "implantar.py").read_text()
for f in ("caixa_delegados.py", "delegado_hermes.py", "delegado_openclaw.py"):
    checa(f'"{f}"' in imp, f"implantar.py conhece {f}")
checa((RAIZ / "infra" / "vm" / "unidades" / "agentepessoal-delegados.service").exists(), "unidade do serviço")
setup = (RAIZ / "infra" / "vm" / "setup.sh").read_text()
checa("agentepessoal-delegados.service" in setup and "caixa_delegados.py" in setup, "setup.sh instala o serviço")
herm = (RAIZ / "infra" / "vm" / "delegado_hermes.py").read_text()
checa('TOOLSETS = ["terminal", "file", "web", "browser", "vision", "todo"]' in herm, "Hermes com as ferramentas de trabalho")
checa("api_key=\"relay-not-a-credential\"" in herm and "skip_memory=True" in herm, "Hermes sem chave e sem memória própria")

if falhas:
    print("FALHAS:")
    for f in falhas:
        print(" -", f)
    sys.exit(1)
print("test_delegados: ok")

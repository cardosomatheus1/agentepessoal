#!/bin/bash
# A virada do agente para o Hermes (migração, fase 8) e a volta ao A0, um comando cada (root no host da VM):
#   virada.sh virar  [motivo]   o Hermes passa a ser o agente de todos (Matheus, convidados); o A0 fica PARADO, intacto
#   virada.sh voltar [motivo]   tudo de volta ao A0 em minutos; o Hermes volta ao ensaio (só leitura, nada ao celular)
#   virada.sh estado
# Pelo operador: python3 infra/operador/virada.py virar|voltar|estado.
#
# virar: (1) a chave da ponte (/var/lib/agentepessoal/destino.json) "padrao": "hermes" para todo login; (2) o A0 para
# (docker stop, sem reinício automático; os dados e as rotinas dele ficam como estão: parado, nada dele roda), e os
# serviços que só existem dentro dele (conector Google do A0, adb do A0) param; (3) o OpenCode 2 + Ponytail sai do
# container do A0 para o host (revisar_opencode.py roda lá com o A0 parado); (4) subir.sh no modo virada (dados
# graváveis, relógio, rede, navegador no perfil de verdade, Google com as permissões do A0, portal gravável, celular,
# um Hermes por convidado); (5) liga no cron do Hermes as rotinas que estavam ligadas no A0 (as desligadas seguem
# desligadas): cada rotina roda num lado só; (6) o túnel do portal (o link do agente passa a abrir o portal).
# voltar: o inverso, na ordem que não deixa nada rodar duas vezes: pausa as rotinas do Hermes, chave "padrao": "a0",
# subir.sh no ensaio, religa o A0 e os serviços dele. Os dados vivos são os mesmos dos dois lados (nada a copiar).
set -euo pipefail
ACAO="${1:-estado}"; MOTIVO="${2:-operador: $ACAO}"
FONTE="${HERMES_FONTE:-/opt/hermes/fonte/hermes}"  # setup.sh numa VM nova passa a do pacote
DESTINO=/var/lib/agentepessoal/destino.json
LIGADAS=/opt/hermes/data/agentepessoal/virada_ligadas.json
HPY=(docker exec -i -u 10000 -e HOME=/opt/data -w /opt/hermes hermes /opt/hermes/.venv/bin/python3)

chave() {  # $1 = a0|hermes: o padrão da ponte, com o histórico (o login de teste fica como está)
  python3 - "$1" "$MOTIVO" <<'PY'
import json, os, sys, tempfile, time
caminho = "/var/lib/agentepessoal/destino.json"
try:
    d = json.load(open(caminho))
except (OSError, ValueError):
    d = {}
d = d if isinstance(d, dict) else {}
d["padrao"] = sys.argv[1]
d.setdefault("logins", {})
d.setdefault("historico", []).append({"em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "login": "*",
                                      "para": sys.argv[1], "por": sys.argv[2]})
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(caminho), prefix=".destino.")
with os.fdopen(fd, "w") as f:
    json.dump(d, f, ensure_ascii=False, indent=1)
os.chmod(tmp, 0o644)
os.replace(tmp, caminho)
print("CHAVE", sys.argv[1])
PY
}

rotinas_hermes() {  # $1 = ligar|pausar
  "${HPY[@]}" - "$1" <<'PY'
import json, sys
sys.path.insert(0, "/opt/hermes")
from cron import jobs
mapa = json.load(open("/opt/data/agentepessoal/rotinas.json"))
feitas = []
if sys.argv[1] == "ligar":
    for k, v in mapa.items():
        if v.get("ligada_no_a0") and jobs.get_job(k):
            jobs.resume_job(k)
            feitas.append(k)
    json.dump({"ligadas": feitas}, open("/opt/data/agentepessoal/virada_ligadas.json", "w"))
else:
    for j in jobs.list_jobs(include_disabled=True):
        if j.get("enabled", True) and j.get("state") != "paused":
            jobs.pause_job(j["id"], reason="volta ao A0 (virada.sh voltar)")
            feitas.append(j["id"])
print("ROTINAS", sys.argv[1], len(feitas))
PY
}

opencode_no_host() {  # o revisor sai do container do A0 (mesmos caminhos de /root no host); uma vez
  [ -x /root/.opencode/bin/opencode2 ] && { echo "OPENCODE_HOST ja"; return 0; }
  docker cp agent-zero:/root/.opencode /root/.opencode
  mkdir -p /root/.config /root/.aws
  docker cp agent-zero:/root/.config/opencode /root/.config/opencode
  grep -q "profile bedrock-agentzero" /root/.aws/config 2>/dev/null \
    || printf '[profile bedrock-agentzero]\nregion = us-east-1\noutput = json\n' >> /root/.aws/config
  [ -e /a0/usr ] || { mkdir -p /a0 && ln -s /opt/a0/usr /a0/usr; }
  echo "OPENCODE_HOST copiado"
}

case "$ACAO" in
virar)
  [ -f "$FONTE/subir.sh" ] || { echo "VIRADA_SEM_FONTE: implante o Hermes (implantar.py --hermes) antes"; exit 1; }
  opencode_no_host
  chave hermes
  docker update --restart no agent-zero >/dev/null 2>&1 || true
  docker stop -t 60 agent-zero >/dev/null 2>&1 || true
  systemctl disable --now agentepessoal-google-mcp.service agentepessoal-agent-tools.service >/dev/null 2>&1 || true
  if ! bash "$FONTE/subir.sh" > /var/log/agentepessoal-virada.log 2>&1; then
    tail -30 /var/log/agentepessoal-virada.log
    echo "VIRADA_FALHOU: o Hermes não subiu no modo virada. Para voltar: bash /opt/hermes/virada.sh voltar"; exit 1
  fi
  grep -E "^(HERMES_OK|CONVIDADO_OK|PORTAL_OK)" /var/log/agentepessoal-virada.log || true
  rotinas_hermes ligar
  systemctl enable -q agentepessoal-portal-tunnel.service 2>/dev/null && systemctl restart agentepessoal-portal-tunnel.service || true
  systemctl restart agentepessoal-url.service || true
  echo "VIRADA_OK $(date -u +%FT%TZ)"
  ;;
voltar)
  if [ "$(docker inspect -f '{{.State.Running}}' hermes 2>/dev/null)" = true ]; then
    rotinas_hermes pausar
  fi
  chave a0
  if [ -f "$FONTE/subir.sh" ]; then
    bash "$FONTE/subir.sh" > /var/log/agentepessoal-volta.log 2>&1 || {
      tail -20 /var/log/agentepessoal-volta.log; echo "VOLTA: o Hermes não voltou ao ensaio; parando o Hermes";
      docker stop hermes >/dev/null 2>&1 || true; }
  fi
  systemctl disable --now agentepessoal-portal-tunnel.service >/dev/null 2>&1 || true
  docker update --restart unless-stopped agent-zero >/dev/null
  docker start agent-zero >/dev/null
  systemctl enable -q agentepessoal-google-mcp.service agentepessoal-agent-tools.service 2>/dev/null || true
  systemctl restart --no-block agentepessoal-google-mcp.service || true
  systemctl start agentepessoal-agent-tools.service || true
  systemctl restart agentepessoal-url.service || true
  echo "VOLTA_OK $(date -u +%FT%TZ)"
  ;;
estado)
  python3 -c 'import json;d=json.load(open("/var/lib/agentepessoal/destino.json"));print("CHAVE", d.get("padrao"), d.get("logins"))' 2>/dev/null || echo "CHAVE a0 (sem arquivo)"
  echo "A0 $(docker inspect -f '{{.State.Status}}' agent-zero 2>/dev/null || echo ausente)"
  for c in hermes hermes-navegador hermes-mcp portal $(docker ps -a --format '{{.Names}}' | grep -E '^hermes-(ilia|will|[a-z0-9_]+)$' | grep -vE 'navegador|mcp|sombra' || true); do
    echo "$c $(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo ausente)"
  done
  [ "$(docker inspect -f '{{.State.Running}}' hermes 2>/dev/null)" = true ] && "${HPY[@]}" - <<'PY' || true
import sys
sys.path.insert(0, "/opt/hermes")
from cron import jobs
todas = jobs.list_jobs(include_disabled=True)
ligadas = [j for j in todas if j.get("enabled", True) and j.get("state") != "paused"]
print("ROTINAS_HERMES ligadas", len(ligadas), "de", len(todas))
PY
  ;;
*) echo "uso: virada.sh virar|voltar|estado [motivo]"; exit 2 ;;
esac

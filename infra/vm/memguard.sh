#!/bin/bash
# Last line of defense against the VM freezing for lack of memory (10/10: the agent's browser reached 11.8 GB, the
# VM thrashed for 30 min with SSM and the tunnel down, and had to be rebooted). Runs every minute: when free memory
# stays below LIMITE_MB for 3 checks in a row, restarts the container using the most memory (the agent or the virtual
# phone; data and logins are on disk), at most MAX_REINICIOS_HORA times an hour, and tells the owner on Telegram.
# 12/10 review: it always restarted the agent (even when the phone was the culprit), could loop, and its header
# promised a Telegram notice the code never sent. The in-agent cleanup (plugin "limpeza") should normally keep memory
# far from this line.
set -u
LIMITE_MB="${LIMITE_MB:-700}"
MAX_REINICIOS_HORA="${MAX_REINICIOS_HORA:-2}"
ESTADO=/var/lib/agentepessoal/memguard-baixas
REINICIOS=/var/lib/agentepessoal/memguard-reinicios  # one epoch per line
mkdir -p /var/lib/agentepessoal

avisar() {  # Telegram through the host bridge (urgent: also in quiet hours); never stops the guard
  local chave
  chave=$(cat /opt/a0/usr/whatsapp/.chave 2>/dev/null) || return 0
  python3 -c 'import json, sys; print(json.dumps({"usuario": "matheus", "texto": sys.argv[1], "tipo": "urgente"}))' "$1" |
    curl -s -m 15 -X POST http://127.0.0.1:8789/enviar -H "X-Chave: $chave" -H "Content-Type: application/json" \
      --data-binary @- >/dev/null 2>&1 || true
}

# The web UI can hang during startup after "Preload completed" (11/10: container up, port 80 never opened, phone
# and tunnel dead). When the container has been up 10+ min and the UI fails 5 checks in a row, restart only run_ui.
UI=/var/lib/agentepessoal/memguard-ui
desde=$(docker inspect -f '{{.State.StartedAt}}' agent-zero 2>/dev/null)
# 23/10 (virada ao Hermes): o A0 fica parado 7 dias para a volta; parado, não se mexe nele (nem na interface)
[ "$(docker inspect -f '{{.State.Running}}' agent-zero 2>/dev/null)" = true ] || desde=""
if [ -n "$desde" ] && [ $(( $(date +%s) - $(date -d "$desde" +%s) )) -ge 600 ]; then
  if curl -s -o /dev/null -m 10 http://127.0.0.1:50080/login; then
    echo 0 > "$UI"
  else
    u=$(( $(cat "$UI" 2>/dev/null || echo 0) + 1 )); echo "$u" > "$UI"
    if [ "$u" -ge 5 ]; then
      echo 0 > "$UI"
      logger -t agentepessoal "memguard: web UI down for 5 min; restarting run_ui"
      docker exec agent-zero supervisorctl restart run_ui
      echo "$(date -u +%FT%TZ) reiniciou run_ui (interface sem resposta)" >> /var/lib/agentepessoal/memguard.log
    fi
  fi
fi

livre=$(awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo)
if [ "$livre" -ge "$LIMITE_MB" ]; then
  echo 0 > "$ESTADO"; exit 0
fi
n=$(( $(cat "$ESTADO" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$ESTADO"
logger -t agentepessoal "memguard: ${livre} MB free (check $n/3)"
[ "$n" -lt 3 ] && exit 0
echo 0 > "$ESTADO"
# the container using the most memory is the one restarted: the agent (A0, or after the cutover the Hermes and its
# browsers, the guests' too), or the phone; `docker stats` lists only running ones
culpado=$(docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' 2>/dev/null | python3 -c '
import re, sys
unid = {"B": 1, "KiB": 2**10, "MiB": 2**20, "GiB": 2**30, "kB": 1e3, "MB": 1e6, "GB": 1e9}
melhor, uso = "", -1.0
for linha in sys.stdin:
    nome, _, resto = linha.strip().partition(" ")
    m = re.match(r"([\d.]+)\s*([A-Za-z]+)", resto)
    candidato = nome in ("agent-zero", "android") or re.fullmatch(r"hermes(-navegador)?(-[a-z0-9_-]+)?", nome)
    if candidato and nome != "hermes-mcp" and m and float(m.group(1)) * unid.get(m.group(2), 1) > uso:
        melhor, uso = nome, float(m.group(1)) * unid.get(m.group(2), 1)
print(melhor)')
[ -n "$culpado" ] || { logger -t agentepessoal "memguard: ${livre} MB free and no agent container running"; exit 0; }
agora=$(date +%s)
recentes=$(awk -v c=$((agora - 3600)) '$1 > c' "$REINICIOS" 2>/dev/null | wc -l)
if [ "$recentes" -ge "$MAX_REINICIOS_HORA" ]; then
  logger -t agentepessoal "memguard: ${livre} MB free again after ${recentes} restarts this hour; not restarting (no loop)"
  echo "$(date -u +%FT%TZ) memória baixa (${livre} MB) de novo; sem reiniciar (${recentes} na última hora)" >> /var/lib/agentepessoal/memguard.log
  avisar "⚠️ Servidor do agente com pouca memória de novo (${livre} MB livres). Já reiniciei ${recentes}× na última hora; não reinicio mais agora para não entrar em ciclo. Quem mais usa memória: ${culpado}."
  exit 0
fi
echo "$agora" >> "$REINICIOS"
logger -t agentepessoal "memguard: ${livre} MB free for 3 min; restarting ${culpado}"
docker restart -t 20 "$culpado"
echo "$(date -u +%FT%TZ) reiniciou ${culpado} com ${livre} MB livres" >> /var/lib/agentepessoal/memguard.log
avisar "🔁 Servidor do agente quase sem memória (${livre} MB livres por 3 min): reiniciei ${culpado}, o que mais usava memória. Os dados ficam no disco e as rodadas voltam sozinhas."

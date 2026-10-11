#!/bin/bash
# Last line of defense against the VM freezing for lack of memory (10/10: the agent's browser reached 11.8 GB, the
# VM thrashed for 30 min with SSM and the tunnel down, and had to be rebooted). Runs every minute: when free memory
# stays below LIMITE_MB for 3 checks in a row, restarts only the Agent Zero container (data and logins are on disk),
# logs it and tells the owner on Telegram once the bridge answers. The in-agent cleanup (plugin "limpeza") should
# normally keep memory far from this line.
set -u
LIMITE_MB="${LIMITE_MB:-700}"
ESTADO=/var/lib/agentepessoal/memguard-baixas
mkdir -p /var/lib/agentepessoal

# The web UI can hang during startup after "Preload completed" (11/10: container up, port 80 never opened, phone
# and tunnel dead). When the container has been up 10+ min and the UI fails 5 checks in a row, restart only run_ui.
UI=/var/lib/agentepessoal/memguard-ui
desde=$(docker inspect -f '{{.State.StartedAt}}' agent-zero 2>/dev/null)
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
logger -t agentepessoal "memguard: ${livre} MB free for 3 min; restarting the agent-zero container"
docker restart -t 20 agent-zero
echo "$(date -u +%FT%TZ) reiniciou agent-zero com ${livre} MB livres" >> /var/lib/agentepessoal/memguard.log

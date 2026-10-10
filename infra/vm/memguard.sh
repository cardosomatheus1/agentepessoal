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

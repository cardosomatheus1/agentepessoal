#!/bin/bash
# Hibernates the VM after IDLE_MINUTES without use. "Use" means any of:
#  - a model call through the Bedrock proxy (agent thinking/working),
#  - a chat file written by Agent Zero (messages, tool output),
#  - someone watching the phone screen (ws-scrcpy connection),
#  - sustained CPU load (a long command still running).
set -u
IDLE_MINUTES="${IDLE_MINUTES:-30}"
ACTIVITY_FILE=/var/lib/agentepessoal/last-activity
CHATS_DIR=/opt/a0/usr/chats

# Time since boot or since the last resume from hibernation.
since_up=$(( $(date +%s) - $(stat -c %Y /var/lib/agentepessoal/resumed 2>/dev/null || echo 0) ))
uptime_s=$(cut -d. -f1 /proc/uptime)
[ "$since_up" -lt "$uptime_s" ] && uptime_s=$since_up
[ "$uptime_s" -lt $((IDLE_MINUTES * 60)) ] && exit 0

if [ -n "$(find "$ACTIVITY_FILE" "$CHATS_DIR" -newermt "-${IDLE_MINUTES} minutes" -print -quit 2>/dev/null)" ]; then
  exit 0
fi

if [ "$(ss -Htn state established '( sport = :8000 )' | wc -l)" -gt 0 ]; then
  touch "$ACTIVITY_FILE"
  exit 0
fi

load5=$(awk '{print $2}' /proc/loadavg)
cpus=$(nproc)
if awk -v l="$load5" -v c="$cpus" 'BEGIN { exit !(l >= c * 0.5) }'; then
  exit 0
fi

# a scheduled task is about to run: stay up rather than sleep and wake again
/opt/agentepessoal/venv/bin/python /opt/agentepessoal/proximo_despertar.py --perto 15
[ $? -eq 3 ] && exit 0

logger -t agentepessoal "idle for ${IDLE_MINUTES} min (load5=${load5}); hibernating"
exec /opt/agentepessoal/hibernate.sh

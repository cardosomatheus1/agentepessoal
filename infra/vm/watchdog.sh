#!/bin/bash
# Stops the VM after IDLE_MINUTES without use. "Use" means any of:
#  - a model call through the Bedrock proxy (agent thinking/working),
#  - a chat file written by Agent Zero (messages, tool output),
#  - sustained CPU load (a long command still running).
set -u
IDLE_MINUTES="${IDLE_MINUTES:-30}"
ACTIVITY_FILE=/var/lib/agentepessoal/last-activity
CHATS_DIR=/opt/a0/usr/chats

uptime_s=$(cut -d. -f1 /proc/uptime)
[ "$uptime_s" -lt $((IDLE_MINUTES * 60)) ] && exit 0

if [ -n "$(find "$ACTIVITY_FILE" "$CHATS_DIR" -newermt "-${IDLE_MINUTES} minutes" -print -quit 2>/dev/null)" ]; then
  exit 0
fi

load5=$(awk '{print $2}' /proc/loadavg)
if awk -v l="$load5" 'BEGIN { exit !(l >= 0.6) }'; then
  exit 0
fi

logger -t agentepessoal "idle for ${IDLE_MINUTES} min (load5=${load5}); stopping instance"
/opt/agentepessoal/backup.sh || true
/opt/agentepessoal/venv/bin/python - <<'EOF' || true
import boto3
boto3.client("ssm", region_name="us-east-1").put_parameter(
    Name="/agentepessoal/agent-url", Value="stopped", Type="String", Overwrite=True)
EOF
shutdown -h now

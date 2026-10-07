#!/bin/bash
# First-boot setup for the agentepessoal VM (Ubuntu 24.04). Rendered by infra/deploy.py.
set -euxo pipefail
exec > >(tee -a /var/log/agentepessoal-setup.log) 2>&1

export DEBIAN_FRONTEND=noninteractive
REGION=us-east-1
BUCKET={{BUCKET}}

# Admin access is through SSM Session Manager; no SSH port is opened.
systemctl disable --now ssh.socket ssh.service || true

apt-get update -y
apt-get install -y docker.io python3-venv unzip curl
systemctl enable --now docker

# AWS CLI v2 (S3 backups)
curl -sSfL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp && /tmp/aws/install && rm -rf /tmp/aws /tmp/awscliv2.zip

mkdir -p /opt/agentepessoal /var/lib/agentepessoal /opt/a0/usr
python3 -m venv /opt/agentepessoal/venv
/opt/agentepessoal/venv/bin/pip install --quiet boto3 aws-bedrock-token-generator

echo '{{PROXY_PY_B64}}' | base64 -d > /opt/agentepessoal/bedrock_proxy.py
echo '{{REPORT_PY_B64}}' | base64 -d > /opt/agentepessoal/report_url.py
echo '{{WATCHDOG_B64}}' | base64 -d > /opt/agentepessoal/watchdog.sh
echo '{{BACKUP_B64}}' | base64 -d > /opt/agentepessoal/backup.sh
chmod +x /opt/agentepessoal/watchdog.sh /opt/agentepessoal/backup.sh
echo "BACKUP_BUCKET=${BUCKET}" > /etc/agentepessoal.env

# Restore earlier data (chats, memory, projects, uploads) when the VM is rebuilt.
/usr/local/bin/aws s3 sync "s3://${BUCKET}/usr" /opt/a0/usr --only-show-errors || true

# Agent Zero config: model presets (through the local Bedrock proxy) and code execution.
mkdir -p /opt/a0/usr/plugins/_model_config /opt/a0/usr/plugins/_code_execution
echo '{{PRESETS_B64}}' | base64 -d > /opt/a0/usr/plugins/_model_config/presets.yaml
echo '{{CODEEXEC_B64}}' | base64 -d > /opt/a0/usr/plugins/_code_execution/config.json

# "Carreira" project: profile, CV folder and application log the agent keeps up to date.
if [ ! -d /opt/a0/usr/projects/carreira ]; then
  mkdir -p /opt/a0/usr/projects/carreira
  echo '{{PROJECT_TGZ_B64}}' | base64 -d | tar -xz -C /opt/a0/usr/projects/carreira
fi

# Single user: no Agent Zero login. The VM has no open ports; the only way in is the
# random tunnel URL, which is revealed only by the key-protected control page.
# Agent Zero always allows its own tunnel origin; localhost covers local checks.
touch /opt/a0/usr/.env
sed -i -E '/^(AUTH_LOGIN|AUTH_PASSWORD|API_KEY_OTHER|ALLOWED_ORIGINS)=/d' /opt/a0/usr/.env
{
  echo "API_KEY_OTHER=local-proxy"
  echo "ALLOWED_ORIGINS=*://localhost,*://localhost:*,*://127.0.0.1,*://127.0.0.1:*"
} >> /opt/a0/usr/.env
chmod 600 /opt/a0/usr/.env

cat > /etc/systemd/system/agentepessoal-proxy.service <<'UNIT'
[Unit]
Description=Bedrock bearer-token proxy for Agent Zero
After=network-online.target
Wants=network-online.target

[Service]
Environment=AWS_REGION=us-east-1
ExecStart=/opt/agentepessoal/venv/bin/python /opt/agentepessoal/bedrock_proxy.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/agentepessoal-url.service <<'UNIT'
[Unit]
Description=Publish Agent Zero tunnel URL to SSM
After=docker.service
Requires=docker.service

[Service]
Environment=AWS_REGION=us-east-1
ExecStart=/opt/agentepessoal/venv/bin/python /opt/agentepessoal/report_url.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/agentepessoal-watchdog.service <<'UNIT'
[Unit]
Description=Stop the VM when idle

[Service]
Type=oneshot
Environment=IDLE_MINUTES={{IDLE_MINUTES}}
EnvironmentFile=/etc/agentepessoal.env
ExecStart=/opt/agentepessoal/watchdog.sh
UNIT

cat > /etc/systemd/system/agentepessoal-watchdog.timer <<'UNIT'
[Unit]
Description=Check for idleness every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
UNIT

# Hourly backup, plus a final one on every shutdown (ExecStop runs before network/docker stop).
cat > /etc/systemd/system/agentepessoal-backup.service <<'UNIT'
[Unit]
Description=Back up Agent Zero data to S3

[Service]
Type=oneshot
EnvironmentFile=/etc/agentepessoal.env
ExecStart=/opt/agentepessoal/backup.sh
UNIT

cat > /etc/systemd/system/agentepessoal-backup.timer <<'UNIT'
[Unit]
Description=Hourly backup of Agent Zero data

[Timer]
OnBootSec=15min
OnUnitActiveSec=1h

[Install]
WantedBy=timers.target
UNIT

cat > /etc/systemd/system/agentepessoal-backup-on-shutdown.service <<'UNIT'
[Unit]
Description=Back up Agent Zero data to S3 on shutdown
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
EnvironmentFile=/etc/agentepessoal.env
ExecStart=/bin/true
ExecStop=/opt/agentepessoal/backup.sh
TimeoutStopSec=300

[Install]
WantedBy=multi-user.target
UNIT

docker pull {{IMAGE}}
docker run -d --name agent-zero --restart unless-stopped \
  -p 127.0.0.1:50080:80 \
  --add-host=host.docker.internal:host-gateway \
  -v /opt/a0/usr:/a0/usr \
  {{IMAGE}}

systemctl daemon-reload
systemctl enable --now agentepessoal-proxy.service agentepessoal-url.service \
  agentepessoal-watchdog.timer agentepessoal-backup.timer agentepessoal-backup-on-shutdown.service

echo "agentepessoal setup done"

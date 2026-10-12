#!/bin/bash
# Idempotent VM setup (Ubuntu 22.04 arm64, Graviton): Agent Zero + virtual Android phone.
# Run by the first-boot user data, and again by `deploy.py --update` to push changes.
# Expects the bundle extracted at /opt/agentepessoal/bundle and /etc/agentepessoal.env.
set -euxo pipefail
source /etc/agentepessoal.env   # BACKUP_BUCKET, IMAGE, IDLE_MINUTES
B=/opt/agentepessoal/bundle
REGION=us-east-1
export DEBIAN_FRONTEND=noninteractive

# --- base packages --------------------------------------------------------------
if ! command -v docker >/dev/null || ! command -v adb >/dev/null; then
  apt-get update -y
  apt-get install -y docker.io python3-venv unzip curl adb "linux-modules-extra-$(uname -r)" || \
    apt-get install -y docker.io python3-venv unzip curl adb
fi
# 12/10 review: the agent's Docker log grew ~200 MB a day with no limit. Containers created from now on get a size
# limit from the daemon (read when docker starts); existing ones keep their settings, so their logs are rotated in place.
if [ ! -f /etc/docker/daemon.json ]; then
  mkdir -p /etc/docker
  echo '{"log-driver": "json-file", "log-opts": {"max-size": "50m", "max-file": "3"}}' > /etc/docker/daemon.json
  systemctl restart docker 2>/dev/null || true
fi
cat > /etc/logrotate.d/agentepessoal-docker <<'EOF'
/var/lib/docker/containers/*/*-json.log {
  daily
  maxsize 100M
  rotate 3
  compress
  missingok
  notifempty
  copytruncate
}
EOF
systemctl enable --now docker
if ! command -v cloudflared >/dev/null; then
  curl -sSfL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o /tmp/cloudflared.deb
  dpkg -i /tmp/cloudflared.deb && rm /tmp/cloudflared.deb
fi

# Admin access is through SSM Session Manager; no SSH port is opened.
systemctl disable --now ssh.service ssh.socket 2>/dev/null || true

# Hibernation on Ubuntu Graviton: AWS recommends disabling KASLR.
REBOOT=0
if ! grep -q nokaslr /proc/cmdline; then
  echo 'GRUB_CMDLINE_LINUX_DEFAULT="$GRUB_CMDLINE_LINUX_DEFAULT nokaslr"' > /etc/default/grub.d/99-agentepessoal-nokaslr.cfg
  update-grub
  REBOOT=1
fi

# Binder driver for the Android container.
echo binder_linux > /etc/modules-load.d/redroid.conf
echo 'options binder_linux devices="binder,hwbinder,vndbinder"' > /etc/modprobe.d/redroid.conf
modprobe binder_linux devices="binder,hwbinder,vndbinder" || true

# --- helper services and scripts -------------------------------------------------
mkdir -p /opt/agentepessoal /var/lib/agentepessoal /opt/a0/usr /opt/android-data
[ -x /opt/agentepessoal/venv/bin/python ] || python3 -m venv /opt/agentepessoal/venv
/opt/agentepessoal/venv/bin/pip install --quiet --upgrade boto3 aws-bedrock-token-generator croniter google-auth requests  # google-auth: Vertex AI through AWS federation (bedrock_proxy)
install -m 755 "$B/bedrock_proxy.py" "$B/report_url.py" "$B/watchdog.sh" "$B/memguard.sh" "$B/backup.sh" "$B/hibernate.sh" "$B/entrada.sh" "$B/credenciais_meta.py" "$B/ponte_whatsapp.py" "$B/proximo_despertar.py" "$B/saude.py" "$B/firewall.sh" /opt/agentepessoal/
install -m 755 "$B/phone/install_apps.sh" "$B/phone/google_id.sh" "$B/agent_tools.sh" /opt/agentepessoal/

# Mark resumes from hibernation so the idle timer restarts.
cat > /usr/lib/systemd/system-sleep/agentepessoal <<'EOF'
#!/bin/sh
[ "$1" = "post" ] && touch /var/lib/agentepessoal/resumed
exit 0
EOF
chmod +x /usr/lib/systemd/system-sleep/agentepessoal

# --- restore data, then agent configuration -----------------------------------------
# 12/10 review: a restore that failed was marked as done anyway, and the next hourly backup (sync --delete) would then
# delete from S3 everything that had not come back. Now the mark only follows a restore that worked (2 = some special
# file skipped), and backup.sh never deletes in S3 while the mark is missing; the next boot tries again.
if [ ! -f /var/lib/agentepessoal/restored ]; then
  /usr/local/bin/aws s3 sync "s3://${BACKUP_BUCKET}/usr" /opt/a0/usr --only-show-errors; rc=$?
  if [ "$rc" -eq 0 ] || [ "$rc" -eq 2 ]; then
    touch /var/lib/agentepessoal/restored
  else
    logger -t agentepessoal "restore from S3 failed (rc=$rc): the backup will not delete anything in S3 until it works"
  fi
fi
mkdir -p /opt/a0/usr/plugins/_model_config /opt/a0/usr/plugins/_code_execution /opt/a0/usr/memoria /opt/a0/usr/skills
cp "$B/generated/presets.yaml" /opt/a0/usr/plugins/_model_config/presets.yaml
cp "$B/generated/code_execution.json" /opt/a0/usr/plugins/_code_execution/config.json
# 12/10 review: re-running setup (deploy.py --update) deleted every plugin installed by implantar.py, with its .versao and
# config.json, and copied the local folder over it (even what was never committed). Now setup only installs a plugin
# or skill that is not there yet (a new VM); updates go through infra/operador/implantar.py: from git, tested first.
for d in "$B"/plugins/*/; do n=$(basename "$d"); [ -d "/opt/a0/usr/plugins/$n" ] || cp -r "$d" /opt/a0/usr/plugins/; done
for d in "$B"/skills/*/; do n=$(basename "$d"); [ -d "/opt/a0/usr/skills/$n" ] || { mkdir -p "/opt/a0/usr/skills/$n" && cp -r "$d". "/opt/a0/usr/skills/$n/"; }; done
# One profile per person (login_usuarios); the original single profile becomes the owner's.
mkdir -p /opt/a0/usr/memoria/usuarios
if [ ! -f /opt/a0/usr/memoria/usuarios/matheus.md ]; then
  if [ -f /opt/a0/usr/memoria/sobre-voce.md ]; then mv /opt/a0/usr/memoria/sobre-voce.md /opt/a0/usr/memoria/usuarios/matheus.md
  else cp "$B/memoria/sobre-voce.md" /opt/a0/usr/memoria/usuarios/matheus.md; fi
fi
[ -d /opt/a0/usr/projects/carreira ] || { mkdir -p /opt/a0/usr/projects/carreira && cp -r "$B/project-carreira/." /opt/a0/usr/projects/carreira/; }

# Login: the people in /opt/a0/usr/usuarios.json (plugin login_usuarios; create them with
# usuarios.py). Agent Zero itself needs one AUTH pair to require a login: a random "master"
# pair kept in /opt/agentepessoal/auth-master. A fixed FLASK_SECRET_KEY keeps sessions valid
# when the server restarts. Agent Zero always allows its own tunnel origin.
[ -s /opt/agentepessoal/auth-master ] || { umask 077; head -c 32 /dev/urandom | base64 | tr -dc A-Za-z0-9 > /opt/agentepessoal/auth-master; }
[ -s /opt/agentepessoal/flask-secret ] || { umask 077; head -c 48 /dev/urandom | base64 | tr -dc A-Za-z0-9 > /opt/agentepessoal/flask-secret; }
touch /opt/a0/usr/.env
sed -i -E '/^(AUTH_LOGIN|AUTH_PASSWORD|API_KEY_OTHER|ALLOWED_ORIGINS|FLASK_SECRET_KEY)=/d' /opt/a0/usr/.env
{ set +x; } 2>/dev/null  # the lines below carry the login password and the session key: never in the log (12/10)
{
  echo "API_KEY_OTHER=local-proxy"
  echo "ALLOWED_ORIGINS=*://localhost,*://localhost:*,*://127.0.0.1,*://127.0.0.1:*"
  # Always: login required (12/10 review: when the restore from S3 failed and usuarios.json was missing, the UI came up
  # with no login at all, reachable through the tunnel). Without usuarios.json only the master pair in
  # /opt/agentepessoal/auth-master gets in, until the users are restored (usuarios.py).
  echo "AUTH_LOGIN=_agentepessoal"
  echo "AUTH_PASSWORD=$(cat /opt/agentepessoal/auth-master)"
  echo "FLASK_SECRET_KEY=$(cat /opt/agentepessoal/flask-secret)"
} >> /opt/a0/usr/.env
set -x
chmod 600 /opt/a0/usr/.env

# --- containers -------------------------------------------------------------------
docker network inspect phone >/dev/null 2>&1 || docker network create phone

# Android 14 + Google Play (MindTheGapps, checksum-pinned), built locally on top of redroid.
ANDROID_IMAGE=redroid-gapps:14
if ! docker image inspect "$ANDROID_IMAGE" >/dev/null 2>&1; then
  G=/opt/agentepessoal/gapps-build
  rm -rf "$G" && mkdir -p "$G/mindthegapps"
  curl -sSfL -o "$G/mtg.zip" https://github.com/s1204IT/MindTheGappsBuilder/releases/download/20240226/MindTheGapps-14.0.0-arm64-20240226.zip
  echo "a0905cc7bf3f4f4f2e3f59a4e1fc789b  $G/mtg.zip" | md5sum -c -
  unzip -q "$G/mtg.zip" 'system/*' -d "$G/mindthegapps"
  cp "$B/phone/gapps.Dockerfile" "$G/Dockerfile"
  docker build -q -t "$ANDROID_IMAGE" "$G"
  rm -f "$G/mtg.zip"
fi
current=$(docker container inspect -f '{{.Config.Image}}' android 2>/dev/null || true)
if [ "$current" != "$ANDROID_IMAGE" ]; then
  docker rm -f android 2>/dev/null || true
  # Google services need a fresh /data; keep the previous one aside once.
  if [ -n "$current" ] && [ ! -d /opt/android-data.pre-gapps ]; then
    mv /opt/android-data /opt/android-data.pre-gapps
    rm -f /var/lib/agentepessoal/apps-installed
  fi
  mkdir -p /opt/android-data
  docker run -d --privileged --name android --restart unless-stopped --network phone \
    -p 127.0.0.1:5555:5555 -v /opt/android-data:/data \
    "$ANDROID_IMAGE" \
    androidboot.redroid_width=720 androidboot.redroid_height=1280 androidboot.redroid_dpi=320 \
    androidboot.redroid_gpu_mode=guest
fi

docker build -q -t ws-scrcpy -f "$B/phone/ws-scrcpy.Dockerfile" "$B/phone"
if ! docker container inspect ws-scrcpy >/dev/null 2>&1; then
  docker run -d --name ws-scrcpy --restart unless-stopped --network phone -p 127.0.0.1:8000:8000 ws-scrcpy
fi

docker pull -q "$IMAGE"
if [ "$(docker inspect -f '{{.Config.Image}}' --type container agent-zero 2>/dev/null)" != "$IMAGE" ]; then
  docker rm -f agent-zero 2>/dev/null || true
  docker run -d --name agent-zero --restart unless-stopped \
    -p 127.0.0.1:50080:80 --add-host=host.docker.internal:host-gateway \
    -v /opt/a0/usr:/a0/usr "$IMAGE"
else
  docker restart agent-zero
fi
docker network connect phone agent-zero 2>/dev/null || true
# 12/10 review: no container may take the whole VM (10/10 the agent's browser reached 11.8 GB and the VM froze for
# 30 min). Past its limit the kernel ends a process inside that container (a browser tab, or the agent, which
# supervisord restarts) and the rest of the VM keeps working; memguard.sh stays as the last line. Applied on every
# setup, also to containers that already exist.
docker update --memory 10g --memory-swap 10g agent-zero >/dev/null
docker update --memory 3g --memory-swap 3g android >/dev/null 2>&1 || true
docker update --memory 512m --memory-swap 512m ws-scrcpy >/dev/null 2>&1 || true
# The agent's browser kept a "Save password?" bubble over every page (and every screen recording):
# turn the password manager and autofill off with a Chromium managed policy (lives in the
# container's /etc, so it is rewritten on every setup)
docker exec -i agent-zero sh -c 'mkdir -p /etc/chromium/policies/managed && cat > /etc/chromium/policies/managed/agentepessoal.json' <<'EOF'
{"PasswordManagerEnabled": false, "PasswordLeakDetectionEnabled": false, "AutofillAddressEnabled": false, "AutofillCreditCardEnabled": false}
EOF

# faster-whisper for voice notes (plugins/whatsapp): ~2x faster than Agent Zero's Whisper on CPU
docker exec agent-zero /opt/venv-a0/bin/pip install --quiet faster-whisper yt-dlp || true  # yt-dlp: plugins/video
# yt-dlp's YouTube challenge solver (ejs); it runs on the image's node (deno has no ARM build here)
docker exec agent-zero /opt/venv-a0/bin/pip install --quiet -U "yt-dlp[default]" || true
# Claude Code CLI for coding tasks: Claude on Bedrock through the proxy's /bedrock route (the proxy signs with
# the VM role), so no claude.ai login, device check or captcha
docker exec agent-zero sh -c 'command -v claude >/dev/null || npm install -g --no-fund --no-audit @anthropic-ai/claude-code' || true
docker exec -i agent-zero sh -c 'mkdir -p /root/.claude && cat > /root/.claude/settings.json' <<'EOF'
{
  "env": {
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "AWS_REGION": "us-east-1",
    "ANTHROPIC_BEDROCK_BASE_URL": "http://host.docker.internal:8787/bedrock",
    "CLAUDE_CODE_SKIP_BEDROCK_AUTH": "1",
    "ANTHROPIC_MODEL": "us.anthropic.claude-opus-5-5",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "us.anthropic.claude-opus-5-5",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "us.anthropic.claude-sonnet-5-5",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "us.anthropic.claude-haiku-5-5",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_AUTOUPDATER": "1"
  }
}
EOF
# Web search: from an AWS address Google/Startpage/Mojeek/Qwant refuse and Brave rate-limits, so plain searches
# came back empty. Turn on the engines that answer (Yandex, Bing) and off the ones that only time out.
docker exec agent-zero sh -c 'grep -q "agentepessoal: motores" /etc/searxng/settings.yml || cat >> /etc/searxng/settings.yml <<EOS

# agentepessoal: motores que respondem a um endereço da AWS
engines:
  - name: yandex
    disabled: false
  - name: bing
    disabled: false
  - name: google
    disabled: true
  - name: startpage
    disabled: true
  - name: qwant
    disabled: true
  - name: mojeek
    disabled: true
EOS
supervisorctl restart run_searxng' || true

# Google connector (MCP, plugins/conectores): its own venv under usr/ so it survives container rebuilds
docker exec agent-zero sh -c '[ -x /a0/usr/mcp/venv-google/bin/workspace-mcp ] || (mkdir -p /a0/usr/mcp/google &&
  uv venv -q -p 3.12 /a0/usr/mcp/venv-google && VIRTUAL_ENV=/a0/usr/mcp/venv-google uv pip install -q workspace-mcp==2.0.1)' || true

# --- systemd units ---------------------------------------------------------------
# Before=docker.service (12/10 review): routines fired at boot before the proxy was up and ended in error.
cat > /etc/systemd/system/agentepessoal-proxy.service <<'EOF'
[Unit]
Description=Bedrock bearer-token proxy for Agent Zero
After=network-online.target
Wants=network-online.target
Before=docker.service
[Service]
Environment=AWS_REGION=us-east-1
EnvironmentFile=/etc/agentepessoal.env
ExecStart=/opt/agentepessoal/venv/bin/python /opt/agentepessoal/bedrock_proxy.py
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/agentepessoal-credenciais-meta.service <<'EOF'
[Unit]
Description=Short-lived AWS credentials for the agent to write the NEXOS Meta app secret
After=network-online.target
Wants=network-online.target
[Service]
Environment=AWS_REGION=us-east-1
ExecStart=/opt/agentepessoal/venv/bin/python /opt/agentepessoal/credenciais_meta.py
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF

# AWS profile the agent uses for `pnpm --filter @ros/infra-aws segredo-meta` (see credenciais_meta.py)
mkdir -p /opt/a0/usr/.aws
cat > /opt/a0/usr/.aws/segredo-meta.py <<'EOF'
import urllib.request
print(urllib.request.urlopen("http://host.docker.internal:8788/", timeout=20).read().decode())
EOF
cat > /opt/a0/usr/.aws/config <<'EOF'
[profile segredo-meta]
region = us-east-1
credential_process = python3 /a0/usr/.aws/segredo-meta.py
EOF

cat > /etc/systemd/system/agentepessoal-whatsapp.service <<'EOF'
[Unit]
Description=WhatsApp bridge: queued messages in, agent answers and notices out
After=network-online.target docker.service
Wants=network-online.target
[Service]
Environment=AWS_REGION=us-east-1
ExecStart=/opt/agentepessoal/venv/bin/python /opt/agentepessoal/ponte_whatsapp.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/agentepessoal-google-mcp.service <<'EOF'
[Unit]
Description=Google connector (workspace-mcp: Gmail/Calendar read-only, Drive/Docs/Sheets write) inside the agent container
After=docker.service
Wants=docker.service
[Service]
# A long-lived HTTP server, not stdio: Agent Zero starts stdio servers per call, so the OAuth
# callback (localhost:8765/oauth2callback, opened by the agent's browser) had nobody listening.
ExecStartPre=/bin/sh -c 'until docker exec agent-zero test -f /a0/usr/mcp/google/client_secret.json; do sleep 10; done'
# `docker exec` leaves the server running in the container when the unit stops: end it, or the next start finds port 8765 taken
ExecStartPre=-/usr/bin/docker exec agent-zero pkill -f venv-google/bin/workspace-mcp
ExecStopPost=-/usr/bin/docker exec agent-zero pkill -f venv-google/bin/workspace-mcp
ExecStart=/usr/bin/docker exec -e GOOGLE_CLIENT_SECRET_PATH=/a0/usr/mcp/google/client_secret.json \
  -e WORKSPACE_MCP_CREDENTIALS_DIR=/a0/usr/mcp/google/credenciais -e USER_GOOGLE_EMAIL=falhanosistema1111@gmail.com \
  -e WORKSPACE_MCP_PORT=8765 -e PORT=8765 agent-zero /a0/usr/mcp/venv-google/bin/workspace-mcp \
  --single-user --permissions gmail:readonly calendar:readonly drive:full docs:full sheets:full \
  --disabled-tools set_drive_file_permissions manage_drive_access debug_docs_runtime_info debug_table_structure \
  --transport streamable-http
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/agentepessoal-phone-tunnel.service <<'EOF'
[Unit]
Description=Cloudflare quick tunnel for the phone screen (ws-scrcpy)
After=network-online.target docker.service
Wants=network-online.target
[Service]
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/agentepessoal-url.service <<'EOF'
[Unit]
Description=Publish agent and phone tunnel URLs to SSM
After=docker.service agentepessoal-phone-tunnel.service
Requires=docker.service
[Service]
Environment=AWS_REGION=us-east-1
ExecStart=/opt/agentepessoal/venv/bin/python /opt/agentepessoal/report_url.py
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF

# adb inside the agent container (reinstalled if the container is ever recreated).
cat > /etc/systemd/system/agentepessoal-agent-tools.service <<'EOF'
[Unit]
Description=Ensure adb is available inside the Agent Zero container
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
ExecStart=/opt/agentepessoal/agent_tools.sh
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/agentepessoal-watchdog.service <<EOF
[Unit]
Description=Hibernate the VM when idle
[Service]
Type=oneshot
Environment=IDLE_MINUTES=${IDLE_MINUTES}
EnvironmentFile=/etc/agentepessoal.env
ExecStart=/opt/agentepessoal/watchdog.sh
EOF

cat > /etc/systemd/system/agentepessoal-watchdog.timer <<'EOF'
[Unit]
Description=Check for idleness every 5 minutes
[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/agentepessoal-memguard.service <<'EOF'
[Unit]
Description=Restart the agent container before the VM freezes for lack of memory
[Service]
Type=oneshot
ExecStart=/opt/agentepessoal/memguard.sh
EOF

cat > /etc/systemd/system/agentepessoal-memguard.timer <<'EOF'
[Unit]
Description=Check free memory every minute
[Timer]
OnBootSec=3min
OnUnitActiveSec=1min
AccuracySec=10s
[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/agentepessoal-backup.service <<'EOF'
[Unit]
Description=Back up Agent Zero data to S3
[Service]
Type=oneshot
EnvironmentFile=/etc/agentepessoal.env
ExecStart=/opt/agentepessoal/backup.sh
EOF

cat > /etc/systemd/system/agentepessoal-backup.timer <<'EOF'
[Unit]
Description=Hourly backup of Agent Zero data
[Timer]
OnBootSec=15min
OnUnitActiveSec=1h
[Install]
WantedBy=timers.target
EOF

# Files sent from the control page land in S3; pull them into the workdir every 30 s.
cat > /etc/systemd/system/agentepessoal-entrada.service <<'EOF'
[Unit]
Description=Move files uploaded from the control page into the agent workdir
After=network-online.target
[Service]
Type=oneshot
EnvironmentFile=/etc/agentepessoal.env
ExecStart=/opt/agentepessoal/entrada.sh
EOF

cat > /etc/systemd/system/agentepessoal-entrada.timer <<'EOF'
[Unit]
Description=Check for files uploaded from the control page
[Timer]
OnBootSec=20s
OnUnitActiveSec=30s
AccuracySec=5s
[Install]
WantedBy=timers.target
EOF

# The virtual phone may not reach the host's model proxy, Meta credentials or phone bridge (12/10 review).
cat > /etc/systemd/system/agentepessoal-firewall.service <<'EOF'
[Unit]
Description=Keep the virtual phone's network away from the host's private ports
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/agentepessoal/firewall.sh
[Install]
WantedBy=multi-user.target
EOF

# Daily health check (12/10 review): one phone notice, only when something is wrong.
cat > /etc/systemd/system/agentepessoal-saude.service <<'EOF'
[Unit]
Description=Daily health check of the agent VM (notice only when something is wrong)
After=network-online.target docker.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/agentepessoal/saude.py --avisar
EOF

cat > /etc/systemd/system/agentepessoal-saude.timer <<'EOF'
[Unit]
Description=Health check every morning (8h50 Bahia)
[Timer]
OnCalendar=*-*-* 11:50:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
EOF

# Full stops (not hibernation) also get a final backup.
cat > /etc/systemd/system/agentepessoal-backup-on-shutdown.service <<'EOF'
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
EOF

systemctl daemon-reload
systemctl enable agentepessoal-proxy agentepessoal-phone-tunnel agentepessoal-url agentepessoal-agent-tools \
  agentepessoal-watchdog.timer agentepessoal-memguard.timer agentepessoal-backup.timer agentepessoal-backup-on-shutdown agentepessoal-entrada.timer agentepessoal-saude.timer agentepessoal-firewall \
  agentepessoal-credenciais-meta agentepessoal-whatsapp agentepessoal-google-mcp
systemctl restart agentepessoal-proxy agentepessoal-phone-tunnel agentepessoal-url agentepessoal-credenciais-meta agentepessoal-whatsapp
systemctl restart --no-block agentepessoal-google-mcp
systemctl start agentepessoal-agent-tools agentepessoal-watchdog.timer agentepessoal-memguard.timer agentepessoal-backup.timer agentepessoal-backup-on-shutdown agentepessoal-entrada.timer agentepessoal-saude.timer agentepessoal-firewall

# First boot only: install test apps on the phone.
[ -f /var/lib/agentepessoal/apps-installed ] || { /opt/agentepessoal/install_apps.sh && touch /var/lib/agentepessoal/apps-installed; } || true

echo "agentepessoal setup done"
if [ "$REBOOT" = 1 ]; then
  echo "rebooting to apply nokaslr"
  (sleep 5; systemctl reboot) &
fi

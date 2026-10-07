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
/opt/agentepessoal/venv/bin/pip install --quiet --upgrade boto3 aws-bedrock-token-generator
install -m 755 "$B/bedrock_proxy.py" "$B/report_url.py" "$B/watchdog.sh" "$B/backup.sh" "$B/hibernate.sh" /opt/agentepessoal/
install -m 755 "$B/phone/install_apps.sh" "$B/phone/google_id.sh" "$B/agent_tools.sh" /opt/agentepessoal/

# Mark resumes from hibernation so the idle timer restarts.
cat > /usr/lib/systemd/system-sleep/agentepessoal <<'EOF'
#!/bin/sh
[ "$1" = "post" ] && touch /var/lib/agentepessoal/resumed
exit 0
EOF
chmod +x /usr/lib/systemd/system-sleep/agentepessoal

# --- restore data, then agent configuration -----------------------------------------
if [ ! -f /var/lib/agentepessoal/restored ]; then
  /usr/local/bin/aws s3 sync "s3://${BACKUP_BUCKET}/usr" /opt/a0/usr --only-show-errors || true
  touch /var/lib/agentepessoal/restored
fi
mkdir -p /opt/a0/usr/plugins/_model_config /opt/a0/usr/plugins/_code_execution /opt/a0/usr/memoria /opt/a0/usr/skills
cp "$B/generated/presets.yaml" /opt/a0/usr/plugins/_model_config/presets.yaml
cp "$B/generated/code_execution.json" /opt/a0/usr/plugins/_code_execution/config.json
rm -rf /opt/a0/usr/plugins/memoria_pessoal && cp -r "$B/plugins/memoria_pessoal" /opt/a0/usr/plugins/
# Overlay (no delete): keeps scripts the agent saved itself, e.g. skills/piloto-rapido/scripts/tarefas/.
for d in "$B"/skills/*/; do n=$(basename "$d"); mkdir -p "/opt/a0/usr/skills/$n" && cp -r "$d". "/opt/a0/usr/skills/$n/"; done
[ -f /opt/a0/usr/memoria/sobre-voce.md ] || cp "$B/memoria/sobre-voce.md" /opt/a0/usr/memoria/
[ -d /opt/a0/usr/projects/carreira ] || { mkdir -p /opt/a0/usr/projects/carreira && cp -r "$B/project-carreira/." /opt/a0/usr/projects/carreira/; }

# Single user, no Agent Zero login: the VM has no open ports and the random tunnel URL is
# only revealed by the key-protected control page. Agent Zero always allows its own tunnel.
touch /opt/a0/usr/.env
sed -i -E '/^(AUTH_LOGIN|AUTH_PASSWORD|API_KEY_OTHER|ALLOWED_ORIGINS)=/d' /opt/a0/usr/.env
{
  echo "API_KEY_OTHER=local-proxy"
  echo "ALLOWED_ORIGINS=*://localhost,*://localhost:*,*://127.0.0.1,*://127.0.0.1:*"
} >> /opt/a0/usr/.env
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

# --- systemd units ---------------------------------------------------------------
cat > /etc/systemd/system/agentepessoal-proxy.service <<'EOF'
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
  agentepessoal-watchdog.timer agentepessoal-backup.timer agentepessoal-backup-on-shutdown
systemctl restart agentepessoal-proxy agentepessoal-phone-tunnel agentepessoal-url
systemctl start agentepessoal-agent-tools agentepessoal-watchdog.timer agentepessoal-backup.timer agentepessoal-backup-on-shutdown

# First boot only: install test apps on the phone.
[ -f /var/lib/agentepessoal/apps-installed ] || { /opt/agentepessoal/install_apps.sh && touch /var/lib/agentepessoal/apps-installed; } || true

echo "agentepessoal setup done"
if [ "$REBOOT" = 1 ]; then
  echo "rebooting to apply nokaslr"
  (sleep 5; systemctl reboot) &
fi

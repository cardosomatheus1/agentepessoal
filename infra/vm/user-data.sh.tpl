#!/bin/bash
# First boot: fetch the setup bundle from S3 and run vm/setup.sh. Rendered by infra/deploy.py.
set -euxo pipefail
exec > >(tee -a /var/log/agentepessoal-setup.log) 2>&1

cat > /etc/agentepessoal.env <<'EOF'
BACKUP_BUCKET={{BUCKET}}
IMAGE={{IMAGE}}
IDLE_MINUTES={{IDLE_MINUTES}}
EOF

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y unzip curl
curl -sSfL https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp && /tmp/aws/install --update && rm -rf /tmp/aws /tmp/awscliv2.zip

mkdir -p /opt/agentepessoal/bundle
/usr/local/bin/aws s3 cp "s3://{{BUCKET}}/bootstrap/bundle.tgz" /tmp/bundle.tgz --only-show-errors
tar -xzf /tmp/bundle.tgz -C /opt/agentepessoal/bundle
bash /opt/agentepessoal/bundle/setup.sh

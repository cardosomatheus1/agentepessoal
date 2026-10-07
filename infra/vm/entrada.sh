#!/bin/bash
# Move files the user sent through the control page (s3://BUCKET/entrada/) into the agent's
# workdir. Uploads go straight to S3, so they work while the VM is off and aren't limited by the
# tunnel (100 MB). The bucket is versioned: a moved file stays recoverable for 30 days.
set -u
BUCKET="${BACKUP_BUCKET:?}"
DEST=/opt/a0/usr/workdir/entrada
mkdir -p "$DEST"
/usr/local/bin/aws s3 mv "s3://${BUCKET}/entrada/" "$DEST/" --recursive --only-show-errors \
  && find "$DEST" -newermt '-1 minute' -type f -printf '%f\n' | while read -r f; do logger -t agentepessoal "arquivo recebido: $f"; done

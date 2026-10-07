#!/bin/bash
# Back up Agent Zero's data (chats, memory, projects, uploads, settings) to S3.
# Runs hourly, before an idle shutdown, and on every OS shutdown (systemd ExecStop).
# The VM disk also persists while stopped; S3 is the copy that survives losing the VM.
set -u
BUCKET="${BACKUP_BUCKET:?}"
SRC=/opt/a0/usr
[ -d "$SRC" ] || exit 0
/usr/local/bin/aws s3 sync "$SRC" "s3://${BUCKET}/usr" --delete --only-show-errors \
  --exclude "tmp/*" --exclude "*/__pycache__/*" \
  && logger -t agentepessoal "backup to s3://${BUCKET}/usr done"

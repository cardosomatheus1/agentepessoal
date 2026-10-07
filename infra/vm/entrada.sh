#!/bin/bash
# Move files the user sent from outside the tunnel (100 MB limit) into the agent:
#   s3://BUCKET/entrada/chats/<chat id>/*  -> that chat's anexos/ (button "Arquivo grande" in the chat)
#   s3://BUCKET/entrada/*                  -> /a0/usr/workdir/entrada (control page, works with the VM off)
# Runs every 30 s and on demand (bedrock_proxy /arquivos/puxar). The bucket is versioned, so a
# moved file stays recoverable for 30 days.
set -u
BUCKET="${BACKUP_BUCKET:?}"
AWS=/usr/local/bin/aws
DEST=/opt/a0/usr/workdir/entrada
CHATS=/opt/a0/usr/chats
exec 9>/run/agentepessoal-entrada.lock
flock 9
mkdir -p "$DEST"
mover() {  # $1 = s3 source prefix, $2 = local dir, rest = extra args
  local src=$1 dst=$2; shift 2
  "$AWS" s3 mv "$src" "$dst/" --recursive --no-progress "$@" 2>&1 \
    | sed -n 's/^move: .* to \(.*\)$/arquivo recebido: \1/p' | logger -t agentepessoal
}
for id in $("$AWS" s3 ls "s3://${BUCKET}/entrada/chats/" 2>/dev/null | awk '$1=="PRE"{print $2}' | tr -d /); do
  [[ "$id" =~ ^[A-Za-z0-9_-]{1,64}$ ]] || continue
  mkdir -p "$CHATS/$id/anexos"
  mover "s3://${BUCKET}/entrada/chats/$id/" "$CHATS/$id/anexos"
done
mover "s3://${BUCKET}/entrada/" "$DEST" --exclude "chats/*"

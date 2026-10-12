#!/bin/bash
# Back up Agent Zero's data (chats, memory, projects, uploads, settings) to S3.
# Runs hourly, before an idle shutdown, and on every OS shutdown (systemd ExecStop).
# The VM disk also persists while stopped; S3 is the copy that survives losing the VM.
# navegador/ (the browser profiles, ~2 GB of constantly changing cache) stays out: the daily disk snapshot keeps it.
# 12/10 review: every run "failed" (exit 2) because the sync skips the desktop's ssh-agent sockets and dangling
# links, while everything else was copied; a real failure looked the same and nobody was told. Now exit 2 counts as
# done, and a real failure sends one phone notice a day.
set -u
BUCKET="${BACKUP_BUCKET:?}"
SRC=/opt/a0/usr
[ -d "$SRC" ] || exit 0

avisar() {  # Telegram through the host bridge, at most once a day; never stops the backup
  local chave marca=/var/lib/agentepessoal/backup-aviso-$(date +%F)
  [ -e "$marca" ] && return 0
  chave=$(cat /opt/a0/usr/whatsapp/.chave 2>/dev/null) || return 0
  python3 -c 'import json, sys; print(json.dumps({"usuario": "matheus", "texto": sys.argv[1], "tipo": "urgente"}))' "$1" |
    curl -s -m 15 -X POST http://127.0.0.1:8789/enviar -H "X-Chave: $chave" -H "Content-Type: application/json" \
      --data-binary @- >/dev/null 2>&1 && touch "$marca"
  return 0
}

# The action ledger (SQLite, plugins/central): S3 gets a consistent copy made by SQLite itself, never the live files
# caught in the middle of a write.
if [ -f "$SRC/central/agente.db" ]; then
  python3 -c 'import sqlite3, sys; o = sqlite3.connect(sys.argv[1]); d = sqlite3.connect(sys.argv[2]); o.backup(d); d.close(); o.close()' \
    "$SRC/central/agente.db" "$SRC/central/agente.copia.db" || logger -t agentepessoal "backup: copy of the action ledger failed"
fi
/usr/local/bin/aws s3 sync "$SRC" "s3://${BUCKET}/usr" --delete --only-show-errors \
  --exclude "tmp/*" --exclude "*/__pycache__/*" --exclude "navegador/*" \
  --exclude "plugins/_desktop/profiles/*/.ssh/agent/*" --exclude "central/agente.db" --exclude "central/agente.db-*"
rc=$?
# 2 = some special files (sockets, dangling links) were skipped; every other file was copied
if [ "$rc" -eq 0 ] || [ "$rc" -eq 2 ]; then
  logger -t agentepessoal "backup to s3://${BUCKET}/usr done (rc=$rc)"
  exit 0
fi
logger -t agentepessoal "backup to s3://${BUCKET}/usr FAILED (rc=$rc)"
avisar "⚠️ A cópia de segurança de hora em hora para o S3 falhou (código $rc). Nada se perdeu: os dados continuam no disco da VM e na cópia diária do disco."
exit "$rc"

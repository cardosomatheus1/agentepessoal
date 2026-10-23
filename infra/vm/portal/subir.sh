#!/bin/bash
# Sobe (ou atualiza) o portal (portal.py): Segundo Cérebro, Painel, Tarefas e Cofre fora do A0, com o login de sempre.
# Chamado pelo hermes/subir.sh com a imagem do Hermes (Python com aiohttp e Node). Só 127.0.0.1:8650; até a virada
# só leitura (PORTAL_SO_LEITURA=1, dados montados ro). O túnel/endereço público passa a apontar para cá na virada.
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
IMAGEM="${1:?imagem do Hermes}"
B=/opt/hermes/portal
mkdir -p "$B/app" "$B/segundo_cerebro/releases"; chmod 700 "$B"
install -m 644 "$AQUI/portal.py" "$B/app/portal.py"
[ -s "$B/segredo" ] || { umask 077; openssl rand -hex 32 > "$B/segredo"; }
install -m 600 /opt/hermes/api_key "$B/hermes_api_key"
# a release do Segundo Cérebro que o A0 serve, numa pasta do portal (o estado do Node do A0 fica com ele)
REL=$(tr -d '[:space:]' < /opt/a0/usr/segundo_cerebro/atual 2>/dev/null || true)
if [ -n "$REL" ] && [ -d "/opt/a0/usr/segundo_cerebro/releases/$REL" ]; then
  rsync -a --delete "/opt/a0/usr/segundo_cerebro/releases/$REL/" "$B/segundo_cerebro/releases/$REL/"
  printf '%s\n' "$REL" > "$B/segundo_cerebro/atual"
fi
docker rm -f portal >/dev/null 2>&1 || true
docker run -d --name portal --restart no --network host --user 0 --memory 768m --memory-swap 768m \
  -v /opt/a0/usr:/a0/usr:ro -v "$B:/portal" \
  -e PORTAL_SO_LEITURA=1 -e PORTAL_PORTA=8650 -e HERMES_URL=http://127.0.0.1:8642 \
  --entrypoint python3 "$IMAGEM" /portal/app/portal.py >/dev/null
for i in $(seq 1 30); do curl -fsS -m 3 http://127.0.0.1:8650/saude >/dev/null 2>&1 && break; sleep 1; done
curl -fsS -m 3 http://127.0.0.1:8650/saude >/dev/null && echo "PORTAL_OK" || { docker logs --tail 20 portal; exit 1; }

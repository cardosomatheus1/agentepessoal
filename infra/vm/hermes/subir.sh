#!/bin/bash
# Sobe (ou atualiza) o Hermes ao lado do Agent Zero (fase 1 da migração, docs/MIGRACAO_HERMES.md). Idempotente.
# Roda como root no host da VM, a partir da pasta com config.yaml e SOUL.md (o implantador copia os dois).
# Dados: /opt/hermes/data (= /opt/data no container). Os dados vivos do agente (/opt/a0/usr) entram no mesmo caminho
# de hoje (/a0/usr), então os helpers dos plugins rodam sem mudar. Sem canais de mensagem nesta fase: só o API server,
# ouvindo em 127.0.0.1:8642 do host.
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
IMAGEM="nousresearch/hermes-agent:v0.22.2"
DADOS=/opt/hermes/data
mkdir -p "$DADOS"
chmod 700 /opt/hermes
install -m 644 "$AQUI/config.yaml" "$DADOS/config.yaml"
install -m 644 "$AQUI/SOUL.md" "$DADOS/SOUL.md"
# Chave do API server: gerada uma vez, só na VM (nunca no git nem no chat).
if [ ! -s /opt/hermes/api_key ]; then
  umask 077; openssl rand -hex 32 > /opt/hermes/api_key
fi
docker pull -q "$IMAGEM" >/dev/null
docker rm -f hermes >/dev/null 2>&1 || true
docker run -d --name hermes --restart unless-stopped \
  --memory 3g --memory-swap 3g \
  --add-host host.docker.internal:host-gateway \
  -v "$DADOS":/opt/data \
  -v /opt/a0/usr:/a0/usr \
  -e AWS_ENDPOINT_URL_BEDROCK_RUNTIME=http://host.docker.internal:8787/bedrock \
  -e ANTHROPIC_BEDROCK_BASE_URL=http://host.docker.internal:8787/bedrock \
  -e AWS_ACCESS_KEY_ID=proxy -e AWS_SECRET_ACCESS_KEY=proxy -e AWS_REGION=us-east-1 -e AWS_EC2_METADATA_DISABLED=true \
  -e API_SERVER_ENABLED=true -e API_SERVER_HOST=0.0.0.0 -e API_SERVER_KEY="$(cat /opt/hermes/api_key)" \
  -e HERMES_TIMEZONE=America/Bahia \
  -p 127.0.0.1:8642:8642 \
  "$IMAGEM" gateway run >/dev/null
for i in $(seq 1 60); do
  curl -fsS -m 3 http://127.0.0.1:8642/health >/dev/null 2>&1 && break
  sleep 2
done
# De pé não basta: uma pergunta de verdade ao modelo, pelo mesmo caminho das conversas (Claude no Bedrock pelo proxy).
RESPOSTA=$(curl -sS -m 120 http://127.0.0.1:8642/v1/chat/completions -H "Authorization: Bearer $(cat /opt/hermes/api_key)" \
  -H 'Content-Type: application/json' -d '{"model":"hermes","messages":[{"role":"user","content":"Responda só: PONTE OK"}]}' || true)
if echo "$RESPOSTA" | grep -qi "PONTE OK"; then echo "HERMES_OK $(docker inspect -f '{{.Image}}' hermes)"; exit 0; fi
echo "HERMES_NAO_RESPONDEU: ${RESPOSTA:0:400}"; docker logs --tail 40 hermes; exit 1

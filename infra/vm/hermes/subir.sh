#!/bin/bash
# Sobe (ou atualiza) o Hermes ao lado do Agent Zero (fase 1 da migração, docs/MIGRACAO_HERMES.md). Idempotente.
# Roda como root no host da VM, a partir da pasta com config.yaml e SOUL.md (o implantador copia os dois).
# Dados: /opt/hermes/data (= /opt/data no container). Os dados vivos do agente (/opt/a0/usr) entram no mesmo caminho
# de hoje (/a0/usr), então os helpers dos plugins rodam sem mudar. Sem canais de mensagem nesta fase: só o API server,
# ouvindo em 127.0.0.1:8642 do host.
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
BASE="nousresearch/hermes-agent:v0.22.2"
# A nossa imagem = a oficial + os pacotes dos helpers (imagem/Dockerfile); o rótulo muda quando o Dockerfile muda.
IMAGEM="agentepessoal/hermes:$(sha256sum "$AQUI/imagem/Dockerfile" | cut -c1-12)"
DADOS=/opt/hermes/data
mkdir -p "$DADOS"
chmod 700 /opt/hermes
install -m 644 "$AQUI/config.yaml" "$DADOS/config.yaml"
install -m 644 "$AQUI/SOUL.md" "$DADOS/SOUL.md"
# Os nossos plugins do Hermes: a pasta inteira é trocada (o que saiu do git sai daqui também).
mkdir -p "$DADOS/plugins"
for p in "$AQUI"/plugins/*/; do
  nome=$(basename "$p"); rm -rf "$DADOS/plugins/$nome"; cp -r "$p" "$DADOS/plugins/$nome"
done
# Chave do API server: gerada uma vez, só na VM (nunca no git nem no chat).
if [ ! -s /opt/hermes/api_key ]; then
  umask 077; openssl rand -hex 32 > /opt/hermes/api_key
fi
# Constrói antes de derrubar: o Hermes fica fora o mínimo (com cache, repetir não refaz nada).
grep -q "^FROM $BASE\$" "$AQUI/imagem/Dockerfile" || { echo "HERMES_IMAGEM: o Dockerfile não parte de $BASE"; exit 1; }
docker image inspect "$IMAGEM" >/dev/null 2>&1 || docker build -q -t "$IMAGEM" "$AQUI/imagem" >/dev/null
docker rm -f hermes >/dev/null 2>&1 || true  # antes de remontar a vista: nada a segurando
# Vista dos dados vivos para o Hermes (dono 10000 na vista, nada muda no disco): ver agentepessoal-hermes-dados.service.
command -v bindfs >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -q bindfs >/dev/null
install -m 644 "$AQUI/agentepessoal-hermes-dados.service" /etc/systemd/system/agentepessoal-hermes-dados.service
systemctl daemon-reload
systemctl enable -q agentepessoal-hermes-dados.service
systemctl restart agentepessoal-hermes-dados.service
for i in $(seq 1 20); do mountpoint -q /opt/hermes/a0usr && break; sleep 1; done
mountpoint -q /opt/hermes/a0usr || { echo "HERMES_SEM_DADOS: a vista /opt/hermes/a0usr não montou"; exit 1; }
# AGENTEPESSOAL_ENSAIO=1 até a virada (fase 8): nada vai ao celular nem se publica na Meta pelo Hermes; o que iria fica
# em /opt/hermes/data/agentepessoal/ensaio_celular.jsonl (whatsapp/helpers/ponte.py, conteudo/helpers/conteudo.py).
docker run -d --name hermes --restart unless-stopped \
  --memory 3g --memory-swap 3g \
  --add-host host.docker.internal:host-gateway \
  -v "$DADOS":/opt/data \
  -v /opt/hermes/a0usr:/a0/usr \
  -e AWS_ENDPOINT_URL_BEDROCK_RUNTIME=http://host.docker.internal:8787/bedrock \
  -e ANTHROPIC_BEDROCK_BASE_URL=http://host.docker.internal:8787/bedrock \
  -e AWS_ACCESS_KEY_ID=proxy -e AWS_SECRET_ACCESS_KEY=proxy -e AWS_REGION=us-east-1 -e AWS_EC2_METADATA_DISABLED=true \
  -e API_SERVER_ENABLED=true -e API_SERVER_HOST=0.0.0.0 -e API_SERVER_KEY="$(cat /opt/hermes/api_key)" \
  -e HERMES_TIMEZONE=America/Bahia \
  -e AGENTEPESSOAL_ENSAIO=1 \
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

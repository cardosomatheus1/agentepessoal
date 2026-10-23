#!/bin/bash
# Os conectores (MCP) do Hermes (migração, fase 3), num container "hermes-mcp" na rede "hermes" (IP fixo .0.251):
# - Google (workspace-mcp 2.0.1, porta 8765) com uma CÓPIA das credenciais do A0 (/opt/a0/usr/mcp/google). No ensaio, só
#   leitura de tudo (Gmail, Agenda, Drive, Docs, Planilhas); na virada, as permissões do A0 (Drive/Docs/Planilhas com
#   escrita, sempre com aprovação);
# - GitHub (repasse na porta 8766 para api.githubcopilot.com com os cabeçalhos do A0, lidos do settings.json dele).
# Tokens só neste container (o Hermes não vê: /a0/usr/mcp aparece vazio para ele). Idempotente; roda como root no host.
#   --renovar   copia as credenciais do Google de novo
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
BASE=/opt/hermes/mcp
PERMISSOES="${HERMES_GOOGLE_PERMISSOES:-gmail:readonly calendar:readonly drive:readonly docs:readonly sheets:readonly}"
EMAIL=$(sed -n 's/.*USER_GOOGLE_EMAIL=\([^ ]*\).*/\1/p' /etc/systemd/system/agentepessoal-google-mcp.service | head -1)
mkdir -p "$BASE"; chmod 700 "$BASE"
if [ ! -d "$BASE/google/credenciais" ] || [ "${1:-}" = "--renovar" ]; then
  rm -rf "$BASE/google.novo"; mkdir -p "$BASE/google.novo"
  cp -a /opt/a0/usr/mcp/google/client_secret.json /opt/a0/usr/mcp/google/credenciais "$BASE/google.novo/"
  rm -rf "$BASE/google"; mv "$BASE/google.novo" "$BASE/google"
fi
# os cabeçalhos do MCP do GitHub do A0 (o token), só para o arquivo deste container; nada impresso
umask 077
python3 - "$BASE/github_headers.json" <<'PY'
import json, sys
s = json.load(open("/opt/a0/usr/settings.json"))
m = s.get("mcp_servers")
d = json.loads(m) if isinstance(m, str) else (m or {})
gh = (d.get("mcpServers") or d).get("github") or {}
h = gh.get("headers") or {}
json.dump(h if isinstance(h, dict) else {}, open(sys.argv[1], "w"))
print("GITHUB_CABECALHOS", len(h) if isinstance(h, dict) else 0)
PY
umask 022
IMAGEM_MCP="agentepessoal/hermes-mcp:$(cat "$AQUI/mcp/Dockerfile" "$AQUI/mcp/versoes.txt" "$AQUI/mcp/github_repasse.py" | sha256sum | cut -c1-12)"
docker image inspect "$IMAGEM_MCP" >/dev/null 2>&1 || docker build -q -t "$IMAGEM_MCP" "$AQUI/mcp" >/dev/null
SUB=$(docker network inspect hermes -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}')
IP="${SUB%.*.*}.0.251"
docker rm -f hermes-mcp >/dev/null 2>&1 || true
docker run -d --name hermes-mcp --restart no --network hermes --ip "$IP" --memory 768m --memory-swap 768m \
  -v "$BASE/google:/google" -v "$BASE/github_headers.json:/segredos/github_headers.json:ro" \
  -e GOOGLE_CLIENT_SECRET_PATH=/google/client_secret.json -e WORKSPACE_MCP_CREDENTIALS_DIR=/google/credenciais \
  -e USER_GOOGLE_EMAIL="$EMAIL" -e WORKSPACE_MCP_PORT=8765 -e PORT=8765 -e WORKSPACE_MCP_HOST=0.0.0.0 \
  --entrypoint /bin/sh "$IMAGEM_MCP" -c "workspace-mcp --single-user --permissions $PERMISSOES \
  --disabled-tools set_drive_file_permissions manage_drive_access debug_docs_runtime_info debug_table_structure \
  --transport streamable-http & exec python /opt/github_repasse.py 8766" >/dev/null
for i in $(seq 1 40); do
  docker exec hermes-mcp python -c "import socket;socket.create_connection(('127.0.0.1',8765),2)" >/dev/null 2>&1 && break
  sleep 1
done
echo "MCP_OK $IP"

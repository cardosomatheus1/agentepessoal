#!/bin/bash
# Liga os containers do Hermes na subida da VM (agentepessoal-hermes.service, depois do firewall e da vista dos dados):
# navegador e conectores antes do Hermes, o portal, e na virada o Hermes de cada convidado com o navegador dele.
# Os containers são criados pelo subir.sh / convidado.sh (--restart no): aqui só `docker start` dos que existem.
#   iniciar.sh [parar]
set -u
nomes=(hermes-navegador hermes-mcp hermes portal)
for c in $(docker ps -a --format '{{.Names}}' | grep -E '^hermes-navegador-' || true); do
  nomes+=("$c" "hermes-${c#hermes-navegador-}")
done
if [ "${1:-}" = parar ]; then
  for ((i=${#nomes[@]}-1; i>=0; i--)); do docker stop "${nomes[$i]}" >/dev/null 2>&1 || true; done
  exit 0
fi
falhou=0
for c in "${nomes[@]}"; do
  docker inspect "$c" >/dev/null 2>&1 || continue
  docker start "$c" >/dev/null || { logger -t agentepessoal "hermes: $c não ligou"; falhou=1; }
done
exit "$falhou"

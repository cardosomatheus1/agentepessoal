#!/bin/bash
# 12/10 review: the virtual phone (Docker network "phone") could reach the host's model proxy (8787), the Meta
# credentials service (8788) and the phone bridge (8789): an app installed on the phone could spend on models or get
# the short-lived AWS credentials. The agent reaches them through the default bridge (host.docker.internal), not
# through the phone network, so only traffic coming FROM the phone network to these host ports is dropped.
# One rule per port (this kernel has no "multiport" match). Idempotent; run at boot by agentepessoal-firewall.service
# (after docker) and by setup.sh. Exits non-zero, and says so in the log, when a rule could not be added.
set -u
REDE=$(docker network inspect phone -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
falhou=0
if [ -n "$REDE" ]; then
  for porta in 8787 8788 8789 8790; do
    regra=(INPUT -s "$REDE" -p tcp --dport "$porta" -j DROP)
    iptables -C "${regra[@]}" 2>/dev/null || iptables -I "${regra[@]}" || falhou=1
  done
else
  logger -t agentepessoal "firewall: rede phone não existe ainda"
fi
# 16/10: the guests' boxes (caixa_convidados.py, network "caixas") get the internet and nothing else: no port of
# the host (model proxy, bridge, the boxes' own service), no private range (the agent's container, the VPC) and no
# cloud metadata. caixa_convidados.py runs this before starting any box and refuses to run if it fails.
CAIXAS=$(docker network inspect caixas -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
if [ -n "$CAIXAS" ]; then
  regra=(INPUT -s "$CAIXAS" -j DROP)
  iptables -C "${regra[@]}" 2>/dev/null || iptables -I "${regra[@]}" || falhou=1
  for destino in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10; do
    regra=(DOCKER-USER -s "$CAIXAS" -d "$destino" -j DROP)
    iptables -C "${regra[@]}" 2>/dev/null || iptables -I "${regra[@]}" || falhou=1
  done
fi
if [ "$falhou" -eq 0 ]; then
  logger -t agentepessoal "firewall: rede $REDE sem acesso às portas 8787-8790 do host; caixas (${CAIXAS:-ainda sem rede}) só com internet"
else
  logger -t agentepessoal "firewall: FALHOU ao fechar as portas do host para a rede $REDE"
fi
exit "$falhou"

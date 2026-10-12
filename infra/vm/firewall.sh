#!/bin/bash
# 12/10 review: the virtual phone (Docker network "phone") could reach the host's model proxy (8787), the Meta
# credentials service (8788) and the phone bridge (8789): an app installed on the phone could spend on models or get
# the short-lived AWS credentials. The agent reaches them through the default bridge (host.docker.internal), not
# through the phone network, so only traffic coming FROM the phone network to these host ports is dropped.
# Idempotent; run at boot by agentepessoal-firewall.service (after docker) and by setup.sh.
set -u
PORTAS=8787,8788,8789
REDE=$(docker network inspect phone -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
[ -n "$REDE" ] || { logger -t agentepessoal "firewall: rede phone não existe ainda"; exit 0; }
REGRA=(INPUT -s "$REDE" -p tcp -m multiport --dports "$PORTAS" -j DROP)
iptables -C "${REGRA[@]}" 2>/dev/null || iptables -I "${REGRA[@]}"
logger -t agentepessoal "firewall: rede $REDE sem acesso às portas $PORTAS do host"

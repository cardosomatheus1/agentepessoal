#!/bin/bash
# 12/10 review: the virtual phone (Docker network "phone") could reach the host's model proxy (8787), the Meta
# credentials service (8788) and the phone bridge (8789): an app installed on the phone could spend on models or get
# the short-lived AWS credentials. The agent reaches them through the default bridge (host.docker.internal), not
# through the phone network, so only traffic coming FROM the phone network to these host ports is dropped.
# One rule per port (this kernel has no "multiport" match). Idempotent; run at boot by agentepessoal-firewall.service
# (after docker) and by setup.sh. Exits non-zero, and says so in the log, when a rule could not be added.
set -u
REDE=$(docker network inspect phone -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
[ -n "$REDE" ] || { logger -t agentepessoal "firewall: rede phone não existe ainda"; exit 0; }
falhou=0
for porta in 8787 8788 8789; do
  regra=(INPUT -s "$REDE" -p tcp --dport "$porta" -j DROP)
  iptables -C "${regra[@]}" 2>/dev/null || iptables -I "${regra[@]}" || falhou=1
done
if [ "$falhou" -eq 0 ]; then
  logger -t agentepessoal "firewall: rede $REDE sem acesso às portas 8787, 8788 e 8789 do host"
else
  logger -t agentepessoal "firewall: FALHOU ao fechar as portas do host para a rede $REDE"
fi
exit "$falhou"

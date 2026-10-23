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
  for porta in 8787 8788 8789 8790 8791 8792; do
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
# 20/10: the delegates' boxes (caixa_delegados.py, network "delegados": Hermes/OpenClaw with their tools) get the
# internet and, of the host, only the relay port 8792 (model + search); the ACCEPT must sit above the DROP.
DELEGADOS=$(docker network inspect delegados -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
if [ -n "$DELEGADOS" ]; then
  regra=(INPUT -s "$DELEGADOS" -j DROP)
  iptables -C "${regra[@]}" 2>/dev/null || iptables -I "${regra[@]}" || falhou=1
  aceita=(INPUT -s "$DELEGADOS" -p tcp --dport 8792 -j ACCEPT)
  iptables -C "${aceita[@]}" 2>/dev/null && iptables -D "${aceita[@]}"
  iptables -I "${aceita[@]}" || falhou=1
  for destino in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10; do
    regra=(DOCKER-USER -s "$DELEGADOS" -d "$destino" -j DROP)
    iptables -C "${regra[@]}" 2>/dev/null || iptables -I "${regra[@]}" || falhou=1
  done
fi
# 23/10 (migração): o Hermes principal (rede "hermes", infra/vm/hermes/subir.sh) tem a internet e, do host, só o proxy
# do modelo (8787) e as respostas das conexões que o host abriu com ele (a porta 8642 publicada); nada do A0, da VPC,
# do serviço de credenciais (8788), da ponte do celular (8789) nem dos metadados da nuvem (revisão OpenCode 23/10).
HERMES=$(docker network inspect hermes -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
if [ -n "$HERMES" ]; then
  regra=(INPUT -s "$HERMES" -j DROP)
  iptables -C "${regra[@]}" 2>/dev/null || iptables -I "${regra[@]}" || falhou=1
  for aceita in "-p tcp --dport 8787" "-m state --state ESTABLISHED,RELATED"; do  # acima do DROP
    # shellcheck disable=SC2206
    a=(INPUT -s "$HERMES" $aceita -j ACCEPT)
    iptables -C "${a[@]}" 2>/dev/null && iptables -D "${a[@]}"
    iptables -I "${a[@]}" || falhou=1
  done
  for destino in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10; do
    regra=(DOCKER-USER -s "$HERMES" -d "$destino" -j DROP)
    iptables -C "${regra[@]}" 2>/dev/null || iptables -I "${regra[@]}" || falhou=1
  done
  # 23/10 (fase 4): dentro da rede, o Hermes só fala com o CDP do navegador dele (hermes/navegador.sh, IP .0.250) e o
  # navegador só responde; o resto da rede privada segue fechado para os dois (acima dos DROPs)
  NAV="${HERMES%.*.*}.0.250"
  for aceita in "-s $HERMES -d $NAV/32 -p tcp --dport 9222" "-s $NAV/32 -d $HERMES -m state --state ESTABLISHED,RELATED"; do
    # shellcheck disable=SC2206
    a=(DOCKER-USER $aceita -j ACCEPT)
    iptables -C "${a[@]}" 2>/dev/null && iptables -D "${a[@]}"
    iptables -I "${a[@]}" || falhou=1
  done
fi
if [ "$falhou" -eq 0 ]; then
  logger -t agentepessoal "firewall: rede $REDE sem acesso às portas 8787-8790 do host; caixas (${CAIXAS:-ainda sem rede}) só com internet"
else
  logger -t agentepessoal "firewall: FALHOU ao fechar as portas do host para a rede $REDE"
fi
exit "$falhou"

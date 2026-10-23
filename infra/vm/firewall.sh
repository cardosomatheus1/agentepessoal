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
# Virada (fase 8, "padrao": "hermes" em /var/lib/agentepessoal/destino.json): o Hermes passa a ser o agente, então ganha
# o que o A0 tinha do host: credenciais Meta (8788), ponte do celular (8789), caixas dos convidados (8790) e dos
# delegados (8791), e o celular Android (IP fixo .0.252 na rede dele, só a porta do adb; o celular não abre nada no
# Hermes nem no host). Os convidados (redes "hermes-<login>", hermes/convidado.sh) só o modelo, a ponte e a caixa deles.
# Voltar ao ensaio tira essas regras de novo.
VIRADA=0
python3 -c 'import json,sys; sys.exit(0 if json.load(open("/var/lib/agentepessoal/destino.json")).get("padrao") == "hermes" else 1)' \
  2>/dev/null && VIRADA=1
aceitar_input() {  # $1 rede, $2 porta, $3 1=pôr / 0=tirar (acima do DROP da rede)
  local a=(INPUT -s "$1" -p tcp --dport "$2" -j ACCEPT)
  iptables -C "${a[@]}" 2>/dev/null && iptables -D "${a[@]}"
  if [ "$3" = 1 ]; then iptables -I "${a[@]}" || falhou=1; fi
}
regra_user() {  # $1 1=pôr / 0=tirar, resto: a regra do DOCKER-USER sem o -j
  local por="$1"; shift
  local a=(DOCKER-USER "$@")
  iptables -C "${a[@]}" 2>/dev/null && iptables -D "${a[@]}"
  if [ "$por" = 1 ]; then iptables -I "${a[@]}" || falhou=1; fi
}
for rede in $(docker network ls --format '{{.Name}}' 2>/dev/null | grep -E '^hermes(-[a-z0-9_-]+)?$'); do
  SUB=$(docker network inspect "$rede" -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
  [ -n "$SUB" ] || continue
  regra=(INPUT -s "$SUB" -j DROP)
  iptables -C "${regra[@]}" 2>/dev/null || iptables -I "${regra[@]}" || falhou=1
  aceitar_input "$SUB" 8787 1
  a=(INPUT -s "$SUB" -m state --state ESTABLISHED,RELATED -j ACCEPT)
  iptables -C "${a[@]}" 2>/dev/null && iptables -D "${a[@]}"
  iptables -I "${a[@]}" || falhou=1
  if [ "$rede" = hermes ]; then portas="8788 8789 8790 8791"; else portas="8789 8790"; fi
  for porta in 8788 8789 8790 8791; do
    case " $portas " in *" $porta "*) aceitar_input "$SUB" "$porta" "$VIRADA" ;; *) aceitar_input "$SUB" "$porta" 0 ;; esac
  done
  for destino in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10; do
    regra=(DOCKER-USER -s "$SUB" -d "$destino" -j DROP)
    iptables -C "${regra[@]}" 2>/dev/null || iptables -I "${regra[@]}" || falhou=1
  done
  # 23/10 (fase 4): dentro da rede, o Hermes só fala com o CDP do navegador dele (navegador.sh, IP .0.250, porta 9223)
  # e o navegador só responde; o resto da rede privada segue fechado (acima dos DROPs)
  NAV="${SUB%.*.*}.0.250"
  regra_user 1 -s "$SUB" -d "$NAV/32" -p tcp --dport 9223 -j ACCEPT
  regra_user 1 -s "$NAV/32" -d "$SUB" -m state --state ESTABLISHED,RELATED -j ACCEPT
  if [ "$rede" = hermes ]; then
    MCP="${SUB%.*.*}.0.251"  # os conectores (hermes/mcp.sh): Google 8765, repasse do GitHub 8766
    regra_user 1 -s "$SUB" -d "$MCP/32" -p tcp --dport 8765 -j ACCEPT
    regra_user 1 -s "$SUB" -d "$MCP/32" -p tcp --dport 8766 -j ACCEPT
    regra_user 1 -s "$MCP/32" -d "$SUB" -m state --state ESTABLISHED,RELATED -j ACCEPT
    AND="${SUB%.*.*}.0.252"  # o celular Android (na virada, hermes/subir.sh o liga nesta rede)
    regra_user "$VIRADA" -s "$AND/32" -d "$SUB" -j DROP
    regra_user "$VIRADA" -s "$AND/32" -d "$SUB" -m state --state ESTABLISHED,RELATED -j ACCEPT
    regra_user "$VIRADA" -s "$SUB" -d "$AND/32" -p tcp --dport 5555 -j ACCEPT
    a=(INPUT -s "$AND/32" -j DROP)  # do celular, nada do host por esta rede (acima dos ACCEPTs da rede)
    iptables -C "${a[@]}" 2>/dev/null && iptables -D "${a[@]}"
    [ "$VIRADA" = 1 ] && { iptables -I "${a[@]}" || falhou=1; }
  fi
done
if [ "$falhou" -eq 0 ]; then
  logger -t agentepessoal "firewall: rede $REDE sem acesso às portas 8787-8790 do host; caixas (${CAIXAS:-ainda sem rede}) só com internet"
else
  logger -t agentepessoal "firewall: FALHOU ao fechar as portas do host para a rede $REDE"
fi
exit "$falhou"

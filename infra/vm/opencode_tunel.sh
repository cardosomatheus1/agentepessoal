#!/bin/bash
# Túnel do OpenCode do Matheus (opencodemobile.service, 127.0.0.1:4096, com a senha do próprio OpenCode).
# 23/10: o túnel rápido (trycloudflare.com) muda de endereço a cada boot e dá 530 com a VM fora. Dois modos:
#  - endereço fixo: com o token de um túnel nomeado da Cloudflare do Matheus no cofre dele
#    (/senha CLOUDFLARE_TUNEL_OPENCODE <token>; opcional /senha OPENCODE_ENDERECO opencode.seudominio.com.br),
#    roda `cloudflared tunnel run` com esse token (o endereço e o destino http://localhost:4096 ficam no painel dele);
#  - sem token: o túnel rápido de antes.
# 24/10 (Matheus: "não tem como botar um túnel fixo pelo AWS?"): acima dos dois, o endereço fixo da AWS (CloudFront ->
# VPC origin -> porta 4097 da VM -> 4096; infra/opencode_aws.py grava o endereço em /agentepessoal/opencode/url-aws e
# opencodemobile-aws.socket abre a porta só na interface da VPC). Quando ele existe e responde (401 sem senha em
# /api/session, da internet), é ele que vai para o celular. O túnel do Cloudflare continua no ar só como reserva: se o
# da AWS falhar 3 minutos seguidos, o endereço da reserva é publicado (e avisado) até o da AWS voltar.
# Em todos, o endereço do momento vai para o SSM /agentepessoal/opencode/url (a página de controle mostra
# "Abrir OpenCode"). Uso: opencode_tunel.sh rodar   (opencodemobile-cloudflare.service, como root: lê o cofre e roda
# o cloudflared como opencodemobile) | opencode_tunel.sh publicar   (opencodemobile-publish-url.timer, a cada minuto)
set -u
COFRE="${COFRE:-/opt/a0/usr/segredos/matheus.json}"
PARAM=/agentepessoal/opencode/url
UNIDADE=opencodemobile-cloudflare.service
USUARIO=opencodemobile
ENDERECO_PADRAO=opencode.raizconnect.com.br
PARAM_AWS=/agentepessoal/opencode/url-aws
ESTADO="${ESTADO:-/var/lib/agentepessoal}"
FALHAS_PARA_RESERVA=3
AWS="${AWS:-/usr/local/bin/aws}"
[ -x "$AWS" ] || AWS=aws
CURL="${CURL:-curl}"

segredo() {  # valor de um nome do cofre (JSON {NOME: valor}); vazio se não houver
  python3 -c 'import json,sys
try: print(json.load(open(sys.argv[1])).get(sys.argv[2], "").strip())
except Exception: print("")' "$COFRE" "$1"
}

endereco_fixo() {  # https://<host> no modo fixo; vazio no rápido
  [ -n "$(segredo CLOUDFLARE_TUNEL_OPENCODE)" ] || return 0
  local host
  host=$(segredo OPENCODE_ENDERECO)
  host=${host#https://}; host=${host%%/*}
  echo "https://${host:-$ENDERECO_PADRAO}"
}

endereco_rapido() {  # o último trycloudflare desde que o túnel subiu (não o de antes de um reinício)
  local desde
  desde=$(systemctl show -p ActiveEnterTimestamp --value "$UNIDADE" 2>/dev/null)
  [ -n "$desde" ] || return 0
  journalctl -u "$UNIDADE" --since "$desde" --no-pager -o cat 2>/dev/null \
    | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1
}

endereco_aws() {  # $1 o endereço fixo da AWS (SSM), $2 o publicado agora; ecoa $1 se responde, vazio se não.
  local url="$1" codigo falhas_arq="$ESTADO/opencode-aws-falhas"
  printf '%s\n' "$url" | grep -Eq '^https://[a-z0-9.-]+$' || return 0
  codigo=$($CURL -s -o /dev/null -w '%{http_code}' -m 15 --retry 1 "$url/api/session" 2>/dev/null || :)
  mkdir -p "$ESTADO" 2>/dev/null || :
  if [ "$codigo" = 401 ] || [ "$codigo" = 200 ]; then
    rm -f "$falhas_arq"
    echo "$url"
    return 0
  fi
  local n
  n=$(( $(cat "$falhas_arq" 2>/dev/null || echo 0) + 1 ))
  echo "$n" > "$falhas_arq"
  logger -t agentepessoal "opencode: endereço da AWS não respondeu ($codigo), falha $n seguida"
  # já publicado: até a 3ª falha seguida continua com ele (um tropeço, ou o OpenCode subindo, não troca o endereço do
  # celular). Ainda não publicado (24/10: a distribuição recém-criada levou 5 min para responder): só quando responder.
  [ "$2" = "$url" ] && [ "$n" -lt "$FALHAS_PARA_RESERVA" ] && echo "$url"
  return 0
}

avisar() {  # 24/10 (Matheus: "sempre que trocar, falar o novo no Telegram"): o endereço novo vai ao celular dele
  if [ -n "${AVISAR:-}" ]; then "$AVISAR" "$@"; return; fi
  python3 - "$@" <<'PY' || logger -t agentepessoal "opencode: aviso do endereço novo não saiu"
import json, sys, urllib.request
url = sys.argv[1]
chave = open("/opt/a0/usr/whatsapp/.chave").read().strip()
texto = (f"🔗 O endereço do OpenCode mudou. Novo:\n{url}\n\nA senha é a mesma. Para ele parar de mudar, falta o "
         "túnel fixo na sua Cloudflare (/senha CLOUDFLARE_TUNEL_OPENCODE <token>).")
if url.endswith("trycloudflare.com") is False:
    texto = f"🔗 O OpenCode agora está no endereço fixo:\n{url}\n\nA senha é a mesma; este não muda mais."
elif len(sys.argv) > 2 and sys.argv[2] == "reserva":
    texto = (f"⚠️ O endereço fixo do OpenCode não está respondendo. Enquanto isso, use este (provisório):\n{url}\n\n"
             "A senha é a mesma. Quando o fixo voltar, eu aviso.")
req = urllib.request.Request("http://127.0.0.1:8789/enviar", data=json.dumps(
    {"usuario": "matheus", "texto": texto, "tipo": "resposta"}).encode(),
    headers={"Content-Type": "application/json", "X-Chave": chave})
urllib.request.urlopen(req, timeout=30).read()
PY
}

publicar() {
  local url atual
  if [ -n "$(segredo CLOUDFLARE_TUNEL_OPENCODE)" ] && [ -n "$(endereco_rapido)" ]; then
    # o token acabou de chegar ao cofre e o túnel ainda é o rápido: passa para o fixo (o endereço muda uma última vez)
    logger -t agentepessoal "opencode: token no cofre, trocando o túnel rápido pelo fixo"
    systemctl restart "$UNIDADE"
  fi
  local aws_url reserva=""
  atual=$($AWS ssm get-parameter --region us-east-1 --name "$PARAM" --query Parameter.Value --output text 2>/dev/null || :)
  aws_url=$($AWS ssm get-parameter --region us-east-1 --name "$PARAM_AWS" --query Parameter.Value --output text 2>/dev/null || :)
  url=$(endereco_aws "$aws_url" "$atual")
  if [ -z "$url" ]; then
    url=$(endereco_fixo)
    [ -n "$url" ] || url=$(endereco_rapido)
    [ -n "$url" ] || exit 0
    [ "$atual" = "$aws_url" ] && reserva=reserva  # caiu do fixo que o celular usava: o aviso diz que é provisório
  fi
  printf '%s\n' "$url" | grep -Eq '^https://[a-z0-9.-]+$' || exit 2
  if [ "$url" != "$atual" ]; then
    $AWS ssm put-parameter --region us-east-1 --name "$PARAM" --type String --overwrite --value "$url" >/dev/null
    logger -t agentepessoal "opencode: endereço publicado $url"
    avisar "$url" $reserva
  fi
}

rodar() {
  local token
  token=$(segredo CLOUDFLARE_TUNEL_OPENCODE)
  if [ -n "$token" ]; then
    logger -t agentepessoal "opencode: túnel nomeado ($(endereco_fixo))"
    publicar || true
    export TUNNEL_TOKEN="$token"  # pelo ambiente, nunca na linha de comando (ps)
    exec setpriv --reuid="$USUARIO" --regid="$USUARIO" --init-groups --no-new-privs \
      /usr/bin/cloudflared tunnel --no-autoupdate run
  fi
  logger -t agentepessoal "opencode: túnel rápido (sem CLOUDFLARE_TUNEL_OPENCODE no cofre)"
  exec setpriv --reuid="$USUARIO" --regid="$USUARIO" --init-groups --no-new-privs \
    /usr/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:4096
}

case "${1:-}" in
  rodar) rodar ;;
  publicar) publicar ;;
  *) echo "uso: $0 rodar|publicar" >&2; exit 64 ;;
esac

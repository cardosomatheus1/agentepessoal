#!/bin/bash
# Túnel do OpenCode do Matheus (opencodemobile.service, 127.0.0.1:4096, com a senha do próprio OpenCode).
# 23/10: o túnel rápido (trycloudflare.com) muda de endereço a cada boot e dá 530 com a VM fora. Dois modos:
#  - endereço fixo: com o token de um túnel nomeado da Cloudflare do Matheus no cofre dele
#    (/senha CLOUDFLARE_TUNEL_OPENCODE <token>; opcional /senha OPENCODE_ENDERECO opencode.seudominio.com.br),
#    roda `cloudflared tunnel run` com esse token (o endereço e o destino http://localhost:4096 ficam no painel dele);
#  - sem token: o túnel rápido de antes.
# Nos dois, o endereço do momento vai para o SSM /agentepessoal/opencode/url (a página de controle mostra
# "Abrir OpenCode"). Uso: opencode_tunel.sh rodar   (opencodemobile-cloudflare.service, como root: lê o cofre e roda
# o cloudflared como opencodemobile) | opencode_tunel.sh publicar   (opencodemobile-publish-url.timer, a cada minuto)
set -u
COFRE="${COFRE:-/opt/a0/usr/segredos/matheus.json}"
PARAM=/agentepessoal/opencode/url
UNIDADE=opencodemobile-cloudflare.service
USUARIO=opencodemobile
ENDERECO_PADRAO=opencode.raizconnect.com.br
AWS="${AWS:-/usr/local/bin/aws}"
[ -x "$AWS" ] || AWS=aws

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

avisar() {  # 24/10 (Matheus: "sempre que trocar, falar o novo no Telegram"): o endereço novo vai ao celular dele
  if [ -n "${AVISAR:-}" ]; then "$AVISAR" "$1"; return; fi
  python3 - "$1" <<'PY' || logger -t agentepessoal "opencode: aviso do endereço novo não saiu"
import json, sys, urllib.request
url = sys.argv[1]
chave = open("/opt/a0/usr/whatsapp/.chave").read().strip()
texto = (f"🔗 O endereço do OpenCode mudou. Novo:\n{url}\n\nA senha é a mesma. Para ele parar de mudar, falta o "
         "túnel fixo na sua Cloudflare (/senha CLOUDFLARE_TUNEL_OPENCODE <token>).")
if url.endswith("trycloudflare.com") is False:
    texto = f"🔗 O OpenCode agora está no endereço fixo:\n{url}\n\nA senha é a mesma; este não muda mais."
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
  url=$(endereco_fixo)
  [ -n "$url" ] || url=$(endereco_rapido)
  [ -n "$url" ] || exit 0
  printf '%s\n' "$url" | grep -Eq '^https://[a-z0-9.-]+$' || exit 2
  atual=$($AWS ssm get-parameter --region us-east-1 --name "$PARAM" --query Parameter.Value --output text 2>/dev/null || :)
  if [ "$url" != "$atual" ]; then
    $AWS ssm put-parameter --region us-east-1 --name "$PARAM" --type String --overwrite --value "$url" >/dev/null
    logger -t agentepessoal "opencode: endereço publicado $url"
    avisar "$url"
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

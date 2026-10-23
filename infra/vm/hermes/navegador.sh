#!/bin/bash
# O navegador logado do Hermes (migração, fase 4): um Chromium próprio, sem tela, exposto por CDP só na rede do Hermes
# (o Hermes liga nele por BROWSER_CDP_URL; as ferramentas browser_* dele abrem abas nele, com os logins do perfil).
# Até a virada (fase 8) ele usa uma CÓPIA do perfil do A0 (Instagram, Google, Meta…): o A0 segue usando o dele, nada
# muda para o Matheus, e no ensaio o Hermes só lê (acesso_hermes.py bloqueia clicar/digitar/teclar). Na virada
# (--proprio) ele abre o perfil de verdade (/opt/a0/usr/navegador/sessions/<perfil>, o A0 parado), como root, para os
# arquivos continuarem do jeito que o A0 deixa (a volta ao A0 acha o perfil como estava, com os logins renovados).
# Como o A0 rodava (23/10, Matheus: "no outro agente não tinha problema com Cloudflare, ia tudo; com Hermes não passa
# nenhum"): o Chromium COM tela, num Xvfb dentro do container (tela 1920x1080, janela 1280x900), com as opções que o
# patchright do A0 passava (sem --headless, AutomationControlled desligado). O toque do "Resolver aqui" chega como mouse
# de verdade do X e o quadro vem da tela do X (cdp_encaminhar.py, /tela/*): o clique sintético do CDP num navegador sem
# tela levava "Verification failed" do Cloudflare, e com tela o print por CDP de página com Cloudflare trava. Com tela o
# agente de usuário já é o do Chrome (o WhatsApp Web recusava o "HeadlessChrome"). Mesmo binário do A0 (chromium-1228, copiado do container dele uma vez, só leitura) e as mesmas opções de senha
# (--password-store=basic --use-mock-keychain), para os cookies do perfil abrirem. Idempotente; roda como root no host,
# chamado pelo subir.sh (e pelo convidado.sh, um por convidado) depois da rede existir. Imprime o endereço CDP na última
# linha (NAVEGADOR_CDP=...).
#   navegador.sh IMAGEM [--nome hermes-navegador] [--rede hermes] [--ip-final 250] [--perfil shared] [--proprio]
#                       [--renovar-perfil]
set -euo pipefail
IMAGEM="${1:?imagem do Hermes}"; shift || true
NOME=hermes-navegador; REDE=hermes; FINAL=250; PERFIL=shared; PROPRIO=0; RENOVAR=0
while [ $# -gt 0 ]; do
  case "$1" in
    --nome) NOME="$2"; shift 2 ;;
    --rede) REDE="$2"; shift 2 ;;
    --ip-final) FINAL="$2"; shift 2 ;;
    --perfil) PERFIL="$2"; shift 2 ;;
    --proprio) PROPRIO=1; shift ;;
    --renovar-perfil) RENOVAR=1; shift ;;
    *) echo "opção desconhecida: $1"; exit 2 ;;
  esac
done
BASE=/opt/hermes/navegador
BIN_A0=/a0/tmp/playwright/chromium-1228
PERFIL_A0="/opt/a0/usr/navegador/sessions/$PERFIL"
mkdir -p "$BASE"; chmod 700 "$BASE"
if [ ! -x "$BASE/chromium-1228/chrome-linux/chrome" ]; then
  docker cp "agent-zero:$BIN_A0" "$BASE/chromium-1228.tmp" && mv "$BASE/chromium-1228.tmp" "$BASE/chromium-1228"
fi
if [ "$PROPRIO" = 1 ]; then
  mkdir -p "$PERFIL_A0"
  ORIGEM="$PERFIL_A0"; USUARIO=0:0
else
  COPIA="$BASE/perfil"; [ "$PERFIL" = shared ] || COPIA="$BASE/perfil-$PERFIL"
  if [ ! -d "$COPIA" ] || [ "$RENOVAR" = 1 ]; then
    rm -rf "$COPIA.novo"
    # caches e travas ficam de fora (Singleton* faria o Chromium achar que o perfil já está aberto)
    rsync -a --exclude 'Singleton*' --exclude '*Cache*' --exclude 'Service Worker/CacheStorage' --exclude 'BrowserMetrics*' \
      "$PERFIL_A0/" "$COPIA.novo/"
    [ -d "$COPIA" ] && { rm -rf "$COPIA.anterior"; mv "$COPIA" "$COPIA.anterior"; }
    mv "$COPIA.novo" "$COPIA"
  fi
  chown -R 10000:10000 "$COPIA"
  ORIGEM="$COPIA"; USUARIO=10000:10000
fi
SUB=$(docker network inspect "$REDE" -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}')
IP="${SUB%.*.*}.0.$FINAL"   # 172.22.0.0/16 -> 172.22.0.250 (o CDP só aceita Host com IP, então endereço fixo)
AQUI="$(cd "$(dirname "$0")" && pwd)"
install -m 644 "$AQUI/cdp_encaminhar.py" "$BASE/cdp_encaminhar.py"
docker rm -f "$NOME" >/dev/null 2>&1 || true
# O Chromium só escuta no loopback do container: o repasse (cdp_encaminhar.py) expõe a porta 9223 na rede.
# A trava do perfil (Singleton*) sai a cada subida: o container novo tem outro nome de máquina e o Chromium recusaria.
docker run -d --name "$NOME" --restart no --network "$REDE" --ip "$IP" \
  --memory 2g --memory-swap 2g --shm-size 512m \
  --user "$USUARIO" \
  -v "$BASE/chromium-1228:/opt/chromium:ro" -v "$ORIGEM:/perfil" -v "$BASE/cdp_encaminhar.py:/opt/cdp_encaminhar.py:ro" \
  --entrypoint /bin/sh \
  "$IMAGEM" -c 'rm -f /perfil/Singleton*; rm -f /tmp/.X99-lock; \
  Xvfb :99 -screen 0 1920x1080x24 +extension GLX +extension RANDR +extension RENDER +extension Composite \
    -nolisten tcp -noreset -ac >/dev/null 2>&1 & \
  for i in 1 2 3 4 5 6 7 8 9 10; do [ -e /tmp/.X11-unix/X99 ] && break; sleep 0.5; done; \
  DISPLAY=:99 /opt/chromium/chrome-linux/chrome --no-sandbox --disable-dev-shm-usage \
  --window-position=0,0 --window-size=1280,900 --disable-blink-features=AutomationControlled \
  --disable-field-trial-config --disable-background-networking --disable-background-timer-throttling \
  --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --disable-hang-monitor \
  --disable-prompt-on-repost --force-color-profile=srgb --no-service-autorun --disable-search-engine-choice-screen \
  --disable-infobars --disable-sync --hide-crash-restore-bubble \
  --password-store=basic --use-mock-keychain --no-first-run --no-default-browser-check \
  --disable-breakpad --disable-notifications \
  --user-data-dir=/perfil --remote-debugging-port=9222 about:blank & \
  DISPLAY=:99 TELA_X=1 exec python3 /opt/cdp_encaminhar.py 9223' >/dev/null
for i in $(seq 1 30); do
  docker exec "$NOME" python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:9223/json/version',timeout=2)" \
    >/dev/null 2>&1 && break
  sleep 1
done
echo "NAVEGADOR_CDP=http://$IP:9223"

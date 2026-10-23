#!/bin/bash
# O navegador logado do Hermes (migração, fase 4): um Chromium próprio, sem tela, exposto por CDP só na rede "hermes"
# (o Hermes liga nele por BROWSER_CDP_URL; as ferramentas browser_* dele abrem abas nele, com os logins do perfil).
# Até a virada (fase 8) ele usa uma CÓPIA do perfil "shared" do A0 (Instagram, Google, Meta…): o A0 segue usando o
# dele, nada muda para o Matheus, e no ensaio o Hermes só lê (acesso_hermes.py bloqueia clicar/digitar/teclar).
# Mesmo binário do A0 (chromium-1228, copiado do container dele, só leitura) e as mesmas opções de senha
# (--password-store=basic --use-mock-keychain), para os cookies do perfil abrirem. Idempotente; roda como root no host,
# chamado pelo subir.sh depois da rede "hermes" existir. Imprime o endereço CDP na última linha (NAVEGADOR_CDP=...).
#   --renovar-perfil   copia o perfil de novo (o anterior vai para perfil.anterior)
set -euo pipefail
BASE=/opt/hermes/navegador
BIN_A0=/a0/tmp/playwright/chromium-1228
PERFIL_A0=/opt/a0/usr/navegador/sessions/shared
IMAGEM="${1:?imagem do Hermes}"; shift || true
mkdir -p "$BASE"; chmod 700 "$BASE"
if [ ! -x "$BASE/chromium-1228/chrome-linux/chrome" ]; then
  docker cp "agent-zero:$BIN_A0" "$BASE/chromium-1228.tmp" && mv "$BASE/chromium-1228.tmp" "$BASE/chromium-1228"
fi
if [ ! -d "$BASE/perfil" ] || [ "${1:-}" = "--renovar-perfil" ]; then
  rm -rf "$BASE/perfil.novo"
  # caches e travas ficam de fora (Singleton* faria o Chromium achar que o perfil já está aberto)
  rsync -a --exclude 'Singleton*' --exclude '*Cache*' --exclude 'Service Worker/CacheStorage' --exclude 'BrowserMetrics*' \
    "$PERFIL_A0/" "$BASE/perfil.novo/"
  [ -d "$BASE/perfil" ] && { rm -rf "$BASE/perfil.anterior"; mv "$BASE/perfil" "$BASE/perfil.anterior"; }
  mv "$BASE/perfil.novo" "$BASE/perfil"
fi
chown -R 10000:10000 "$BASE/perfil"
SUB=$(docker network inspect hermes -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}')
IP="${SUB%.*.*}.0.250"   # 172.22.0.0/16 -> 172.22.0.250 (o CDP só aceita Host com IP, então endereço fixo)
AQUI="$(cd "$(dirname "$0")" && pwd)"
install -m 644 "$AQUI/cdp_encaminhar.py" "$BASE/cdp_encaminhar.py"
docker rm -f hermes-navegador >/dev/null 2>&1 || true
# O Chromium sem tela só escuta no loopback do container: o repasse (cdp_encaminhar.py) expõe a porta 9223 na rede hermes.
# A trava do perfil (Singleton*) sai a cada subida: o container novo tem outro nome de máquina e o Chromium recusaria.
docker run -d --name hermes-navegador --restart no --network hermes --ip "$IP" \
  --memory 2g --memory-swap 2g --shm-size 512m \
  --user 10000:10000 \
  -v "$BASE/chromium-1228:/opt/chromium:ro" -v "$BASE/perfil:/perfil" -v "$BASE/cdp_encaminhar.py:/opt/cdp_encaminhar.py:ro" \
  --entrypoint /bin/sh \
  "$IMAGEM" -c 'rm -f /perfil/Singleton*; /opt/chromium/chrome-linux/chrome --headless=new --no-sandbox --disable-dev-shm-usage --disable-gpu \
  --password-store=basic --use-mock-keychain --no-first-run --no-default-browser-check \
  --disable-background-networking --disable-breakpad --disable-notifications \
  --user-data-dir=/perfil --remote-debugging-port=9222 about:blank & exec python3 /opt/cdp_encaminhar.py 9223' >/dev/null
for i in $(seq 1 30); do
  docker exec hermes-navegador python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:9223/json/version',timeout=2)" \
    >/dev/null 2>&1 && break
  sleep 1
done
echo "NAVEGADOR_CDP=http://$IP:9223"

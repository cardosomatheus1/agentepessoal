#!/bin/bash
# O dia de sombra do Hermes (migração, fase 7): um segundo Hermes ("hermes-sombra") roda UM DIA INTEIRO as mesmas
# rotinas do A0, nos mesmos horários, com o relógio ligado, numa CÓPIA dos dados do agente (grava na cópia, nunca nos
# dados vivos), no ensaio (nada vai ao celular de ninguém nem se publica na Meta: o que iria fica em
# /opt/hermes/sombra/data/agentepessoal/ensaio_celular.jsonl, só o operador vê), na mesma rede fechada e com os mesmos
# escondidos (cofre, chave da ponte, tokens, perfis). O navegador (só leitura no ensaio) e os conectores (Google só
# leitura) são os do Hermes de ensaio. Depois de 24 h ele para sozinho (systemd-run). Nada muda para o A0 nem para o
# Matheus.
#   sombra.sh iniciar     copia os dados, sobe, aplica as rotinas e liga as que estão ligadas no A0
#   sombra.sh conferir    o que rodou, o que falhou e o que teria ido ao celular
#   sombra.sh parar       para (os dados da cópia ficam para conferir)
set -euo pipefail
S=/opt/hermes/sombra
DUR="${HERMES_SOMBRA_HORAS:-24}h"
case "${1:-}" in
iniciar)
  IMAGEM=$(docker inspect -f '{{.Config.Image}}' hermes)
  CDP=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' hermes | sed -n 's/^BROWSER_CDP_URL=//p')
  docker rm -f hermes-sombra >/dev/null 2>&1 || true
  mkdir -p "$S"; chmod 700 "$S"
  rm -rf "$S/a0usr" "$S/data"
  # a cópia dos dados, sem o que é grande e não muda o dia (workdir, arquivos antigos) e sem o que dá poder de agir
  rsync -a --exclude /workdir --exclude /chats_arquivo --exclude /downloads --exclude /moldes.anterior \
    --exclude /navegador --exclude /navegador_visual --exclude /segredos --exclude /whatsapp/.chave --exclude /mcp \
    --exclude /.aws --exclude /celular --exclude /delegados --exclude /.env --exclude /secrets.env \
    --exclude /settings.json --exclude '/usuarios.json*' /opt/a0/usr/ "$S/a0usr/"
  mkdir -p "$S/a0usr/segredos" "$S/a0usr/mcp" "$S/a0usr/navegador" "$S/a0usr/workdir"
  chown -R 10000:10000 "$S/a0usr"
  mkdir -p "$S/data/agentepessoal"
  for f in config.yaml SOUL.md; do install -m 644 "/opt/hermes/data/$f" "$S/data/$f"; done
  cp -a /opt/hermes/data/plugins /opt/hermes/data/skills /opt/hermes/data/scripts "$S/data/"
  cp -a /opt/hermes/data/agentepessoal/rotinas_fonte /opt/hermes/data/agentepessoal/rotinas_aplicar.py \
    /opt/hermes/data/agentepessoal/rotina_rodar.py "$S/data/agentepessoal/"
  chown -R 10000:10000 "$S/data"
  docker run -d --name hermes-sombra --restart no --network hermes --memory 2500m --memory-swap 2500m \
    --add-host host.docker.internal:host-gateway \
    -v "$S/data":/opt/data -v "$S/a0usr":/a0/usr \
    -e AWS_ENDPOINT_URL_BEDROCK_RUNTIME=http://host.docker.internal:8787/hermes/bedrock \
    -e ANTHROPIC_BEDROCK_BASE_URL=http://host.docker.internal:8787/hermes/bedrock \
    -e AWS_ACCESS_KEY_ID=proxy -e AWS_SECRET_ACCESS_KEY=proxy -e AWS_REGION=us-east-1 -e AWS_EC2_METADATA_DISABLED=true \
    -e API_SERVER_ENABLED=true -e API_SERVER_HOST=0.0.0.0 -e API_SERVER_KEY="$(cat /opt/hermes/api_key)" \
    -e HERMES_TIMEZONE=America/Bahia -e AGENTEPESSOAL_ENSAIO=1 -e AGENTEPESSOAL_RELOGIO=1 \
    -e BROWSER_CDP_URL="$CDP" -p 127.0.0.1:8643:8642 "$IMAGEM" gateway run >/dev/null
  for i in $(seq 1 60); do curl -fsS -m 3 http://127.0.0.1:8643/health >/dev/null 2>&1 && break; sleep 2; done
  docker exec hermes-sombra python3 /opt/data/agentepessoal/rotinas_aplicar.py | grep "^ROTINAS_OK"
  docker exec hermes-sombra python3 -c '
import json, sys
sys.path.insert(0, "/opt/hermes")
from cron import jobs
mapa = json.load(open("/opt/data/agentepessoal/rotinas.json"))
ligadas = [k for k, v in mapa.items() if v.get("ligada_no_a0")]
for k in ligadas:
    jobs.resume_job(k)
print("SOMBRA_LIGADAS", len(ligadas), "de", len(mapa))'
  date -u +%FT%TZ > "$S/inicio"
  systemctl stop hermes-sombra-fim.timer >/dev/null 2>&1 || true
  systemd-run --quiet --unit hermes-sombra-fim --on-active="$DUR" /usr/bin/docker stop hermes-sombra
  echo "SOMBRA_OK desde $(cat "$S/inicio"), para sozinha em $DUR"
  ;;
conferir)
  echo "início: $(cat "$S/inicio" 2>/dev/null || echo '?')  container: $(docker inspect -f '{{.State.Status}}' hermes-sombra 2>/dev/null || echo 'não existe')"
  python3 - "$S" <<'PY'
import json, sqlite3, sys
from collections import Counter
from pathlib import Path
s = Path(sys.argv[1]) / "data"
try:
    jobs = json.loads((s / "cron" / "jobs.json").read_text())["jobs"]
except Exception as exc:
    jobs = []
    print("jobs.json:", exc)
mapa = json.loads((s / "agentepessoal" / "rotinas.json").read_text()) if (s / "agentepessoal" / "rotinas.json").exists() else {}
ligadas = {k for k, v in mapa.items() if v.get("ligada_no_a0")}
for j in sorted(jobs, key=lambda j: j.get("name", "")):
    if j["id"] in ligadas:
        print(f"- {j['name'][:45]:45} última: {j.get('last_run_at') or '-':32} estado: {j.get('last_status') or '-'}"
              f"{'  ERRO: ' + str(j.get('last_error'))[:120] if j.get('last_error') else ''}")
celular = s / "agentepessoal" / "ensaio_celular.jsonl"
linhas = [json.loads(l) for l in celular.read_text().splitlines()] if celular.exists() else []
print(f"teria ido ao celular: {len(linhas)} mensagem(ns); por rotina: {dict(Counter(l.get('rotina') or '-' for l in linhas))}")
PY
  docker exec hermes-sombra sh -c 'grep -h -E "relógio|rotinas:" /opt/data/logs/*.log | tail -15' 2>/dev/null || true
  ;;
parar)
  docker stop hermes-sombra >/dev/null 2>&1 || true
  systemctl stop hermes-sombra-fim.timer >/dev/null 2>&1 || true
  echo "SOMBRA_PARADA"
  ;;
*)
  echo "uso: sombra.sh iniciar|conferir|parar"; exit 2 ;;
esac

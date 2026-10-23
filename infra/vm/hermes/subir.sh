#!/bin/bash
# Sobe (ou atualiza) o Hermes ao lado do Agent Zero (fase 1 da migração, docs/MIGRACAO_HERMES.md). Idempotente.
# Roda como root no host da VM, a partir da pasta com config.yaml e SOUL.md (o implantador copia os dois).
# Dados: /opt/hermes/data (= /opt/data no container). Os dados vivos do agente (/opt/a0/usr) entram no mesmo caminho
# de hoje (/a0/usr), então os helpers dos plugins rodam sem mudar. Sem canais de mensagem nesta fase: só o API server,
# ouvindo em 127.0.0.1:8642 do host.
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
# Virada (fase 8): com "padrao": "hermes" em /var/lib/agentepessoal/destino.json o Hermes É o agente (sem o ensaio,
# dados graváveis, relógio ligado, rede e escondidos do que ele precisa, navegador no perfil de verdade, Google com as
# permissões do A0, portal gravável, celular Android e um Hermes por convidado). Sem isso: o ensaio, como até a fase 7.
# virada.sh vira e desvira (um comando cada).
VIRADA=0
python3 -c 'import json,sys; sys.exit(0 if json.load(open("/var/lib/agentepessoal/destino.json")).get("padrao") == "hermes" else 1)' \
  2>/dev/null && VIRADA=1
if [ "$VIRADA" = 1 ] && [ "$(docker inspect -f '{{.State.Running}}' agent-zero 2>/dev/null)" = true ]; then
  echo "HERMES_A0_RODANDO: na virada o A0 precisa estar parado (o perfil do navegador e as rotinas são os mesmos)"; exit 1
fi
BASE="nousresearch/hermes-agent:v0.22.2"
# A nossa imagem = a oficial + os pacotes dos helpers (imagem/Dockerfile); o rótulo muda quando o Dockerfile muda.
IMAGEM="agentepessoal/hermes:$(sha256sum "$AQUI/imagem/Dockerfile" | cut -c1-12)"
DADOS=/opt/hermes/data
mkdir -p "$DADOS"
chmod 700 /opt/hermes
install -m 644 "$AQUI/config.yaml" "$DADOS/config.yaml"
install -m 644 "$AQUI/SOUL.md" "$DADOS/SOUL.md"
# Os nossos plugins do Hermes: a pasta inteira é trocada (o que saiu do git sai daqui também).
mkdir -p "$DADOS/plugins"
for p in "$AQUI"/plugins/*/; do
  nome=$(basename "$p"); rm -rf "$DADOS/plugins/$nome"; cp -r "$p" "$DADOS/plugins/$nome"
done
# As skills do agente (fase 3), adaptadas às ferramentas do Hermes: semeadas UMA vez (a que já existe não é trocada:
# depois de semeada ela é do curador do Hermes, que melhora e poda; "Hermes primeiro", docs/MIGRACAO_HERMES.md).
SK="$DADOS/skills/agentepessoal"
mkdir -p "$SK" "$DADOS/agentepessoal"
install -m 644 "$AQUI/skills/DESCRIPTION.md" "$SK/DESCRIPTION.md"
for s in "$AQUI"/skills/*/; do
  n=$(basename "$s")
  [ -e "$SK/$n" ] || { cp -r "$s" "$SK/$n"; echo "$n $(date -u +%FT%TZ)" >> "$DADOS/agentepessoal/skills_semeadas.txt"; }
done
# As rotinas (fase 5): a fonte vai junto e o rotinas_aplicar.py (dentro do container, depois de subir) cria as novas
# PAUSADAS e atualiza as que existem sem mudar ligada/pausada. O portão das rotinas que têm um (portao.json do A0) é
# um "script" do cron do Hermes: um embrulho por rotina em scripts/.
rm -rf "$DADOS/agentepessoal/rotinas_fonte"; cp -r "$AQUI/rotinas" "$DADOS/agentepessoal/rotinas_fonte"
install -m 755 "$AQUI/rotinas_aplicar.py" "$DADOS/agentepessoal/rotinas_aplicar.py"
install -m 755 "$AQUI/rotina_rodar.py" "$DADOS/agentepessoal/rotina_rodar.py"
install -m 700 "$AQUI/sombra.sh" /opt/hermes/sombra.sh  # o dia de sombra (fase 7), rodado pelo operador
install -m 700 "$AQUI/virada.sh" /opt/hermes/virada.sh  # virar para o Hermes / voltar ao A0 (fase 8), um comando cada
install -m 755 "$AQUI/a0py" /opt/agentepessoal/a0py  # o Python dos helpers para o operador (A0 se no ar, senão Hermes)
mkdir -p "$DADOS/scripts"
install -m 644 "$AQUI/scripts/portao.py" "$DADOS/scripts/portao.py"
for u in $(python3 -c "import json;print(' '.join(k for k,v in json.load(open('/opt/a0/usr/plugins/rotinas/portao.json')).items() if isinstance(v,dict) and v.get('fontes')))" 2>/dev/null); do
  printf 'import runpy, sys\nsys.argv = ["portao.py", "%s"]\nrunpy.run_path("/opt/data/scripts/portao.py", run_name="__main__")\n' "$u" \
    > "$DADOS/scripts/portao_$u.py"
done
chown -R 10000:10000 "$SK" "$DADOS/agentepessoal" "$DADOS/scripts"
# Chave do API server: gerada uma vez, só na VM (nunca no git nem no chat).
if [ ! -s /opt/hermes/api_key ]; then
  umask 077; openssl rand -hex 32 > /opt/hermes/api_key
fi
# Constrói antes de derrubar: o Hermes fica fora o mínimo (com cache, repetir não refaz nada).
grep -q "^FROM $BASE\$" "$AQUI/imagem/Dockerfile" || { echo "HERMES_IMAGEM: o Dockerfile não parte de $BASE"; exit 1; }
docker image inspect "$IMAGEM" >/dev/null 2>&1 || docker build -q -t "$IMAGEM" "$AQUI/imagem" >/dev/null
docker rm -f hermes >/dev/null 2>&1 || true  # antes de remontar a vista: nada a segurando
for c in $(docker ps -a --format '{{.Names}}' | grep -E '^hermes-' | grep -vE '^hermes-(navegador|mcp|sombra)' || true); do
  docker rm -f "$c" >/dev/null 2>&1 || true  # os Hermes dos convidados também usam a vista (sobem de novo abaixo)
done
# Vista dos dados vivos para o Hermes (dono 10000 na vista, nada muda no disco): ver agentepessoal-hermes-dados.service.
command -v bindfs >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -q bindfs >/dev/null
install -m 644 "$AQUI/agentepessoal-hermes-dados.service" /etc/systemd/system/agentepessoal-hermes-dados.service
mkdir -p /etc/agentepessoal
if [ "$VIRADA" = 1 ]; then MODO_DADOS=rw; else MODO_DADOS=ro; fi
echo "HERMES_DADOS_MODO=$MODO_DADOS" > /etc/agentepessoal/hermes-dados.env
systemctl daemon-reload
systemctl enable -q agentepessoal-hermes-dados.service
systemctl restart agentepessoal-hermes-dados.service
for i in $(seq 1 20); do mountpoint -q /opt/hermes/a0usr && break; sleep 1; done
mountpoint -q /opt/hermes/a0usr || { echo "HERMES_SEM_DADOS: a vista /opt/hermes/a0usr não montou"; exit 1; }
# O Hermes roda o código dos plugins que está na vista: sem a trava do ensaio lá, não sobe (o plugin novo vai ao A0
# primeiro, por implantar.py; revisão OpenCode 23/10).
findmnt -no OPTIONS /opt/hermes/a0usr | tr ',' '\n' | grep -qx "$MODO_DADOS" \
  || { echo "HERMES_SEM_DADOS: a vista não está $MODO_DADOS"; exit 1; }
for f in whatsapp/helpers/ponte.py conteudo/helpers/conteudo.py; do
  grep -q AGENTEPESSOAL_ENSAIO "/opt/hermes/a0usr/plugins/$f" || { echo "HERMES_SEM_ENSAIO: $f no ar não tem a trava do ensaio; implante o plugin antes"; exit 1; }
done
# Rede própria: internet e, do host, só o proxy do modelo (firewall.sh); sem a regra no lugar, não sobe.
docker network inspect hermes >/dev/null 2>&1 || docker network create hermes >/dev/null
/opt/agentepessoal/firewall.sh || { echo "HERMES_SEM_FIREWALL: a rede do Hermes não ficou fechada"; exit 1; }
iptables -C INPUT -s "$(docker network inspect hermes -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}')" -j DROP 2>/dev/null \
  || { echo "HERMES_SEM_FIREWALL: firewall.sh no ar não conhece a rede hermes (implante --host antes)"; exit 1; }
# O navegador logado do Hermes (fase 4): Chromium próprio com uma cópia do perfil do A0, CDP só na rede hermes.
if [ "$VIRADA" = 1 ]; then NAV_OPC=(--proprio); else NAV_OPC=(); fi
CDP=$(bash "$AQUI/navegador.sh" "$IMAGEM" "${NAV_OPC[@]}" | sed -n 's/^NAVEGADOR_CDP=//p')
[ -n "$CDP" ] || { echo "HERMES_SEM_NAVEGADOR: o navegador do Hermes não subiu"; exit 1; }
# Os conectores (fase 3): Google e GitHub num container ao lado, com os tokens só lá.
if [ "$VIRADA" = 1 ]; then  # as permissões do A0 (agentepessoal-google-mcp.service): Drive/Docs/Planilhas com escrita
  export HERMES_GOOGLE_PERMISSOES="gmail:readonly calendar:readonly drive:full docs:full sheets:full"
fi
bash "$AQUI/mcp.sh" | grep -q "^MCP_OK" || { echo "HERMES_SEM_MCP: os conectores do Hermes não subiram"; exit 1; }
# No ensaio, o que dá poder de agir fora das ferramentas aparece vazio no container: chave da ponte do celular, cofre,
# chaves e login do A0, credenciais AWS, perfis logados do navegador, tokens dos conectores, celular e caixas.
ESCONDIDOS=()
for caminho in /opt/hermes/a0usr/.env /opt/hermes/a0usr/secrets.env /opt/hermes/a0usr/settings.json /opt/hermes/a0usr/usuarios.json*; do
  f=$(basename "$caminho")
  [ -f "$caminho" ] && ESCONDIDOS+=(-v "/dev/null:/a0/usr/$f:ro")  # (vista só leitura: não cria o que falta)
done
# .time_travel e workdir guardam instantâneos e perfis de navegador logados (iFood…); chats e chats_arquivo, tokens
# colados em conversas antigas (EAA… da Meta); .tmp e caixa, o que é de outros (revisão OpenCode 23/10, fase 7)
# Na virada o Hermes é o agente: vê o que o A0 via (cofre, chave da ponte, caixas, conversas antigas para o `lembrar`),
# menos as chaves e logins do próprio A0 (acima), os perfis logados (só os navegadores abrem) e os tokens dos conectores
# (ficam no hermes-mcp).
if [ "$VIRADA" = 1 ]; then
  PASTAS_ESCONDIDAS="navegador navegador_visual mcp .time_travel"
else
  PASTAS_ESCONDIDAS=".aws whatsapp segredos navegador navegador_visual mcp celular delegados .time_travel .tmp workdir caixa chats chats_arquivo"
fi
for d in $PASTAS_ESCONDIDAS; do
  [ -d "/opt/hermes/a0usr/$d" ] && ESCONDIDOS+=(--mount "type=tmpfs,destination=/a0/usr/$d,tmpfs-mode=0755")
done
if [ "$VIRADA" = 1 ]; then
  MODO_ENV=(-e AGENTEPESSOAL_RELOGIO=1)
else
  MODO_ENV=(-e AGENTEPESSOAL_ENSAIO=1)
fi
# AGENTEPESSOAL_ENSAIO=1 até a virada (fase 8): nada vai ao celular nem se publica na Meta pelo Hermes; o que iria fica
# em /opt/hermes/data/agentepessoal/ensaio_celular.jsonl (whatsapp/helpers/ponte.py, conteudo/helpers/conteudo.py).
# E, no ensaio, a chave da ponte do celular (/a0/usr/whatsapp) e os valores do cofre (/a0/usr/segredos) aparecem vazios
# no container: um terminal ou código do Hermes não tem com que mandar ao celular nem publicar por fora das ferramentas.
docker run -d --name hermes --restart no --network hermes \
  --memory 3g --memory-swap 3g \
  --add-host host.docker.internal:host-gateway \
  -v "$DADOS":/opt/data \
  -v /opt/hermes/a0usr:/a0/usr \
  "${ESCONDIDOS[@]}" \
  -e AWS_ENDPOINT_URL_BEDROCK_RUNTIME=http://host.docker.internal:8787/hermes/bedrock \
  -e ANTHROPIC_BEDROCK_BASE_URL=http://host.docker.internal:8787/hermes/bedrock \
  -e AWS_ACCESS_KEY_ID=proxy -e AWS_SECRET_ACCESS_KEY=proxy -e AWS_REGION=us-east-1 -e AWS_EC2_METADATA_DISABLED=true \
  -e API_SERVER_ENABLED=true -e API_SERVER_HOST=0.0.0.0 -e API_SERVER_KEY="$(cat /opt/hermes/api_key)" \
  -e HERMES_TIMEZONE=America/Bahia -e HF_HOME=/opt/data/cache/hf \
  "${MODO_ENV[@]}" \
  -e BROWSER_CDP_URL="$CDP" \
  -p 127.0.0.1:8642:8642 \
  "$IMAGEM" gateway run >/dev/null
# Virada: o celular Android na rede do Hermes (IP fixo .0.252, nome "android" como na rede phone do A0; firewall.sh
# deixa o Hermes falar só com a porta do adb e o celular não abre nada no Hermes nem no host).
if [ "$VIRADA" = 1 ] && docker inspect android >/dev/null 2>&1; then
  SUBH=$(docker network inspect hermes -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}')
  docker network inspect hermes -f '{{range .Containers}}{{.Name}} {{end}}' | grep -qw android \
    || docker network connect --ip "${SUBH%.*.*}.0.252" --alias android hermes android
elif docker inspect android >/dev/null 2>&1; then
  docker network disconnect hermes android >/dev/null 2>&1 || true
fi
/opt/agentepessoal/firewall.sh || { echo "HERMES_SEM_FIREWALL"; exit 1; }
# Na subida da VM quem liga o Hermes é esta unidade, depois do firewall e da vista (não o reinício do próprio Docker).
install -m 755 "$AQUI/iniciar.sh" /opt/hermes/iniciar.sh
install -m 644 "$AQUI/agentepessoal-hermes.service" /etc/systemd/system/agentepessoal-hermes.service
systemctl daemon-reload
systemctl enable -q agentepessoal-hermes.service
for i in $(seq 1 60); do
  curl -fsS -m 3 http://127.0.0.1:8642/health >/dev/null 2>&1 && break
  sleep 2
done
# De pé não basta: uma pergunta de verdade ao modelo, pelo mesmo caminho das conversas (Claude no Bedrock pelo proxy).
RESPOSTA=$(curl -sS -m 120 http://127.0.0.1:8642/v1/chat/completions -H "Authorization: Bearer $(cat /opt/hermes/api_key)" \
  -H 'Content-Type: application/json' -d '{"model":"hermes","messages":[{"role":"user","content":"Responda só: PONTE OK"}]}' || true)
if echo "$RESPOSTA" | grep -qi "PONTE OK"; then
  [ -f "$AQUI/../portal/subir.sh" ] && { PORTAL_VIRADA="$VIRADA" bash "$AQUI/../portal/subir.sh" "$IMAGEM" | grep "^PORTAL_OK" \
    || { echo "HERMES_SEM_PORTAL: o portal não subiu"; exit 1; }; }
  # Virada: um Hermes por convidado (memória, conversas, rotinas e navegador só dele); fora dela, nenhum
  for login in $(python3 -c "import importlib.util as u;s=u.spec_from_file_location('c','/opt/a0/usr/plugins/login_usuarios/helpers/convidados.py');m=u.module_from_spec(s);s.loader.exec_module(m);print(' '.join(sorted(m.CONVIDADOS)))"); do
    if [ "$VIRADA" = 1 ]; then
      bash "$AQUI/convidado.sh" "$login" "$IMAGEM" | grep "^CONVIDADO_OK" || { echo "HERMES_SEM_CONVIDADO: $login"; exit 1; }
    else
      docker rm -f "hermes-$login" "hermes-navegador-$login" >/dev/null 2>&1 || true
    fi
  done
  docker exec hermes python3 /opt/data/agentepessoal/rotinas_aplicar.py | grep "^ROTINAS_OK" \
    || { echo "HERMES_SEM_ROTINAS: as rotinas não foram aplicadas"; exit 1; }
  # o modelo do áudio (faster-whisper small) baixa uma vez para o cache, em segundo plano
  docker exec -d hermes python3 -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"
  # a fonte que está no ar fica guardada: virada.sh (virar/voltar) sobe o Hermes de novo a partir dela
  if [ "$AQUI" != /opt/hermes/fonte/hermes ]; then
    mkdir -p /opt/hermes/fonte
    rsync -a --delete "$AQUI/" /opt/hermes/fonte/hermes/
    [ -d "$AQUI/../portal" ] && rsync -a --delete "$AQUI/../portal/" /opt/hermes/fonte/portal/
  fi
  echo "HERMES_OK $(docker inspect -f '{{.Image}}' hermes) modo=$([ "$VIRADA" = 1 ] && echo virada || echo ensaio)"; exit 0
fi
echo "HERMES_NAO_RESPONDEU: ${RESPOSTA:0:400}"; docker logs --tail 40 hermes; exit 1

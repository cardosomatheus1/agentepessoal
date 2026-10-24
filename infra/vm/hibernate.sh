#!/bin/bash
# Back up, then hibernate this instance: RAM is saved to the encrypted disk and the
# next start resumes with the agent and the phone already running.
# 24/10: hibernar só com HIBERNAR=1 em /etc/agentepessoal.env (a volta da hibernação deixou a VM sem rede: a placa ENA
# não voltou). Sem isso, "Desligar" na página de controle faz backup e um desligamento normal (o próximo Ligar começa
# do zero, com tudo subindo sozinho).
set -u
REGION=us-east-1
BASE="${BASE:-/opt/agentepessoal}"
AWS="${AWS:-/usr/local/bin/aws}"
HIBERNAR="${HIBERNAR:-$(sed -n 's/^HIBERNAR=//p' /etc/agentepessoal.env 2>/dev/null | tail -1)}"
"$BASE/backup.sh" || true
# wake exactly for the agent's next scheduled task (one-shot AWS schedule; none = stays asleep)
"$BASE/venv/bin/python" "$BASE/proximo_despertar.py" 2>&1 | logger -t agentepessoal || true
if [ -z "${IID:-}" ]; then
  TOKEN=$(curl -sS -m 5 -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
  IID=$(curl -sS -m 5 -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
fi
for p in agent-url phone-url; do
  "$AWS" ssm put-parameter --region "$REGION" --name "/agentepessoal/$p" --value stopped --type String --overwrite >/dev/null 2>&1 || true
done
if [ "${HIBERNAR:-0}" != 1 ]; then
  logger -t agentepessoal "desligando $IID (sem hibernar: HIBERNAR não é 1)"
  "$AWS" ec2 stop-instances --region "$REGION" --instance-ids "$IID" >/dev/null || shutdown -h now
  exit 0
fi
logger -t agentepessoal "hibernating $IID"
if ! "$AWS" ec2 stop-instances --region "$REGION" --instance-ids "$IID" --hibernate >/dev/null; then
  # 12/10 review: this turned into a plain shutdown without a word; now it is logged and the daily health check says so
  logger -t agentepessoal "hibernação FALHOU: desligando (a próxima partida começa do zero)"
  touch /var/lib/agentepessoal/hibernacao_falhou
  shutdown -h now
fi

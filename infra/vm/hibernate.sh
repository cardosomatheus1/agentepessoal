#!/bin/bash
# Back up, then hibernate this instance: RAM is saved to the encrypted disk and the
# next start resumes with the agent and the phone already running.
set -u
REGION=us-east-1
/opt/agentepessoal/backup.sh || true
TOKEN=$(curl -sS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
IID=$(curl -sS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
for p in agent-url phone-url; do
  /usr/local/bin/aws ssm put-parameter --region "$REGION" --name "/agentepessoal/$p" --value stopped --type String --overwrite >/dev/null 2>&1 || true
done
logger -t agentepessoal "hibernating $IID"
/usr/local/bin/aws ec2 stop-instances --region "$REGION" --instance-ids "$IID" --hibernate >/dev/null || shutdown -h now

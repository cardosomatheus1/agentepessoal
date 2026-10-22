"""Short-lived AWS credentials for the agent to write the NEXOS Meta app secret.

The agent container has no AWS identity. This service (on the VM host) assumes the narrow role
agentepessoal-segredo-meta — read/write only the secret ros-dev-meta/app and restart the NEXOS
api/worker services — and answers in the AWS CLI/SDK `credential_process` format, so
`pnpm --filter @ros/infra-aws segredo-meta` runs inside the container with
AWS_CONFIG_FILE=/a0/usr/.aws/config AWS_PROFILE=segredo-meta, and no key ever goes through the chat.
Only containers on this VM (docker networks) and the host itself may ask.

Path /voz (22/10): the same for the narration of the video templates (/a0/usr/moldes): role agentepessoal-voz, only
Nova 2 Sonic in Bedrock and Polly, profile `voz` in the same config file.
"""

import http.server
import ipaddress
import json
import os

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
LISTEN = ("0.0.0.0", int(os.environ.get("META_CREDS_PORT", "8788")))
PAPEIS = {"/": ("agentepessoal-segredo-meta", "agente-segredo-meta"), "/voz": ("agentepessoal-voz", "agente-voz")}
LOCAL = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "172.16.0.0/12")]


def credentials(caminho: str = "/") -> dict:
    papel, sessao = PAPEIS[caminho]
    sts = boto3.client("sts", region_name=REGION)
    arn = f"arn:aws:iam::{sts.get_caller_identity()['Account']}:role/{papel}"
    c = sts.assume_role(RoleArn=arn, RoleSessionName=sessao, DurationSeconds=3600)["Credentials"]
    return {"Version": 1, "AccessKeyId": c["AccessKeyId"], "SecretAccessKey": c["SecretAccessKey"],
            "SessionToken": c["SessionToken"], "Expiration": c["Expiration"].isoformat()}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        ip = ipaddress.ip_address(self.client_address[0])
        if self.path not in PAPEIS or not any(ip in n for n in LOCAL):
            code, body = 404, {"error": "not found"}
        else:
            try:
                code, body = 200, credentials(self.path)
            except Exception as exc:
                code, body = 503, {"error": str(exc)[:300]}
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(LISTEN, Handler).serve_forever()

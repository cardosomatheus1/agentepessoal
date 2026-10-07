"""Keep Agent Zero's built-in Cloudflare tunnel up and publish its URL to SSM.

The quick-tunnel URL changes on every boot, so the control page reads it from
the SSM parameter this loop maintains.
"""

import json
import os
import subprocess
import time
import urllib.request

import boto3

PARAM = os.environ.get("URL_PARAM", "/agentepessoal/agent-url")
CONTAINER = os.environ.get("CONTAINER", "agent-zero")
LOCAL_UI = os.environ.get("LOCAL_UI", "http://127.0.0.1:50080/")

ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def tunnel(action: str) -> dict:
    payload = json.dumps({"action": action, "provider": "cloudflared"})
    cmd = [
        "docker", "exec", CONTAINER, "python3", "-c",
        "import sys,urllib.request;"
        "r=urllib.request.Request('http://localhost:55520/',data=sys.argv[1].encode(),"
        "headers={'Content-Type':'application/json'});"
        "print(urllib.request.urlopen(r,timeout=120).read().decode())",
        payload,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return json.loads(out.stdout or "{}")


def ui_up() -> bool:
    try:
        with urllib.request.urlopen(LOCAL_UI, timeout=5) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:
        return False


def publish(value: str) -> None:
    ssm.put_parameter(Name=PARAM, Value=value, Type="String", Overwrite=True)


def main() -> None:
    publish("starting")
    published = "starting"
    while True:
        try:
            if ui_up():
                url = (tunnel("get") or {}).get("tunnel_url")
                if not url:
                    url = (tunnel("create") or {}).get("tunnel_url")
                if url and url != published:
                    publish(url)
                    published = url
        except Exception as exc:  # keep trying; the page shows "starting" meanwhile
            print(f"report_url: {exc}", flush=True)
        time.sleep(15 if published == "starting" else 60)


if __name__ == "__main__":
    main()

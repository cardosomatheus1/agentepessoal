"""Keep the agent and phone tunnels up and publish their URLs to SSM.

- agent: Agent Zero's built-in Cloudflare tunnel (handles its origin checks)
- phone: a host cloudflared quick tunnel in front of ws-scrcpy

Quick-tunnel URLs change on reboot. After hibernate/resume the agent tunnel may
keep its URL but stop answering; it is recreated after a few failed checks. The control page
writes "starting"/"stopped" into the parameters, so we compare against SSM on
every pass and republish whenever the stored value differs from the live URL.
"""

import json
import os
import re
import subprocess
import time
import urllib.request

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
AGENT_PARAM = "/agentepessoal/agent-url"
PHONE_PARAM = "/agentepessoal/phone-url"
CONTAINER = "agent-zero"
LOCAL_UI = "http://127.0.0.1:50080/"
PHONE_UNIT = "agentepessoal-phone-tunnel"
REFRESH_S = 60
PHONE_FILE = "/opt/a0/usr/celular/url.txt"  # read by the Agent Zero "Celular" panel


def write_phone_file(url: str) -> None:
    try:
        os.makedirs(os.path.dirname(PHONE_FILE), exist_ok=True)
        with open(PHONE_FILE, "w") as f:
            f.write(url)
    except OSError as exc:
        print(f"report_url: {exc}", flush=True)

ssm = boto3.client("ssm", region_name=REGION)


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


def reachable(url: str) -> bool:
    """The public side of the tunnel answers (any status below 500 means Cloudflare reached the UI)."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/login", timeout=15) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:
        return False


_dead_checks = {"n": 0}
DEAD_LIMIT = 3  # ~3 refreshes (3 min) of a dead public URL before recreating the tunnel


def agent_url() -> str | None:
    if not ui_up():
        return None
    url = (tunnel("get") or {}).get("tunnel_url")
    # After hibernate/resume the quick tunnel often keeps reporting its old URL while
    # Cloudflare answers 530/connection errors: recreate it instead of publishing a dead link.
    if url and not reachable(url):
        _dead_checks["n"] += 1
        if _dead_checks["n"] < DEAD_LIMIT:
            return url
        print(f"report_url: {url} unreachable, recreating the agent tunnel", flush=True)
        tunnel("stop")
        url = None
    _dead_checks["n"] = 0
    return url or (tunnel("create") or {}).get("tunnel_url")


def phone_url() -> str | None:
    out = subprocess.run(
        ["journalctl", "-u", PHONE_UNIT, "-b", "--no-pager", "-o", "cat"],
        capture_output=True, text=True, timeout=30,
    ).stdout
    found = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", out)
    return found[-1] if found else None


def stored(name: str) -> str:
    try:
        return ssm.get_parameter(Name=name)["Parameter"]["Value"]
    except Exception:
        return ""


def main() -> None:
    sources = {AGENT_PARAM: agent_url, PHONE_PARAM: phone_url}
    live: dict[str, str] = {}
    checked: dict[str, float] = {}
    while True:
        for param, source in sources.items():
            try:
                current = stored(param)
                due = time.time() - checked.get(param, 0) > REFRESH_S
                if param not in live or current != live[param] or due:
                    url = source()
                    checked[param] = time.time()
                    if url:
                        live[param] = url
                        if param == PHONE_PARAM:
                            write_phone_file(url)
                        if current != url:
                            ssm.put_parameter(Name=param, Value=url, Type="String", Overwrite=True)
            except Exception as exc:  # keep trying; the page shows "starting" meanwhile
                print(f"report_url {param}: {exc}", flush=True)
        time.sleep(4)


if __name__ == "__main__":
    main()

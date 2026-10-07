"""Calls to the VM's local proxy (bedrock_proxy.py), which holds the AWS role."""
import json
import re
import urllib.request

HOST = "http://host.docker.internal:8787"
CHAT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def post(path: str, body: dict, timeout: float = 60) -> dict:
    req = urllib.request.Request(HOST + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}") or {"error": f"HTTP {e.code}"}

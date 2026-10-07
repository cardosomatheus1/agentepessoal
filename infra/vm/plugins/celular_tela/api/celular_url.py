from pathlib import Path

from helpers.api import ApiHandler, Request, Response

# Written by the VM's report_url.py (host) whenever the phone tunnel URL changes.
URL_FILE = Path("/a0/usr/celular/url.txt")


class CelularUrl(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            url = URL_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            url = ""
        return {"url": url if url.startswith("https://") else ""}

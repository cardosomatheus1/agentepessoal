"""Small log of what the phone viewer did on a real device (taps, keyboard, scrolling), so problems
seen only on the phone can be read on the server. Capped at ~200 KB."""

import json
import time
from pathlib import Path

from helpers.api import ApiHandler, Request, Response

ARQUIVO = Path("/a0/usr/navegador_visual/diag.log")


class Diag(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        if ARQUIVO.exists() and ARQUIVO.stat().st_size > 200_000:
            ARQUIVO.write_text(ARQUIVO.read_text(encoding="utf-8")[-100_000:], encoding="utf-8")
        linha = {"t": time.strftime("%H:%M:%S"), **{k: input[k] for k in list(input)[:20]}}
        with ARQUIVO.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False)[:2000] + "\n")
        return {"ok": True}

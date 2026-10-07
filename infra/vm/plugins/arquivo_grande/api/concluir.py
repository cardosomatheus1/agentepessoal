import asyncio
import importlib.util
from pathlib import Path

from helpers.api import ApiHandler, Request, Response

_spec = importlib.util.spec_from_file_location("arquivo_grande_host", Path(__file__).resolve().parents[1] / "helpers" / "host.py")
host = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(host)


class Concluir(ApiHandler):
    """Pull the uploaded file into /a0/usr/chats/<chat>/anexos now; poll until it is there."""

    async def process(self, input: dict, request: Request) -> dict | Response:
        chat = str(input.get("context", ""))
        name = str(input.get("name", ""))
        if not host.CHAT_ID.match(chat) or not name or "/" in name or name in (".", ".."):
            return Response('{"error": "pedido inválido"}', status=400, mimetype="application/json")
        path = Path("/a0/usr/chats") / chat / "anexos" / name
        if not path.exists():
            await asyncio.to_thread(host.post, "/arquivos/puxar", {"wait": 40}, 60)
        if path.exists():
            return {"ok": True, "path": str(path), "size": path.stat().st_size}
        return {"ok": False, "pending": True}

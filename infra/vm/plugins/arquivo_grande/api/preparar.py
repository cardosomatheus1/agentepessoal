import asyncio
import importlib.util
from pathlib import Path

from helpers.api import ApiHandler, Request, Response

_spec = importlib.util.spec_from_file_location("arquivo_grande_host", Path(__file__).resolve().parents[1] / "helpers" / "host.py")
host = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(host)


class Preparar(ApiHandler):
    """Presigned S3 upload URL for a file going into this chat's anexos/."""

    async def process(self, input: dict, request: Request) -> dict | Response:
        chat = str(input.get("context", ""))
        if not host.CHAT_ID.match(chat):
            return Response('{"error": "conversa inválida"}', status=400, mimetype="application/json")
        return await asyncio.to_thread(host.post, "/arquivos/presign",
                                       {"chat": chat, "name": input.get("name", ""), "size": input.get("size", 0)})

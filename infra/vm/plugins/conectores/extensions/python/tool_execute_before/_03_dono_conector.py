"""A connector tied to one person's account (donos.json) only runs in that person's chats."""

import json
import sys
from pathlib import Path

from helpers.extension import Extension

DONOS = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "donos.json"


def donos() -> dict:
    try:
        return json.loads(DONOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def dono_da_conversa(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")


class DonoConector(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if not self.agent or "." not in (tool_name or ""):
            return
        servidor = tool_name.split(".", 1)[0]
        dono = donos().get(servidor)
        if dono and dono != dono_da_conversa(self.agent.context):
            from helpers.errors import RepairableException

            raise RepairableException(
                f"O conector '{servidor}' está ligado à conta de outra pessoa e não pode ser usado nesta conversa. "
                "Não tente de novo; faça pelo navegador, se a pessoa tiver acesso, ou diga que não há conector dela.")

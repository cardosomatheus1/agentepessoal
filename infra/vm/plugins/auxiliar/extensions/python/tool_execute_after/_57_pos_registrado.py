"""After the agent saves loose ends in the person's phone chat while a meeting follow-up is pending, the
follow-up counts as answered — without depending on the model also calling `reuniao pos_registrado`."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension


def aux():
    nome = "auxiliar_helper"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "auxiliar.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


class PosRegistrado(Extension):
    async def execute(self, response=None, tool_name: str = "", **kwargs):
        agent = self.agent
        if not agent or agent.number != 0 or tool_name != "fios":
            return
        login = agent.context.get_data("whatsapp_de")
        if not login:
            return
        try:
            a = aux()
            for r in a.pos_pendentes(login):
                a.registrar_pos(login, r["evento_id"])
        except Exception as exc:
            print(f"auxiliar: follow-up not marked: {exc}", flush=True)

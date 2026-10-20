"""Every model call carries the chat's owner (X-A0-Dono), so the host proxy can log spending per person and the phone
bridge can hold a guest to the daily limit (helpers/convidados.py); and (20/10) which chat, routine and agent made it
(helpers/rastreio.py), for the prompt-cache diagnosis and cache settings in the host proxy."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def _helper(nome: str, arquivo: str):
    caminho = RAIZ / "helpers" / arquivo
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def convidados():
    return _helper("login_usuarios_convidados", "convidados.py")


def rastreio():
    return _helper("login_usuarios_rastreio", "rastreio.py")


PAPEL = "util"


class QuemGasta(Extension):
    async def execute(self, call_data: dict | None = None, **kwargs):
        if not self.agent or not isinstance(call_data, dict) or not call_data.get("model"):
            return
        try:
            sep = sys.modules.get("login_usuarios_separacao")
            dono = sep.dono_contexto(self.agent.context) if sep else (self.agent.context.get_data("dono") or "matheus")
            try:
                extras = rastreio().do_agente(self.agent, PAPEL)
            except Exception:
                extras = {}
            call_data["model"] = convidados().com_dono(call_data["model"], dono, extras)
        except Exception as exc:  # never in the way of a model call
            print(f"login_usuarios: dono do gasto não marcado: {exc}", flush=True)

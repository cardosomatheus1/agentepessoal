"""Before a long wait in a phone chat, tell the person on the phone until when.

The agent once read "n espera até 21:30" ("do NOT wait") as "wait until 21:30" and sat silent. A
wait longer than a minute in a Telegram/WhatsApp chat is now announced at once, so a misreading
shows up the same minute and /parar ends it.
"""

import asyncio
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from helpers.extension import Extension

LIMITE = 60
FUSO = ZoneInfo("America/Bahia")


def ponte():
    nome = "whatsapp_ponte"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "ponte.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        for estado in ("PENDENTES", "PEDIDOS"):
            if antigo is not None and hasattr(antigo, estado):
                setattr(modulo, estado, getattr(antigo, estado))
        sys.modules[nome] = modulo
    return sys.modules[nome]


def fim_da_espera(args: dict) -> datetime | None:
    agora = datetime.now(timezone.utc)
    ate = str(args.get("until") or "").strip()
    if ate:
        try:
            from helpers.localization import Localization

            return Localization.get().localtime_str_to_utc_dt(ate)
        except Exception:
            try:
                fim = datetime.fromisoformat(ate.replace("Z", "+00:00"))
                return fim if fim.tzinfo else fim.replace(tzinfo=FUSO).astimezone(timezone.utc)
            except ValueError:
                return None
    try:
        return agora + timedelta(days=float(args.get("days") or 0), hours=float(args.get("hours") or 0),
                                 minutes=float(args.get("minutes") or 0), seconds=float(args.get("seconds") or 0))
    except (TypeError, ValueError):
        return None


class AvisarEspera(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if not self.agent or tool_name != "wait":
            return
        destino = self.agent.context.get_data("whatsapp_de")
        if not destino:
            return
        fim = fim_da_espera(tool_args or {})
        if fim is None:
            return
        segundos = (fim - datetime.now(timezone.utc)).total_seconds()
        if segundos <= LIMITE:
            return
        hora = fim.astimezone(FUSO).strftime("%H:%M")
        minutos = max(1, round(segundos / 60))
        texto = (f"⏳ Vou ficar esperando até {hora} (~{minutos} min) antes de continuar. "
                 "Se não era isso, mande /parar e diga o que fazer.")
        erro = await asyncio.to_thread(ponte().enviar, destino, texto)
        if erro:
            print(f"whatsapp: wait notice not delivered: {erro}", flush=True)

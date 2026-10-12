"""The "CRM Raiz" sheet (12/10 review §5.2 item 10): once a day, after 20h30 (the day's summary goes at 20h17), the
prospecting register is written to the sheet (helpers/crm.py: when, and how). A failure is tried again an hour later,
at most 3 times a day; the first time, the person gets the sheet's link once."""

import asyncio
import importlib.util
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
ESTADO = Path("/a0/usr/marcas/crm_raiz.json")  # module globals reset on every job loop pass: state in a file
LOGIN = "matheus"  # the Google connector is single-user: the owner's
FUSO = ZoneInfo("America/Bahia")


def carregar(nome: str, caminho: Path):
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


async def _chamar(ferramenta: str, argumentos: dict) -> tuple[bool, str]:
    from helpers.mcp_handler import MCPConfig

    try:
        r = await MCPConfig.get_instance().call_tool(f"google.{ferramenta}", argumentos)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    texto = "\n".join(str(getattr(c, "text", "") or "") for c in (getattr(r, "content", None) or []))
    return not getattr(r, "isError", False), texto


class CrmRaiz(Extension):
    async def execute(self, **kwargs):
        agora = datetime.now(FUSO)
        try:
            estado = json.loads(ESTADO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            estado = {}
        crm = carregar("prospeccao_crm", RAIZ / "helpers" / "crm.py")
        if not crm.na_vez(estado, agora):
            return
        dia = agora.date().isoformat()
        estado = {"dia": dia, "tentativas": (estado.get("tentativas", 0) if estado.get("dia") == dia else 0) + 1,
                  "em": time.time(), "ok": False}
        ESTADO.parent.mkdir(parents=True, exist_ok=True)
        ESTADO.write_text(json.dumps(estado), encoding="utf-8")
        try:
            pr = carregar("prospeccao_helper", RAIZ / "helpers" / "prospeccao.py")
            sid, criada = await crm.sincronizar(pr, LOGIN, _chamar)
            estado["ok"] = True
            ESTADO.write_text(json.dumps(estado), encoding="utf-8")
            print(f"prospeccao: CRM Raiz atualizado ({len(pr.linhas_crm(LOGIN)) - 1} leads)", flush=True)
            if criada:
                ponte = carregar("whatsapp_ponte", Path("/a0/usr/plugins/whatsapp/helpers/ponte.py"))
                await asyncio.to_thread(ponte.enviar, LOGIN, (
                    "📊 Criei a planilha *CRM Raiz*: os leads da prospecção, os mais quentes primeiro, com a etapa e o "
                    f"próximo passo. Atualiza sozinha todo dia às 20h30 (é só para ver; quem manda é o registro).\n"
                    f"https://docs.google.com/spreadsheets/d/{sid}"), "", "", None, "progresso")
        except Exception as exc:  # never stops the job loop
            print(f"prospeccao: CRM Raiz falhou ({estado['tentativas']}/{crm.TENTATIVAS}): {type(exc).__name__}: {exc}",
                  flush=True)

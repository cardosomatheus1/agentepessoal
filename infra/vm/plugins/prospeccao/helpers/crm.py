"""The "CRM Raiz" sheet (12/10 review §5.2 item 10): the prospecting register written once a day to a Google sheet,
through the agent's own Google connector (no model, no new credential). A view only: the register stays the source
and nothing is read back from the sheet."""

import re
from datetime import datetime

HORA = "20:30"  # after the day's summary (20h17)
TENTATIVAS = 3
CONTA = "falhanosistema1111@gmail.com"  # the Google account of the agent's connector (workspace-mcp, single user)
ABA = "Leads"
SUMIU = re.compile(r"not ?found|404|n[aã]o encontrad|does not exist|deleted|trashed", re.I)


class CrmFalhou(RuntimeError):
    pass


async def sincronizar(pr, login: str, chamar, conta: str = CONTA) -> tuple[str, bool]:
    """Rewrite the sheet with `pr.linhas_crm(login)`; a new sheet the first time or when the old one was deleted.
    `chamar(ferramenta, argumentos) -> (ok, texto)` calls a tool of the Google connector. Returns (id, created)."""
    linhas = pr.linhas_crm(login)
    sid = str(pr.carregar(login)["config"].get("crm_planilha") or "")
    if sid:
        ok, texto = await chamar("modify_sheet_values", {"user_google_email": conta, "spreadsheet_id": sid,
                                                         "range_name": f"{ABA}!A:Z", "clear_values": True})
        if not ok:
            if not SUMIU.search(texto):  # the connector or Google is down: try again later, same sheet
                raise CrmFalhou(f"não consegui limpar a planilha: {texto[:200]}")
            sid = ""
    criada = not sid
    if criada:
        ok, texto = await chamar("create_spreadsheet", {"user_google_email": conta, "title": pr.CRM_TITULO,
                                                        "sheet_names": [ABA]})
        achado = re.search(r"ID: ([A-Za-z0-9_-]{20,})", texto or "")
        if not ok or not achado:
            raise CrmFalhou(f"não consegui criar a planilha: {(texto or '')[:200]}")
        sid = achado.group(1)
        pr.definir_crm(login, sid)
    ok, texto = await chamar("modify_sheet_values", {"user_google_email": conta, "spreadsheet_id": sid,
                                                     "range_name": f"{ABA}!A1", "values": linhas, "value_input_option": "RAW"})
    if not ok:
        raise CrmFalhou(f"não consegui escrever na planilha: {texto[:200]}")
    if criada:  # the header in bold, frozen; failures here are cosmetic
        colunas = chr(ord("A") + len(linhas[0]) - 1)
        await chamar("format_sheet_range", {"user_google_email": conta, "spreadsheet_id": sid, "range_name": f"{ABA}!A1:{colunas}1",
                                            "bold": True})
        await chamar("resize_sheet_dimensions", {"user_google_email": conta, "spreadsheet_id": sid, "sheet_name": ABA,
                                                 "frozen_row_count": 1})
    return sid, criada


def na_vez(estado: dict, agora: datetime) -> bool:
    """After HORA, once a day; after a failure, again one hour later, up to TENTATIVAS a day.
    `estado`: {"dia", "ok", "tentativas", "em"} of the last attempt."""
    if agora.strftime("%H:%M") < HORA:
        return False
    if estado.get("dia") != agora.date().isoformat():
        return True
    return (not estado.get("ok") and estado.get("tentativas", 0) < TENTATIVAS
            and agora.timestamp() - estado.get("em", 0) >= 3600)

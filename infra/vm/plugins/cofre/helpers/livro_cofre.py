"""The vault in the action ledger (12/10 review §6, "livro registrando só o nome do segredo usado"): every time a
secret is handed to a tool, plugins/central's ledger gets the NAME, the tool and the chat — never the value. The same
name in the same chat is recorded once every INTERVALO (a login retries a few times)."""

import importlib.util
import sys
import time
from pathlib import Path

LIVRO = Path("/a0/usr/plugins/central/helpers/livro.py")
INTERVALO = 10 * 60


def livro():
    """plugins/central's ledger helper (None when it is not installed)."""
    if not LIVRO.exists():
        return sys.modules.get("central_livro")
    antigo = sys.modules.get("central_livro")
    mtime = LIVRO.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location("central_livro", LIVRO)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules["central_livro"] = modulo
    return sys.modules["central_livro"]


def registrar_usos(registro, login: str, ferramenta: str, nomes: list, ultimos: dict, ctx_id: str = "",
                   agora: float | None = None) -> list:
    """Record each secret name handed to `ferramenta` (not seen in this chat in the last INTERVALO). `registro`: the
    ledger module (or None); `ultimos`: {name: when last recorded} of this chat, updated in place. Returns the names
    recorded."""
    agora = agora or time.time()
    novos = [n for n in nomes if agora - float(ultimos.get(n) or 0) >= INTERVALO]
    if not registro or not novos:
        return []
    feitos = []
    for nome in novos:
        if registro.registrar("executada", login, "cofre", ferramenta, "segredo", f"cofre:{nome}", conteudo="",
                              resultado=f"senha {nome} entregue à ferramenta {ferramenta}", ctx_id=ctx_id, em=agora):
            ultimos[nome] = agora
            feitos.append(nome)
    return feitos

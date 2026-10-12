"""Each research in the action ledger (12/10 review §6, "Pesquisa: registrar o arquivo do resultado no livro"): what
was asked, where the result is and how many sources — so "aquela pesquisa da lava e seca" is found later from the
ledger instead of from memory."""

import importlib.util
import sys
from pathlib import Path

LIVRO = Path("/a0/usr/plugins/central/helpers/livro.py")


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


def registrar(registro, login: str, pergunta: str, arquivo: str, fontes: int, ctx_id: str = "") -> str:
    """The ledger id of the record ('' when there is no ledger or it was not recorded)."""
    if not registro or not arquivo:
        return ""
    return registro.registrar("executada", login, "pesquisa", "pesquisar", "pesquisa", f"arquivo:{arquivo}",
                              conteudo=" ".join(str(pergunta or "").split()),
                              resultado=f"{fontes} fontes; síntese em {arquivo}", ctx_id=ctx_id)

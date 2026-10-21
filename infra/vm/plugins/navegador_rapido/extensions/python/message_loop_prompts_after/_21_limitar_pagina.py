"""Cap the page text the browser plugin adds to every model call.

A big page (e.g. a Wikipedia article: ~260k chars, ~65k tokens) was resent in full at
every step, making each step slower and pricier. Keep the top of the page and tell the
agent how to read the rest on demand.

Item 11 of docs/AUDITORIA_MATURIDADE_AGENTE.md (Hermes browser_tool_snapshot.py): the whole page also goes to a file,
and the cut says where it is and from which line to keep reading (tool `ler`), so nothing past the cut is lost.
"""

import hashlib
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension

MAX_CHARS = 20_000  # ~5k tokens per step; the agent reads other parts on demand
PASTA = Path("/a0/usr/workdir/paginas")
GUARDAR = 20  # page files kept (the oldest go)


def guardar(texto: str, contexto: str, pasta: Path = PASTA) -> Path | None:
    """The whole page text in <pasta>/<chat>-<hash>.txt (the same page is written once); None when it cannot write."""
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        nome = f"{''.join(c for c in str(contexto) if c.isalnum())[:16] or 'pagina'}-" \
               f"{hashlib.sha1(texto.encode('utf-8', 'replace')).hexdigest()[:10]}.txt"
        arq = pasta / nome
        if not arq.exists():
            arq.write_text(texto, encoding="utf-8")
            for velho in sorted(pasta.glob("*.txt"), key=lambda p: p.stat().st_mtime)[:-GUARDAR]:
                velho.unlink(missing_ok=True)
        return arq
    except OSError:
        return None


def cortar(texto: str, contexto: str, pasta: Path = PASTA) -> str:
    if not isinstance(texto, str) or len(texto) <= MAX_CHARS:
        return texto
    cut = texto.rfind("\n", 0, MAX_CHARS)
    cut = cut if cut > MAX_CHARS // 2 else MAX_CHARS
    arq = guardar(texto, contexto, pasta)
    resto = ""
    if arq is not None:
        linha = texto.count("\n", 0, cut) + (2 if texto[cut:cut + 1] == "\n" else 1)  # first line not shown
        resto = (f" The WHOLE page is saved in {arq}: to read past this cut, call the tool `ler` with "
                 f"caminho {arq} and inicio {linha} (it pages by lines).")
    return (texto[:cut]
            + f"\n\n[page text cut at {cut:,} of {len(texto):,} characters to keep steps fast.{resto} "
            "Or call the browser tool with action `content` and a CSS `selector` for that section, or `scroll` and "
            "read again.]")


class LimitarPagina(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        text = loop_data.extras_temporary.get("browser_context")
        if not isinstance(text, str) or len(text) <= MAX_CHARS:
            return
        contexto = getattr(getattr(self.agent, "context", None), "id", "") or "pagina"
        loop_data.extras_temporary["browser_context"] = cortar(text, contexto)

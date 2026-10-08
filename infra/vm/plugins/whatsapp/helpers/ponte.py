"""Talk to the host's ponte_whatsapp (infra/vm/ponte_whatsapp.py).

The bridge holds the Meta token and the phone numbers; here people are addressed only by
their login name, so the agent can reach no one but the registered users.
"""

import json
import re
import urllib.request
from pathlib import Path

URL = "http://host.docker.internal:8789/enviar"
CHAVE = Path("/a0/usr/whatsapp/.chave")


def chave() -> str:
    try:
        return CHAVE.read_text().strip()
    except OSError:
        return ""


def enviar(usuario: str, texto: str = "", arquivo: str = "", legenda: str = "") -> str:
    """'' when sent, else the reason it was not."""
    if not usuario:
        return "conversa sem dono"
    corpo = {"usuario": usuario, "texto": formatar(texto) if texto else "", "arquivo": arquivo, "legenda": legenda}
    req = urllib.request.Request(URL, data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json", "X-Chave": chave()})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            r.read()
        return ""
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()).get("erro") or str(e)
        except Exception:
            return str(e)
    except Exception as exc:
        return str(exc)


def formatar(texto: str) -> str:
    """Agent markdown -> WhatsApp formatting (*bold*, _italic_, ~strike~, ```mono```)."""
    t = texto.replace("\r\n", "\n")
    t = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", t, flags=re.M)          # headings
    t = re.sub(r"\*\*(.+?)\*\*", r"*\1*", t)                         # bold
    t = re.sub(r"(?<![\w*])__(.+?)__(?![\w*])", r"*\1*", t)
    t = re.sub(r"~~(.+?)~~", r"~\1~", t)
    t = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", r"\1", t)                 # images -> path
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", t)  # links
    t = re.sub(r"^\s*[-*]\s+", "• ", t, flags=re.M)                  # bullets
    linhas = []
    for linha in t.split("\n"):                                      # tables -> "a · b · c"
        if re.match(r"^\s*\|?\s*:?-{3,}", linha):
            continue
        if linha.strip().startswith("|") and linha.strip().endswith("|"):
            celulas = [c.strip() for c in linha.strip().strip("|").split("|")]
            linha = " · ".join(c for c in celulas if c)
        linhas.append(linha)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()


def dono(context) -> str:
    """Owner login of a chat, the same rule the per-user separation uses (login_usuarios)."""
    import sys

    sep = sys.modules.get("login_usuarios_separacao")
    try:
        if sep is not None:
            return sep.dono_contexto(context)
        return (context.get_data("dono") or "").lower()
    except Exception:
        return ""

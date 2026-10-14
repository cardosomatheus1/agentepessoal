"""Signed links to one chat's browser tab, opened inside Telegram ("🖥️ Resolver aqui").

14/10, Matheus: "quero conseguir resolver pelo Telegram, sem nada extra". A captcha or a login the agent cannot do
used to need the app: open it, pick the right chat, open the Navegador. Now the phone message carries a button that
opens, inside Telegram, a live view of that chat's tab where a tap is a click. The link is the only key, so it is
signed (HMAC with the bridge's shared secret), names one chat and one person, and expires in 30 minutes.
"""

import base64
import hashlib
import hmac
import time
from pathlib import Path

CHAVE = Path("/a0/usr/whatsapp/.chave")  # the secret shared with the host bridge (never leaves the machine)
VALIDADE_S = 30 * 60
CAMINHO = "/api/plugins/navegador_visual/tela"


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).decode().rstrip("=")


def _assinatura(segredo: str, corpo: str) -> str:
    return _b64(hmac.new(segredo.encode(), corpo.encode(), hashlib.sha256).digest()[:18])


def assinar(contexto: str, usuario: str, segredo: str, agora: float | None = None, validade: int = VALIDADE_S) -> str:
    corpo = f"{contexto}.{usuario}.{int((agora or time.time()) + validade)}"
    return f"{corpo}.{_assinatura(segredo, corpo)}"


def conferir(token: str, segredo: str, agora: float | None = None) -> dict | None:
    """{"contexto", "usuario", "expira"} for a valid, unexpired token; None otherwise."""
    partes = str(token or "").split(".")
    if len(partes) != 4 or not segredo:
        return None
    contexto, usuario, expira, assinatura = partes
    if not hmac.compare_digest(assinatura, _assinatura(segredo, f"{contexto}.{usuario}.{expira}")):
        return None
    try:
        expira_em = int(expira)
    except ValueError:
        return None
    if expira_em < (agora or time.time()):
        return None
    return {"contexto": contexto, "usuario": usuario, "expira": expira_em}


def segredo(arquivo: Path = CHAVE) -> str:
    try:
        return arquivo.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def link(base_url: str, contexto: str, usuario: str, arquivo: Path = CHAVE) -> str:
    """The "Resolver aqui" link, or '' when the app address or the secret is missing."""
    s = segredo(arquivo)
    base = str(base_url or "").strip().rstrip("/")
    if not s or not base.startswith("https://") or not contexto:
        return ""
    return f"{base}{CAMINHO}?t={assinar(contexto, usuario, s)}"

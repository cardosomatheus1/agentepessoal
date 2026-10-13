"""Users allowed to log in: /a0/usr/usuarios.json (PBKDF2 hashes, never plain passwords).

{"usuarios": {"matheus": {"nome": "Matheus", "salt": "<hex>", "hash": "<hex>", "iter": 310000}}}
Create or change entries with infra/vm/usuarios.py; nothing here is in git.
"""

import hashlib
import hmac
import json
import time
from pathlib import Path

ARQUIVO = Path("/a0/usr/usuarios.json")
TENTATIVAS, JANELA = 5, 15 * 60


def carregar() -> dict:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8")).get("usuarios", {})
    except Exception:
        return {}


def verificar(login: str, senha: str) -> dict | None:
    u = carregar().get((login or "").strip().lower())
    if not u:
        hashlib.pbkdf2_hmac("sha256", b"x", b"y", 310000)  # same cost for unknown users
        return None
    calc = hashlib.pbkdf2_hmac("sha256", (senha or "").encode(), bytes.fromhex(u["salt"]), int(u.get("iter", 310000)))
    return u if hmac.compare_digest(calc.hex(), u["hash"]) else None


def nomes() -> list[str]:
    return [u.get("nome") or k.title() for k, u in carregar().items()]


class Bloqueio:
    """Failed logins, kept in the app process. Only the IP that failed is locked out (12/10 review: a global lock let
    anyone, from a few addresses, lock the owner out for 15 min). Many failures overall only make every failed
    attempt slower (`espera`); a right password from an IP that is not locked always gets in."""

    def __init__(self):
        self.falhas: dict[str, list[float]] = {}

    def _recentes(self, chave: str, agora: float | None = None) -> list[float]:
        agora = agora or time.time()
        lst = [t for t in self.falhas.get(chave, []) if agora - t < JANELA]
        self.falhas[chave] = lst
        return lst

    def bloqueado(self, ip: str, agora: float | None = None) -> bool:
        return len(self._recentes(ip, agora)) >= TENTATIVAS

    def falhou(self, ip: str, agora: float | None = None) -> None:
        for chave in (ip, "*"):
            self._recentes(chave, agora).append(agora or time.time())

    def espera(self, agora: float | None = None) -> float:
        """Seconds to hold a failed attempt: 1 normally, 5 when there are many failures overall (distributed)."""
        return 5.0 if len(self._recentes("*", agora)) >= TENTATIVAS * 6 else 1.0

    def ok(self, ip: str) -> None:
        self.falhas.pop(ip, None)


def bloqueio_do_app(extensoes: dict) -> "Bloqueio":
    """The app's lockout counter. It lives in the web process, which outlives a plugin deploy: after one, the instance
    kept there is of the OLD class (13/10: 'Bloqueio' object has no attribute 'espera', every wrong password became
    a 500). An instance of another version is replaced; the failure counts restart, which is harmless."""
    atual = extensoes.get("login_usuarios_bloqueio")
    if not isinstance(atual, Bloqueio):
        atual = extensoes["login_usuarios_bloqueio"] = Bloqueio()
    return atual

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
    """Failed logins per IP (and overall), kept in the app process."""

    def __init__(self):
        self.falhas: dict[str, list[float]] = {}

    def _recentes(self, chave: str) -> list[float]:
        agora = time.time()
        lst = [t for t in self.falhas.get(chave, []) if agora - t < JANELA]
        self.falhas[chave] = lst
        return lst

    def bloqueado(self, ip: str) -> bool:
        return len(self._recentes(ip)) >= TENTATIVAS or len(self._recentes("*")) >= TENTATIVAS * 6

    def falhou(self, ip: str) -> None:
        for chave in (ip, "*"):
            self._recentes(chave).append(time.time())

    def ok(self, ip: str) -> None:
        self.falhas.pop(ip, None)

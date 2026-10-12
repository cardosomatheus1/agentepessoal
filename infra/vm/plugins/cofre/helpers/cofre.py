"""Per-person vault: /a0/usr/segredos/<login>.json, values never shown back.

Agent Zero's own secrets (Settings → Secrets) are one store for every login. Here each person
has their own: the agent writes §§secret(NAME); right before the tool runs the placeholder
becomes the owner's value, and any value that comes back in a result is masked again.
"""

import fcntl
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

PASTA = Path("/a0/usr/segredos")
PADRAO = re.compile(r"§§secret\(([A-Za-z_][A-Za-z0-9_]*)\)")
NOME_OK = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
ESPERA_TRAVA = 30  # seconds; a write takes milliseconds

# 12/10 review: the agent (here) and the phone bridge on the host (ponte_whatsapp.py) both rewrite these files; a read
# in the middle of the other's write saw a cut file, took it as "no secrets" and the next save kept only the new one.
# Now every change is one step under a lock shared with the bridge (flock on <file>.lock: same file on the same disk),
# files are replaced whole (temp file + fsync + rename, mode 600 from the start) and an unreadable file stops the
# change instead of being overwritten.
_ultimo_bom: dict[str, dict] = {}


class CofreIlegivel(RuntimeError):
    pass


def _arquivo(usuario: str) -> Path:
    return PASTA / f"{re.sub(r'[^a-z0-9_.-]', '', usuario.lower())}.json"


def _ler(arq: Path) -> dict:
    """{} only when the file does not exist; unreadable after 3 tries = CofreIlegivel."""
    if not arq.exists():
        return {}
    for tentativa in range(3):
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
            raise ValueError("não é um objeto JSON")
        except (OSError, ValueError) as exc:
            if tentativa == 2:
                raise CofreIlegivel(f"o cofre ({arq.name}) não pôde ser lido ({str(exc)[:60]}); nada foi gravado") from None
            time.sleep(0.1)
    return {}


@contextmanager
def _transacao(arq: Path):
    """Read → change → write as one step, excluding other writers (the bridge included)."""
    PASTA.mkdir(parents=True, exist_ok=True)
    os.chmod(PASTA, 0o700)
    with open(arq.with_name(arq.name + ".lock"), "a") as trava:
        limite = time.time() + ESPERA_TRAVA
        while True:
            try:
                fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() > limite:
                    raise RuntimeError("o cofre está ocupado há mais de 30 s; tente de novo") from None
                time.sleep(0.05)
        try:
            dados = _ler(arq)
            yield dados
            _gravar_arquivo(arq, dados)
        finally:
            fcntl.flock(trava, fcntl.LOCK_UN)


def _gravar_arquivo(arq: Path, dados: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=arq.parent, prefix=f".{arq.name}.", suffix=".tmp")  # created with mode 600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1 if arq.name.endswith(".descricoes.json") else None)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, arq)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def carregar(usuario: str) -> dict:
    """For using and masking secrets: a failed read falls back to the last good copy, so values keep being
    masked; writers use _transacao, which never takes a failed read as empty."""
    arq = _arquivo(usuario)
    try:
        dados = _ler(arq)
    except CofreIlegivel:
        return dict(_ultimo_bom.get(str(arq), {}))
    _ultimo_bom[str(arq)] = dados
    return dict(dados)


def salvar(usuario: str, nome: str, valor: str) -> None:
    if not usuario or not NOME_OK.match(nome):
        raise ValueError("nome inválido: use MAIÚSCULAS, números e _ (ex.: FACEBOOK_SENHA)")
    with _transacao(_arquivo(usuario)) as dados:
        dados[nome] = valor


def apagar(usuario: str, nome: str) -> None:
    with _transacao(_arquivo(usuario)) as dados:
        dados.pop(nome, None)
    with _transacao(_arquivo_descricoes(usuario)) as desc:
        desc.pop(nome, None)


# What each secret is for ("Google · matheus@raizconnect.com.br"): names and descriptions only, never values,
# so the agent knows which one to use without asking. Kept apart from the values file.
def _arquivo_descricoes(usuario: str) -> Path:
    return PASTA / f"{re.sub(r'[^a-z0-9_.-]', '', usuario.lower())}.descricoes.json"


def descricoes(usuario: str) -> dict:
    try:
        return _ler(_arquivo_descricoes(usuario))
    except CofreIlegivel:
        return {}


def descrever(usuario: str, nome: str, para: str) -> None:
    if nome not in _ler(_arquivo(usuario)):
        raise ValueError(f"{nome} não está no cofre")
    with _transacao(_arquivo_descricoes(usuario)) as desc:
        desc[nome] = re.sub(r"\s+", " ", para).strip()[:160]


def lista(usuario: str) -> list[tuple[str, str]]:
    """(name, what it is for) of every secret the person has."""
    desc = descricoes(usuario)
    return [(n, desc.get(n, "")) for n in sorted(carregar(usuario))]


def trocar(valor, dados: dict):
    """Placeholders -> values, recursively (only the owner's names; others are left as they are)."""
    if isinstance(valor, str):
        return PADRAO.sub(lambda m: dados.get(m.group(1), m.group(0)), valor)
    if isinstance(valor, dict):
        return {k: trocar(v, dados) for k, v in valor.items()}
    if isinstance(valor, list):
        return [trocar(v, dados) for v in valor]
    return valor


def mascarar(texto: str, dados: dict) -> str:
    for nome, valor in sorted(dados.items(), key=lambda kv: -len(kv[1] or "")):
        if valor and len(valor) >= 4:
            texto = texto.replace(valor, f"§§secret({nome})")
    return texto


def dono(context) -> str:
    import sys

    sep = sys.modules.get("login_usuarios_separacao")
    try:
        return sep.dono_contexto(context) if sep else (context.get_data("dono") or "").lower()
    except Exception:
        return ""

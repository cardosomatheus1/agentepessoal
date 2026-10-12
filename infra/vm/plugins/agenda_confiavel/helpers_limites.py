"""Shared limits of scheduled tasks: minimum interval, end date, run history."""

import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

PASTA = Path("/a0/usr/agenda")
LIMITES = PASTA / "limites.json"     # {uuid: {"ate": epoch | None, "permanente": bool}}
HISTORICO = PASTA / "historico"      # <uuid>.jsonl, last 20 runs
INTERVALO_MINIMO = 10 * 60
VALIDADE_PADRAO = 30 * 24 * 3600
# tasks that existed before limits: no expiry (resumo do dia, radar, nexos, vigia)
# routines that predate the 30-day rule and never expire. 12/10 review: the Nexos watch (H8kWmYP1) left this list;
# it switches itself off when Meta decides and, failing that, ends on the date set in limites.json
EXISTENTES = {"nW924Nkj", "HL76nfIg", "qAvKcIyw"}


class LimitesIlegiveis(RuntimeError):
    pass


# 12/10 review: an unreadable limites.json was read as "no limits", so every routine marked permanent looked like a
# 30-day one and was switched off once 30 days old. Now: unreadable = error (and nothing is switched off), writes
# replace the file whole under a lock.
def carregar() -> dict:
    """{} only when the file does not exist; unreadable after 3 tries = LimitesIlegiveis."""
    if not LIMITES.exists():
        return {}
    for tentativa in range(3):
        try:
            dados = json.loads(LIMITES.read_text(encoding="utf-8"))
            if isinstance(dados, dict):
                return dados
            raise ValueError("não é um objeto JSON")
        except (OSError, ValueError) as exc:
            if tentativa == 2:
                raise LimitesIlegiveis(f"limites.json ilegível ({str(exc)[:60]})") from None
            time.sleep(0.1)
    return {}


def _gravar(arq: Path, texto: str) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=arq.parent, prefix=f".{arq.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, arq)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextmanager
def _trava():
    PASTA.mkdir(parents=True, exist_ok=True)
    with open(PASTA / "limites.lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def salvar(dados: dict) -> None:
    with _trava():
        _gravar(LIMITES, json.dumps(dados, ensure_ascii=False, indent=1))


def definir(uuid: str, registro: dict) -> None:
    """Change one task's limit as one step (read → change → write under the lock)."""
    with _trava():
        dados = carregar()
        dados[uuid] = registro
        _gravar(LIMITES, json.dumps(dados, ensure_ascii=False, indent=1))


def a_desligar(tarefas, dados: dict | None, agora: float, desligada, rodando) -> list:
    """Tasks past their end date. Limits unknown (unreadable file) = none: never switch a routine off when unsure."""
    if dados is None:
        return []
    fora = []
    for task in tarefas:
        reg = dados.get(task.uuid, {})
        if task.uuid in EXISTENTES or reg.get("permanente") or task.state == desligada:
            continue
        criado = task.created_at if task.created_at.tzinfo else task.created_at.replace(tzinfo=timezone.utc)
        ate = reg.get("ate") or (criado.timestamp() + VALIDADE_PADRAO)
        if agora < ate or task.state == rodando:
            continue
        fora.append(task)
    return fora


def menor_intervalo(crontab_txt: str, fuso: str = "UTC") -> float:
    """Smallest gap in seconds between the next 30 runs of a cron line."""
    import pytz
    from crontab import CronTab

    tab = CronTab(crontab_txt)
    agora = datetime.now(timezone.utc).astimezone(pytz.timezone(fuso or "UTC"))
    marcas, t = [], 0.0
    for _ in range(30):
        prox = tab.next(now=agora.timestamp() + t, default_utc=True)
        if prox is None:
            break
        t += prox + 1
        marcas.append(t)
    gaps = [b - a for a, b in zip(marcas, marcas[1:])]
    return min(gaps) if gaps else float("inf")


def registrar_rodada(uuid: str, quando: str, resultado: str) -> None:
    arq = HISTORICO / f"{uuid}.jsonl"
    linhas = historico(uuid)
    if linhas and linhas[-1].get("quando") == quando:
        return
    linhas.append({"quando": quando, "resultado": (resultado or "")[:600]})
    _gravar(arq, "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in linhas[-20:]))


def historico(uuid: str) -> list[dict]:
    arq = HISTORICO / f"{uuid}.jsonl"
    if not arq.exists():
        return []
    saida = []
    for linha in arq.read_text(encoding="utf-8").splitlines():
        try:
            saida.append(json.loads(linha))
        except ValueError:
            continue  # a line cut by an old non-atomic write: skip it, keep the rest
    return saida

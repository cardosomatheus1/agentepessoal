"""Shared limits of scheduled tasks: minimum interval, end date, run history."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

PASTA = Path("/a0/usr/agenda")
LIMITES = PASTA / "limites.json"     # {uuid: {"ate": epoch | None, "permanente": bool}}
HISTORICO = PASTA / "historico"      # <uuid>.jsonl, last 20 runs
INTERVALO_MINIMO = 10 * 60
VALIDADE_PADRAO = 30 * 24 * 3600
# tasks that existed before limits: no expiry (resumo do dia, radar, nexos, vigia)
EXISTENTES = {"nW924Nkj", "HL76nfIg", "H8kWmYP1", "qAvKcIyw"}


def carregar() -> dict:
    try:
        return json.loads(LIMITES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def salvar(dados: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    LIMITES.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


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
    HISTORICO.mkdir(parents=True, exist_ok=True)
    arq = HISTORICO / f"{uuid}.jsonl"
    linhas = arq.read_text(encoding="utf-8").splitlines() if arq.exists() else []
    if linhas and json.loads(linhas[-1]).get("quando") == quando:
        return
    linhas.append(json.dumps({"quando": quando, "resultado": (resultado or "")[:600]}, ensure_ascii=False))
    arq.write_text("\n".join(linhas[-20:]) + "\n", encoding="utf-8")


def historico(uuid: str) -> list[dict]:
    arq = HISTORICO / f"{uuid}.jsonl"
    return [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()] if arq.exists() else []

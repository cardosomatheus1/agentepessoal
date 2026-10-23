"""O limite do dia do convidado (virada, fase 8): o que o A0 fazia em login_usuarios/extensions/python/job_loop/
_20_limite_convidados.py, no Hermes do convidado. A ponte do host grava /a0/usr/whatsapp/<login>/limite_hoje.txt
quando o gasto do dia dele passa do teto; aqui as rotinas dele (o cron deste Hermes) param, e no dia seguinte voltam
só as que foram paradas aqui (convidados.decidir_pausa, a mesma regra). Roda no relógio, só no Hermes de um convidado."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

PLUGINS = Path("/a0/usr/plugins")


def _convidados():
    nome, caminho = "login_usuarios_convidados", PLUGINS / "login_usuarios" / "helpers" / "convidados.py"
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def _jobs():
    from cron import jobs  # o cron do próprio Hermes

    return jobs


def passo(login: str | None = None, jobs=None, hoje: str | None = None) -> dict:
    """Uma passada: {"pausar": [...], "voltar": [...]}."""
    login = login or sys.modules["agentepessoal_ponte_a0"].convidado_da_instancia()
    if not login:
        return {"pausar": [], "voltar": []}
    c, jobs = _convidados(), jobs or _jobs()
    hoje = hoje or dt.datetime.now(ZoneInfo("America/Bahia")).strftime("%Y-%m-%d")
    pasta = c.CELULAR / login
    marca, registro = pasta / "limite_hoje.txt", pasta / "rotinas_pausadas.json"
    passou = marca.exists() and marca.read_text().strip() == hoje
    pausadas = json.loads(registro.read_text()) if registro.exists() else []
    tarefas = [(j["id"], "disabled" if (j.get("state") == "paused" or not j.get("enabled", True)) else "idle")
               for j in jobs.list_jobs(include_disabled=True)]
    pausar, voltar = c.decidir_pausa(passou, tarefas, pausadas)
    for u in pausar:
        jobs.pause_job(u)
    for u in voltar:
        jobs.resume_job(u)
    if pausar or voltar or (pausadas and not passou):
        pasta.mkdir(parents=True, exist_ok=True)
        registro.write_text(json.dumps(sorted(set(pausadas) | set(pausar)) if passou else []))
    return {"pausar": pausar, "voltar": voltar}

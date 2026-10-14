"""Live panel (14/10, from Hermes Agent's live-dashboard skill, MIT): one read-only page in the web UI with the
prospecting funnel, how the posts did and the calendar of the next days, each with the time it was read.

The page never reads the sources itself: a light job (extensions/python/job_loop/_47_painel.py) reads each source when
its interval is due and saves /a0/usr/painel/<login>.json; the page only shows that file. A source that fails keeps its
last good value, marked "desatualizado" with the error and the time of the failure, never an empty block. Only the
existing read functions of the other plugins are called: prospeccao.carregar/metricas/painel and
conteudo.agenda_proxima/desempenho. Nothing here writes anywhere but this plugin's own folder."""

import datetime as dt
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

PASTA = Path(os.environ.get("PAINEL_PASTA", "/a0/usr/painel"))
PLUGINS = Path(os.environ.get("PAINEL_PLUGINS", "/a0/usr/plugins"))
FUSO = "America/Bahia"
DONOS = ("matheus",)          # logins the job keeps a panel for
DONO_CONTEUDO = "matheus"     # the @raiz.connect calendar and Meta token are his
INTERVALO = {"funil": 10 * 60, "agenda": 10 * 60, "desempenho": 3 * 3600}  # desempenho calls Meta once per post
NOVA_TENTATIVA = 15 * 60      # a failed source is tried again after this (or its interval, if shorter)
ESTADO = {"rodando": False}   # the job's guard (this module stays loaded in sys.modules between passes)


def _tz():
    from zoneinfo import ZoneInfo
    return ZoneInfo(FUSO)


def hora(ts) -> str:
    """'14/10 09:12' in Bahia time ('' when never)."""
    return dt.datetime.fromtimestamp(float(ts), _tz()).strftime("%d/%m %H:%M") if ts else ""


def _modulo(nome: str, caminho: Path):
    """Another plugin's helper, loaded by path under this plugin's own name (again when its file changed)."""
    if not caminho.exists():
        raise FileNotFoundError(f"{caminho.parent.parent.name} não está instalado")
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


# ------------------------------------------------------------------ the readers (read-only calls into other plugins)

def ler_funil(login: str) -> dict:
    pr = _modulo("painel_prospeccao", PLUGINS / "prospeccao" / "helpers" / "prospeccao.py")
    d = pr.carregar(login)
    etapas = pr.metricas(login, 7)["etapas"]
    resumo = (pr.painel(login) or "").splitlines()
    return {"proposto": sum(1 for a in d["acoes"] if a.get("estado") == "proposta"),
            "lead": int(etapas.get("lead", 0)), "demo": int(etapas.get("demo", 0)), "teste": int(etapas.get("teste", 0)),
            "cliente": int(etapas.get("cliente", 0)), "resumo": resumo[0] if resumo else ""}


def _conteudo():
    return _modulo("painel_conteudo", PLUGINS / "conteudo" / "helpers" / "conteudo.py")


def ler_agenda(login: str) -> dict:
    return _conteudo().agenda_proxima(7)


def ler_desempenho(login: str) -> dict:
    c = _conteudo()
    api = c.api_do_cofre(login)
    if api is None:
        raise RuntimeError("sem o token da Meta no cofre")
    r = c.desempenho(api, 7)
    if not r.get("ok"):
        raise RuntimeError(r.get("erro") or "a Meta não respondeu")
    return r


LEITORES = {"funil": ler_funil, "agenda": ler_agenda, "desempenho": ler_desempenho}


def fontes_de(login: str) -> tuple:
    return ("funil", "agenda", "desempenho") if login == DONO_CONTEUDO else ("funil",)


# ------------------------------------------------------------------ the saved panel

def _arq(login: str) -> Path:
    return PASTA / f"{''.join(ch for ch in str(login).lower() if ch.isalnum() or ch in '_-')}.json"


def ler(login: str) -> dict | None:
    """The saved panel (what the page shows), or None when there is none yet."""
    arq = _arq(login)
    if not arq.exists():
        return None
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for nome, bloco in (d.get("fontes") or {}).items():  # the times, ready to show
        bloco["lido_as"] = hora(bloco.get("lido_em"))
        bloco["falhou_as"] = hora(bloco.get("falhou_em"))
    d["atualizado_as"] = hora(d.get("atualizado_em"))
    return d


def _gravar(login: str, d: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    arq = _arq(login)
    tmp = arq.with_suffix(f".{os.getpid()}.{time.time_ns()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, arq)


def devidas(d: dict, login: str, agora: float) -> list:
    """Sources whose interval is due (a failed one waits NOVA_TENTATIVA, so Meta is not hammered)."""
    saida = []
    for nome in fontes_de(login):
        b = (d.get("fontes") or {}).get(nome) or {}
        espera = INTERVALO[nome] if not b.get("desatualizado") else min(INTERVALO[nome], NOVA_TENTATIVA)
        if agora - float(b.get("tentado_em") or 0) >= espera:
            saida.append(nome)
    return saida


def atualizar(login: str, leitores: dict | None = None, agora: float | None = None, forcar: bool = False) -> dict:
    """Read the due sources and save. A failure keeps the last good value ("desatualizado")."""
    leitores = leitores or LEITORES
    agora = agora or time.time()
    arq = _arq(login)
    try:
        d = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    except (OSError, ValueError):
        d = {}  # a broken panel file is only a view: it is rebuilt from the sources
    d.setdefault("fontes", {})
    pedidas = list(fontes_de(login)) if forcar else devidas(d, login, agora)
    for nome in pedidas:
        b = d["fontes"].setdefault(nome, {})
        b["tentado_em"] = agora
        try:
            valor = leitores[nome](login)
        except Exception as exc:
            b.update(desatualizado=True, erro=f"{type(exc).__name__}: {str(exc)[:160]}", falhou_em=agora)
            continue
        b.update(valor=valor, lido_em=agora, desatualizado=False, erro="", falhou_em=None)
    if pedidas:
        d["login"], d["atualizado_em"] = login, agora
        _gravar(login, d)
    return d


def passo(agora: float | None = None, leitores: dict | None = None) -> None:
    """One job pass: every panel, only what is due. Never raises (the job loop must go on)."""
    for login in DONOS:
        try:
            atualizar(login, leitores, agora)
        except Exception as exc:
            print(f"painel: {login}: {type(exc).__name__}: {exc}", flush=True)

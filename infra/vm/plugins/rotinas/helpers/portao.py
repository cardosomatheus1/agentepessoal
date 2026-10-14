"""Wake gate of scheduled routines (idea from Hermes cron/monitor.py + the wakeAgent gate).

Before a round, a cheap source read with no model (ids of new e-mails and calendar events through the Google
connector, or a file) is compared with what the last round saw, kept in PASTA/<uuid>.json:
- nothing new: the round is skipped without calling the model;
- something new: the round runs with what changed appended to its prompt;
- a source that fails means "run" (never "no change"), and the first round of each day always runs in full.

The new state is written as pending and only replaces the old one when the round ends without error, so a round
that fails sees the same change again next time (Hermes keeps it at detection time and loses it).
Which routines have a gate, and their sources, lives in ../portao.json."""

import asyncio
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PASTA = Path("/a0/usr/rotinas/portao")
CONFIG = Path(__file__).resolve().parents[1] / "portao.json"
FUSO = ZoneInfo("America/Bahia")
CONTA = "falhanosistema1111@gmail.com"  # the Google account of the agent's connector (workspace-mcp, single user)
ESPERA = 60           # seconds per source; slower counts as an error (= run)
MAX_ITENS = 300
MAX_CONTEXTO = 4000
PULO = "SEM NOVIDADE (portão: nada mudou desde a última rodada)"


class FonteComErro(Exception):
    pass


def config(uuid: str) -> dict | None:
    """The gate of this routine, or None (no gate, switched off, or unreadable config: the round runs as before)."""
    try:
        dados = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cfg = dados.get(uuid) if isinstance(dados, dict) else None
    if not isinstance(cfg, dict) or cfg.get("ligado") is False or not cfg.get("fontes"):
        return None
    return cfg


# ---- sources: each returns {key: text}; anything unexpected raises FonteComErro ----

async def _google(chamar, ferramenta: str, args: dict) -> str:
    ok, texto = await chamar(ferramenta, args)
    if not ok:
        raise FonteComErro(f"{ferramenta}: {str(texto)[:160]}")
    return str(texto or "")


async def fonte_gmail(f: dict, chamar, agora: datetime) -> dict:
    texto = await _google(chamar, "search_gmail_messages", {
        "user_google_email": CONTA, "query": f["busca"], "page_size": int(f.get("max", 30)), "include_headers": True})
    itens, atual = {}, None
    for linha in texto.splitlines():
        m = re.search(r"Message ID:\s*(\S+)", linha)
        if m:
            atual = m.group(1)
            itens[atual] = ""
            continue
        m = re.match(r"\s*(Subject|From):\s*(.*)", linha)
        if atual and m:
            rotulo = "Assunto" if m.group(1) == "Subject" else "De"
            itens[atual] = (itens[atual] + " | " if itens[atual] else "") + f"{rotulo}: {m.group(2).strip()[:100]}"
    if not itens and "No messages found" not in texto:
        raise FonteComErro(f"resposta inesperada do Gmail: {texto[:120]}")
    return itens


async def fonte_agenda(f: dict, chamar, agora: datetime) -> dict:
    hoje = agora.astimezone(FUSO).date()
    texto = await _google(chamar, "get_events", {
        "user_google_email": CONTA, "calendar_id": "primary", "time_min": hoje.isoformat(),
        "time_max": (hoje + timedelta(days=int(f.get("dias", 7)))).isoformat(), "max_results": int(f.get("max", 50))})
    itens = {l.strip(): l.strip()[:200] for l in texto.splitlines() if l.strip().startswith('- "')}
    if not itens and "No events found" not in texto:
        raise FonteComErro(f"resposta inesperada da Agenda: {texto[:120]}")
    return itens


async def fonte_arquivo(f: dict, chamar, agora: datetime) -> dict:
    """A file: its lines, or with "lista" the items of that JSON list (key "id", text = the "campos")."""
    arq = Path(f["caminho"])
    try:
        texto = arq.read_text(encoding="utf-8")
    except OSError as exc:
        raise FonteComErro(f"{arq.name}: {exc}") from None
    if not f.get("lista"):
        return {l.strip(): l.strip()[:200] for l in texto.splitlines() if l.strip()}
    try:
        lista = json.loads(texto)[f["lista"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise FonteComErro(f"{arq.name} ilegível ({str(exc)[:60]})") from None
    campos = f.get("campos") or ["titulo"]
    filtro = f.get("so_estados")
    return {str(i.get("id")): " | ".join(str(i.get(c, "")) for c in campos) for i in lista
            if isinstance(i, dict) and i.get("id") and (not filtro or i.get("estado", "aberto") in filtro)}


FONTES = {"gmail": fonte_gmail, "agenda": fonte_agenda, "arquivo": fonte_arquivo}


async def ler_fontes(cfg: dict, chamar, agora: datetime) -> dict:
    """{source name: {"itens": {...}} | {"erro": "..."}} — never raises."""
    lidas = {}
    for f in cfg["fontes"]:
        nome = f.get("nome") or f.get("tipo")
        try:
            ler = FONTES[f["tipo"]]
            itens = await asyncio.wait_for(ler(f, chamar, agora), ESPERA)
            lidas[nome] = {"itens": dict(list(itens.items())[:MAX_ITENS])}
        except asyncio.TimeoutError:
            lidas[nome] = {"erro": f"sem resposta em {ESPERA} s"}
        except Exception as exc:  # unknown type, connector down, bug: never "no change"
            lidas[nome] = {"erro": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return lidas


# ---- decision ----

def _hash(itens: dict) -> str:
    return hashlib.sha256(json.dumps(sorted(itens.items()), ensure_ascii=False).encode()).hexdigest()


def _dia(agora: datetime) -> str:
    return agora.astimezone(FUSO).date().isoformat()


def decidir(cfg: dict, lidas: dict, estado: dict | None, agora: datetime) -> dict:
    """{"rodar", "motivo" (primeira|erro|diaria|mudou|igual), "mudancas", "erros", "estado" (to keep)}."""
    estado = estado if isinstance(estado, dict) else None
    antigas = (estado or {}).get("fontes") or {}
    so_novos = {(f.get("nome") or f.get("tipo")) for f in cfg["fontes"] if f.get("so_novos")}
    mudancas, erros, fontes = {}, {}, {}
    for nome, lida in lidas.items():
        velha = antigas.get(nome) or {}
        if "erro" in lida:
            erros[nome] = lida["erro"]
            if velha:
                fontes[nome] = velha  # keep what was seen: the next round compares against it again
            continue
        itens = lida["itens"]
        fontes[nome] = {"hash": _hash(itens), "itens": itens}
        if not velha or velha.get("hash") == fontes[nome]["hash"]:
            continue
        antes = velha.get("itens") or {}
        m = {"novos": [f"{k} | {v}" if v and v != k else k for k, v in itens.items() if k not in antes],
             "mudou": [v or k for k, v in itens.items() if k in antes and antes[k] != v],
             "saiu": [] if nome in so_novos else [antes[k] or k for k in antes if k not in itens]}
        if any(m.values()):
            mudancas[nome] = m
    novo = {"fontes": fontes, "rodou_em": (estado or {}).get("rodou_em"),
            "rodou_quando": (estado or {}).get("rodou_quando")}
    if estado is None:
        motivo = "primeira"
    elif erros:
        motivo = "erro"
    elif estado.get("rodou_em") != _dia(agora):
        motivo = "diaria"
    elif mudancas:
        motivo = "mudou"
    else:
        motivo = "igual"
    novas = [n for n in lidas if "erro" not in lidas[n] and n not in antigas]
    if motivo == "igual" and novas:  # a source added to the config: no baseline yet
        motivo = "primeira"
    rodar = motivo != "igual"
    if rodar:
        novo["rodou_em"], novo["rodou_quando"] = _dia(agora), agora.isoformat(timespec="minutes")
    else:
        novo["pulada_quando"] = agora.isoformat(timespec="minutes")
    return {"rodar": rodar, "motivo": motivo, "mudancas": mudancas, "erros": erros, "estado": novo,
            "desde": (estado or {}).get("rodou_quando")}


def contexto(decisao: dict) -> str:
    """What the round gets appended to its prompt."""
    desde = decisao.get("desde")
    try:
        desde = datetime.fromisoformat(desde).astimezone(FUSO).strftime("%d/%m %H:%M") if desde else ""
    except ValueError:
        desde = ""
    motivo = decisao["motivo"]
    linhas = ["## Portão da rotina (conferido sem IA antes desta rodada)"]
    if motivo == "primeira":
        linhas.append("Primeira rodada com portão: faça a rodada completa.")
    elif motivo == "erro":
        linhas.append("Não deu para conferir " + "; ".join(f"{n} ({e})" for n, e in decisao["erros"].items())
                      + ": faça a rodada completa.")
    elif motivo == "diaria":
        linhas.append("Rodada completa do dia: siga todos os passos, sem se limitar ao que mudou.")
    else:
        linhas.append(f"Desde a última rodada{f' ({desde})' if desde else ''} mudou só o que está abaixo; o resto já "
                      "foi visto. Concentre-se nisso, seguindo os passos da rotina.")
    for nome, m in decisao["mudancas"].items():
        partes = [f"{len(m[k])} {r}" for k, r in (("novos", "novo(s)"), ("mudou", "mudou(aram)"), ("saiu", "saiu(íram)"))
                  if m[k]]
        linhas.append(f"- {nome}: {', '.join(partes)}")
        linhas += [f"  + {x}" for x in m["novos"]] + [f"  ~ {x}" for x in m["mudou"]] + [f"  - {x}" for x in m["saiu"]]
    texto = "\n".join(linhas)
    return texto if len(texto) <= MAX_CONTEXTO else texto[:MAX_CONTEXTO] + "\n  … (cortado; confira a fonte)"


# ---- state ----

def _arq(uuid: str, sufixo: str = "") -> Path:
    return PASTA / f"{re.sub(r'[^A-Za-z0-9_-]', '', uuid)}{sufixo}.json"


def carregar_estado(uuid: str) -> dict | None:
    """None when there is none or it cannot be read (= first round: runs in full)."""
    try:
        dados = json.loads(_arq(uuid).read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else None
    except (OSError, ValueError):
        return None


def _gravar(arq: Path, dados: dict) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=arq.parent, prefix=f".{arq.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(dados, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, arq)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def preparar(uuid: str, decisao: dict) -> None:
    """The round runs: keep the new state aside until it ends well."""
    _gravar(_arq(uuid, ".pendente"), decisao["estado"])


def confirmar(uuid: str) -> bool:
    try:
        os.replace(_arq(uuid, ".pendente"), _arq(uuid))
        return True
    except OSError:
        return False


def descartar(uuid: str) -> None:
    _arq(uuid, ".pendente").unlink(missing_ok=True)


def registrar_pulo(uuid: str, decisao: dict) -> None:
    _gravar(_arq(uuid), decisao["estado"])


async def avaliar(uuid: str, cfg: dict, chamar, agora: datetime | None = None) -> dict:
    agora = agora or datetime.now(FUSO)
    lidas = await ler_fontes(cfg, chamar, agora)
    return decidir(cfg, lidas, carregar_estado(uuid), agora)

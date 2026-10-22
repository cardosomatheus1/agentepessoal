"""The Tarefas board (22/10, from Claude Duet's Tasks tab: Active / Up next / Scheduled / Resolved, "only you can mark a
task as completed", each task its own sub-chat). It only reads what already exists and shows it in one place:

- the loose ends of plugins/fios_soltos (the register of what is open, whose it is, its next step): Ativas (open),
  A conferir (the agent says it finished; only he closes), Próximas (postponed), Resolvidas (last 14 days);
- the goals of /goal that are still running (Ativas);
- the scheduled routines (/a0/usr/scheduler/tasks.json: name, when, last run and result), read only.

Writes go through fios_soltos only (concluir, reabrir); "Faz pra mim" is done by the API (a chat of its own)."""

import datetime as dt
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

PLUGINS = Path(os.environ.get("QUADRO_PLUGINS", "/a0/usr/plugins"))
TAREFAS = Path(os.environ.get("QUADRO_TAREFAS", "/a0/usr/scheduler/tasks.json"))
OBJETIVOS = Path(os.environ.get("QUADRO_OBJETIVOS", "/a0/usr/plugins/_goal/goals"))
FUSO = "America/Bahia"
DIAS = ("dom", "seg", "ter", "qua", "qui", "sex", "sáb")  # cron weekday numbers: 0 = Sunday


def fios():
    """plugins/fios_soltos/helpers/fios.py, reloaded when it changes."""
    caminho = PLUGINS / "fios_soltos" / "helpers" / "fios.py"
    nome = "quadro_fios"
    antigo = sys.modules.get(nome)
    if antigo is None or getattr(antigo, "_mtime", None) != caminho.stat().st_mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = caminho.stat().st_mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def _hora(ts) -> str:
    from zoneinfo import ZoneInfo
    try:
        if isinstance(ts, str):
            d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            d = dt.datetime.fromtimestamp(float(ts), dt.timezone.utc)
        return d.astimezone(ZoneInfo(FUSO)).strftime("%d/%m %H:%M")
    except Exception:
        return ""


def quando(schedule: dict) -> str:
    """'todo dia 07:45', 'seg 08:52', 'dia 1 09:07', 'a cada hora' from the scheduler's cron fields."""
    s = schedule or {}
    minuto, hora = str(s.get("minute", "*")), str(s.get("hour", "*"))
    dia, semana = str(s.get("day", "*")), str(s.get("weekday", "*"))
    if hora == "*":
        return "a cada hora" if minuto != "*" else "o tempo todo"
    horas = ", ".join(f"{int(h):02d}:{int(minuto):02d}" if minuto.isdigit() and h.isdigit() else f"{h}:{minuto}"
                      for h in hora.split(","))
    if semana != "*":
        nomes = []
        for parte in semana.split(","):
            if "-" in parte and all(x.isdigit() for x in parte.split("-")):
                a, b = (int(x) % 7 for x in parte.split("-"))
                nomes.append(f"{DIAS[a]} a {DIAS[b]}")
            elif parte.isdigit():
                nomes.append(DIAS[int(parte) % 7])
            else:
                nomes.append(parte)
        return f"{', '.join(nomes)} {horas}"
    if dia != "*":
        return f"dia {dia} {horas}"
    return f"todo dia {horas}"


def _cartao(f: dict) -> dict:
    return {"id": f.get("id"), "titulo": f.get("titulo", ""), "detalhe": f.get("detalhe", ""),
            "dono": f.get("dono", ""), "prazo": f.get("prazo", ""), "prioridade": f.get("prioridade", ""),
            "proximo_passo": f.get("proximo_passo", ""), "area": f.get("area", ""), "estado": f.get("estado", "aberto"),
            "nota": f.get("nota_agente", ""), "adiar_ate": f.get("adiar_ate", ""), "conversa": f.get("conversa", ""),
            "atualizado_as": _hora(f.get("atualizado")), "atualizado": float(f.get("atualizado") or 0)}


def agendadas() -> list:
    try:
        tarefas = json.loads(TAREFAS.read_text(encoding="utf-8")).get("tasks", [])
    except Exception:
        return []
    saida = []
    for t in tarefas:
        if t.get("state") == "disabled" or not t.get("schedule"):
            continue
        resultado = " ".join(str(t.get("last_result") or "").split())
        saida.append({"nome": t.get("name", ""), "quando": quando(t.get("schedule")), "ultima": _hora(t.get("last_run")),
                      "resultado": resultado[:160] + ("…" if len(resultado) > 160 else ""),
                      "rodando": t.get("state") == "running"})
    return sorted(saida, key=lambda x: x["nome"])


def objetivos() -> list:
    saida = []
    for g in sorted(OBJETIVOS.glob("*.json")) if OBJETIVOS.exists() else []:
        try:
            o = json.loads(g.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(o.get("status") or "").lower() in ("active", "ativo", "running", "blocked", "bloqueado"):
            saida.append({"titulo": str(o.get("objective") or o.get("goal") or o.get("objetivo") or "")[:200],
                          "estado": o.get("status"), "nota": str(o.get("note") or o.get("nota") or "")[:200]})
    return saida


def montar(login: str, agora: float | None = None) -> dict:
    agora = time.time() if agora is None else agora
    hoje = dt.datetime.fromtimestamp(agora).strftime("%Y-%m-%d")
    registro = fios().carregar(login)["fios"]
    colunas = {"ativas": [], "conferir": [], "proximas": [], "resolvidas": []}
    for f in registro:
        estado = f.get("estado", "aberto")
        if estado == "aberto" or (estado == "adiado" and str(f.get("adiar_ate", "")) <= hoje):
            colunas["ativas"].append(_cartao(f))
        elif estado == "adiado":
            colunas["proximas"].append(_cartao(f))
        elif estado == "a_conferir":
            colunas["conferir"].append(_cartao(f))
        elif estado in ("resolvido", "ignorado") and agora - float(f.get("atualizado") or 0) < 14 * 86400:
            colunas["resolvidas"].append(_cartao(f))
    prioridade = {"alta": 0, "media": 1, "média": 1, "baixa": 2}
    colunas["ativas"].sort(key=lambda c: (prioridade.get(str(c["prioridade"]).lower(), 1), c["prazo"] or "9999"))
    colunas["proximas"].sort(key=lambda c: c["adiar_ate"])
    colunas["resolvidas"].sort(key=lambda c: c["atualizado"], reverse=True)
    return {**colunas, "objetivos": objetivos(), "agendadas": agendadas(), "lido_as": _hora(agora)}


def texto_fazer(f: dict) -> str:
    """What the task's own chat receives when he taps "Faz pra mim" on the board (the same rules as the phone button)."""
    return (f"▶ Faz pra mim (tarefa {f.get('id')} do quadro): {f.get('titulo', '')}.\n"
            + (f"O que está em aberto: {f['detalhe']}\n" if f.get("detalhe") else "")
            + (f"Ligação: {f['ligacoes']}\n" if f.get("ligacoes") else "")
            + (f"Próximo passo combinado: {f['proximo_passo']}\n" if f.get("proximo_passo") else "")
            + "Esta conversa é só desta tarefa. Faça o próximo passo agora. Peça minha aprovação antes de qualquer coisa "
              "que envie, pague, apague ou mude algo fora daqui; se depender de mim, me diga exatamente o quê. Quando "
              f"terminar, marque o fio {f.get('id')} como feito (ferramenta fios, acao resolver, com uma nota do que fez: "
              "eu confiro e fecho no quadro) e me diga em poucas linhas o que fez.")

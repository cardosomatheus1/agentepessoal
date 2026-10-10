"""Loose ends ("fios soltos"): a per-person register of what is still open, plus a digest of everything
recent (chats, scheduled tasks, notices, goals, approvals, memory) for the model to cross-check."""

import ast
import json
import re
import time
import uuid
from pathlib import Path

PASTA = Path("/a0/usr/fios")
CHATS = Path("/a0/usr/chats")
TAREFAS = Path("/a0/usr/scheduler/tasks.json")
OBJETIVOS = Path("/a0/usr/plugins/_goal/goals")
MEMORIA = Path("/a0/usr/memoria/usuarios")
APROVACOES = Path("/a0/usr/aprovacoes/atividade")
NOME_TAREFA = "🧵 Fios soltos"
PENDENCIA = re.compile(r"pendente|aguardando|bloquead|travad|falta |próximo passo|depende de você|precisa de você|"
                       r"não consegui|vence|prazo|lembr", re.I)
PRIORIDADE = {"alta": 0, "media": 1, "média": 1, "baixa": 2}


def _login(login: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "", (login or "").lower()) or "matheus"


def arquivo(login: str) -> Path:
    return PASTA / f"{_login(login)}.json"


def carregar(login: str) -> dict:
    try:
        dados = json.loads(arquivo(login).read_text(encoding="utf-8"))
        dados.setdefault("fios", [])
        return dados
    except Exception:
        return {"fios": []}


def salvar(login: str, dados: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    agora = time.time()
    # resolved/ignored ones are kept 14 days, so a later round does not recreate them
    dados["fios"] = [f for f in dados.get("fios", [])
                     if f.get("estado", "aberto") in ("aberto", "adiado") or agora - f.get("atualizado", agora) < 14 * 86400]
    arquivo(login).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


def mesclar(login: str, novos: list, resolvidos: list | None = None) -> tuple[int, int, int]:
    dados = carregar(login)
    por_id = {f["id"]: f for f in dados["fios"] if f.get("id")}
    agora = time.time()
    criados = atualizados = fechados = 0
    for item in novos or []:
        if not isinstance(item, dict) or not (item.get("titulo") or item.get("id")):
            continue
        fid = str(item.get("id") or "").strip()
        if fid and fid in por_id:
            por_id[fid].update({k: v for k, v in item.items() if v not in (None, "")})
            por_id[fid]["atualizado"] = agora
            atualizados += 1
            continue
        fio = {"id": fid or uuid.uuid4().hex[:6], "estado": "aberto", "criado": agora, "atualizado": agora}
        fio.update({k: v for k, v in item.items() if v not in (None, "") and k != "id"})
        dados["fios"].append(fio)
        por_id[fio["id"]] = fio
        criados += 1
    for fid in resolvidos or []:
        fio = por_id.get(str(fid))
        if fio and fio.get("estado") != "resolvido":
            fio.update({"estado": "resolvido", "atualizado": agora})
            fechados += 1
    salvar(login, dados)
    return criados, atualizados, fechados


def abertos(login: str, limite: int = 8) -> list:
    hoje = time.strftime("%Y-%m-%d")
    lista = [f for f in carregar(login)["fios"]
             if f.get("estado", "aberto") == "aberto" or (f.get("estado") == "adiado" and str(f.get("adiar_ate", "")) <= hoje)]
    lista.sort(key=lambda f: (PRIORIDADE.get(str(f.get("prioridade", "media")).lower(), 1), str(f.get("prazo") or "9999")))
    return lista[:limite]


def linha(f: dict) -> str:
    extras = [x for x in (f.get("dono") and f"de {f['dono']}", f.get("prazo") and f"prazo {f['prazo']}",
                          f.get("prioridade") and f"prioridade {f['prioridade']}") if x]
    texto = f"[{f.get('id')}] {f.get('titulo', '')}"
    if f.get("proximo_passo"):
        texto += f" → {f['proximo_passo']}"
    if f.get("ligacoes"):
        texto += f" (liga com: {f['ligacoes']})"
    return texto + (f" ({', '.join(extras)})" if extras else "")


def _kv(valor):
    if isinstance(valor, dict):
        return valor
    try:
        return ast.literal_eval(valor) if isinstance(valor, str) and valor.startswith("{") else {}
    except Exception:
        return {}


def _curto(texto, n):
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()
    return texto if len(texto) <= n else texto[: n - 1] + "…"


def conversas(login: str, horas: int = 72, ignorar: str = "") -> list[dict]:
    limite = time.time() - horas * 3600
    saida = []
    for arq in CHATS.glob("*/chat.json"):
        try:
            if arq.stat().st_mtime < limite or arq.parent.name == ignorar:
                continue
            d = json.loads(arq.read_text(encoding="utf-8"))
        except Exception:
            continue
        dono = (d.get("data") or {}).get("dono") or "matheus"
        if _login(dono) != _login(login) or NOME_TAREFA in str(d.get("name") or ""):
            continue
        logs = (d.get("log") or {}).get("logs") or []
        usuario = []
        for x in logs:
            if x.get("type") != "user":
                continue
            u = str(x.get("content", ""))
            u = _curto(u, 120) if u.lstrip().startswith("## Task") else u  # a scheduled round repeats its whole prompt
            if u not in usuario:
                usuario.append(u)
        usuario = usuario[-2:]
        respostas = [x.get("content", "") for x in logs if x.get("type") == "response" and x.get("content")][-1:]
        avisos = []
        for x in logs:
            k = _kv(x.get("kvps"))
            if k.get("_tool_name") == "notify_user" or "notify_user" in str(x.get("heading", "")):
                if k.get("title") or k.get("message"):
                    avisos.append(f"{k.get('title', '')}: {k.get('message', '')}")
        pendencias = []
        ctx = arq.parent / "contexto.md"
        if ctx.exists():
            pendencias = [l.strip() for l in ctx.read_text(encoding="utf-8", errors="ignore").splitlines() if PENDENCIA.search(l)][-5:]
        saida.append({"id": arq.parent.name, "nome": d.get("name") or f"Chat {arq.parent.name}",
                      "mudou_ha_h": round((time.time() - arq.stat().st_mtime) / 3600, 1),
                      "pedidos": [_curto(u, 300) for u in usuario], "ultima_resposta": _curto(respostas[0], 500) if respostas else "",
                      "avisos": [_curto(a, 300) for a in avisos[-3:]], "pendencias": [_curto(p, 200) for p in pendencias]})
    saida.sort(key=lambda c: c["mudou_ha_h"])
    return saida


def coletar(login: str, horas: int = 72, ignorar: str = "") -> str:
    partes = [f"# Panorama das últimas {horas} h ({time.strftime('%d/%m %H:%M')})"]
    regs = carregar(login)["fios"]
    if regs:
        partes.append("## Registro de fios atual\n" + "\n".join(
            f"- {linha(f)} [estado: {f.get('estado', 'aberto')}, desde {time.strftime('%d/%m', time.localtime(f.get('criado', time.time())))}]"
            for f in regs))
    convs = conversas(login, horas, ignorar)
    if convs:
        blocos = []
        for c in convs[:25]:
            b = [f"### {c['nome']} (id {c['id']}, mudou há {c['mudou_ha_h']} h)"]
            b += [f"- pediu: {p}" for p in c["pedidos"]]
            if c["ultima_resposta"]:
                b.append(f"- última resposta: {c['ultima_resposta']}")
            b += [f"- aviso: {a}" for a in c["avisos"]]
            b += [f"- pendência anotada: {p}" for p in c["pendencias"]]
            blocos.append("\n".join(b))
        partes.append("## Conversas\n" + "\n\n".join(blocos))
        # the register, tasks and memory matter more than the oldest chats: cap chats so they fit
    try:
        tarefas = json.loads(TAREFAS.read_text(encoding="utf-8")).get("tasks", [])
        linhas = [f"- {t.get('name')} [{t.get('state')}] última {str(t.get('last_run') or '')[:16]}: {_curto(t.get('last_result'), 300)}"
                  for t in tarefas if t.get("name") != NOME_TAREFA]
        if linhas:
            partes.append("## Tarefas agendadas\n" + "\n".join(linhas))
    except Exception:
        pass
    objs = []
    for g in OBJETIVOS.glob("*.json"):
        try:
            o = json.loads(g.read_text(encoding="utf-8"))
            objs.append(f"- [{o.get('status')}] {_curto(o.get('objective') or o.get('goal') or o.get('objetivo'), 200)} — {_curto(o.get('note') or o.get('nota'), 200)}")
        except Exception:
            continue
    if objs:
        partes.append("## Objetivos (/goal)\n" + "\n".join(objs[-10:]))
    ap = APROVACOES / f"{_login(login)}.jsonl"
    if ap.exists():
        partes.append("## Ações com aprovação (recentes)\n" + "\n".join(
            "- " + _curto(l, 250) for l in ap.read_text(encoding="utf-8", errors="ignore").splitlines()[-10:]))
    mem = MEMORIA / f"{_login(login)}.md"
    if mem.exists():
        partes.append("## Memória sobre a pessoa\n" + _curto(mem.read_text(encoding="utf-8", errors="ignore"), 2500))
    texto = "\n\n".join(partes)
    return texto[:24000]

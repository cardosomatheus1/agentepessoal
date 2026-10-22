"""Loose ends ("fios soltos"): a per-person register of what is still open, plus a digest of everything
recent (chats, scheduled tasks, notices, goals, approvals, memory) for the model to cross-check.

20/10 (ADR 0001): for the owner, once the Segundo Cérebro's Pasta is migrated, the register lives there: each loose end
is a Pendência, one file in Pendencias/ (plugins/cerebro/helpers/pasta.py); "ruido" and other register-wide keys in
Pendencias/.meta.json. This module stays the only writer; what it drops goes to Arquivo-morto/, never deleted."""

import ast
import fcntl
import functools
import importlib.util
import json
import sys
import os
import re
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
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


# ------------------------------------------------------------------ safe state file
# 12/10 review: an unreadable register was read as empty and the next save wiped every loose end (and the "ignored"
# list, so dismissed subjects came back); two writers could overwrite each other. Now: one writer at a time per
# person (a short file lock), the file replaced whole, and an unreadable file stops the change instead.
ESPERA_TRAVA = 30  # seconds; writes take milliseconds
_DONO = threading.local()


class EstadoIlegivel(RuntimeError):
    pass


def _do_cerebro(nome: str, arquivo: str):
    """A helper of plugins/cerebro (helpers/<arquivo>), reloaded when it changes; None if absent."""
    caminho = Path(__file__).resolve().parents[2] / "cerebro" / "helpers" / arquivo
    if nome not in sys.modules and not caminho.exists():
        return None
    antigo = sys.modules.get(nome)
    if antigo is not None and Path(getattr(antigo, "__file__", "") or "").resolve() != caminho.resolve():
        return antigo  # loaded from another copy (the cerebro plugin itself, a staging copy, a test): that one wins
    if antigo is None or (caminho.exists() and getattr(antigo, "_mtime", None) != caminho.stat().st_mtime):
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = caminho.stat().st_mtime
        if antigo is not None and hasattr(antigo, "RAIZ"):
            modulo.RAIZ = antigo.RAIZ  # a test (or the operator) may point it elsewhere
        sys.modules[nome] = modulo
    return sys.modules[nome]


def pasta():
    """plugins/cerebro/helpers/pasta.py (the Segundo Cérebro's Pasta), reloaded when it changes; None if absent."""
    return _do_cerebro("cerebro_pasta", "pasta.py")


def area_de(*textos) -> tuple[str, set]:
    """(guessed Área, valid Áreas) from the cerebro's one keyword table (helpers/migracao.py area_de/AREAS);
    ("geral", {"geral"}) when that plugin is absent or fails."""
    try:
        m = _do_cerebro("cerebro_migracao", "migracao.py")
        if m is not None:
            return m.area_de(*textos), {a for a, _ in m.AREAS} | {"geral"}
    except Exception:
        pass
    return "geral", {"geral"}


def _com_area(fio: dict) -> None:
    """Every Pendência carries its Área (20/10): a missing or unknown one gets the deterministic guess."""
    palpite, validas = area_de(fio.get("titulo"), fio.get("detalhe"), fio.get("ligacoes"))
    atual = str(fio.get("area") or "").strip().lower()
    fio["area"] = atual if atual in validas else palpite


def na_pasta(login: str) -> bool:
    p = pasta()
    return bool(p and p.ativa(login))


@contextmanager
def _exclusivo(login: str):
    """One writer at a time per person, across threads and processes; re-entrant in the same thread."""
    chave = _login(login)
    travas = getattr(_DONO, "travas", None)
    if travas is None:
        travas = _DONO.travas = {}
    if travas.get(chave):
        travas[chave] += 1
        try:
            yield
        finally:
            travas[chave] -= 1
        return
    PASTA.mkdir(parents=True, exist_ok=True)
    with open(PASTA / f"{chave}.lock", "a") as fh:
        limite = time.time() + ESPERA_TRAVA
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() > limite:
                    raise RuntimeError("o registro de fios está ocupado há mais de 30 s; tente de novo") from None
                time.sleep(0.05)
        travas[chave] = 1
        try:
            yield
        finally:
            travas[chave] = 0
            fcntl.flock(fh, fcntl.LOCK_UN)


def _transacao(fn):
    """Load → change → save as one step for the person in the first argument."""
    @functools.wraps(fn)
    def envolta(login, *args, **kwargs):
        with _exclusivo(login):
            return fn(login, *args, **kwargs)
    return envolta


def carregar(login: str) -> dict:
    if na_pasta(login):
        p = pasta()
        meta = p.RAIZ / "Pendencias" / ".meta.json"
        try:
            dados = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
            dados["fios"] = sorted(p.ler("pendencias"), key=lambda f: f.get("criado", 0))
        except (p.Ilegivel, OSError, ValueError) as exc:
            raise EstadoIlegivel(f"uma pendência da Pasta não pôde ser lida ({str(exc)[:60]}); nada foi gravado") from None
        return dados
    arq = arquivo(login)
    dados = {}
    if arq.exists():
        for tentativa in range(3):
            try:
                dados = json.loads(arq.read_text(encoding="utf-8"))
                if not isinstance(dados, dict):
                    raise ValueError("não é um objeto JSON")
                break
            except (OSError, ValueError) as exc:
                if tentativa == 2:
                    raise EstadoIlegivel(f"o registro de fios ({arq.name}) não pôde ser lido ({str(exc)[:60]}); "
                                         "nada foi gravado") from None
                time.sleep(0.1)
    dados.setdefault("fios", [])
    return dados


def salvar(login: str, dados: dict) -> None:
    with _exclusivo(login):
        agora = time.time()
        # resolved/ignored ones are kept 14 days, so a later round does not recreate them
        dados["fios"] = [f for f in dados.get("fios", [])
                         if f.get("estado", "aberto") in ("aberto", "adiado", "a_conferir")
                         or agora - f.get("atualizado", agora) < 14 * 86400]
        if na_pasta(login):
            p = pasta()
            p.gravar("pendencias", dados["fios"])
            p.escrever(p.RAIZ / "Pendencias" / ".meta.json",
                       json.dumps({k: v for k, v in dados.items() if k != "fios"}, ensure_ascii=False, indent=1))
            return
        fd, tmp = tempfile.mkstemp(dir=PASTA, prefix=f".{_login(login)}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, arquivo(login))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


ID_OK = re.compile(r"^[A-Za-z0-9_-]{1,40}$")  # 12/10: the model sent "[new fio id from previous result not returned]"


@_transacao
def mesclar(login: str, novos: list, resolvidos: list | None = None) -> tuple[int, int, int]:
    dados = carregar(login)
    por_id = {f["id"]: f for f in dados["fios"] if f.get("id")}
    agora = time.time()
    do_dono = na_pasta(login)  # the owner's Pendências carry an Área; guests' register is unchanged
    criados = atualizados = fechados = 0
    for item in novos or []:
        if not isinstance(item, dict) or not (item.get("titulo") or item.get("id")):
            continue
        fid = str(item.get("id") or "").strip()
        if fid and fid not in por_id and not ID_OK.match(fid):
            fid = ""  # not an id (a placeholder or a sentence): a new one, never a file named after the text
        if fid and fid in por_id:
            por_id[fid].update({k: v for k, v in item.items() if v not in (None, "")})
            if do_dono:
                _com_area(por_id[fid])
            por_id[fid]["atualizado"] = agora
            atualizados += 1
            continue
        fio = {"id": fid or uuid.uuid4().hex[:6], "estado": "aberto", "criado": agora, "atualizado": agora}
        fio.update({k: v for k, v in item.items() if v not in (None, "") and k != "id"})
        if do_dono:
            _com_area(fio)
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


# 22/10 (Claude Duet: "only you can mark a task as completed"): what the agent says it finished goes to "a_conferir";
# only the person closes it (the Tarefas board, or his own words through the tool's `pedido_dele`).
@_transacao
def para_conferir(login: str, ids: list, nota: str = "") -> int:
    dados = carregar(login)
    agora, n = time.time(), 0
    for fio in dados["fios"]:
        if str(fio.get("id")) in {str(i) for i in ids or []} and fio.get("estado", "aberto") in ("aberto", "adiado"):
            fio.update({"estado": "a_conferir", "atualizado": agora, **({"nota_agente": str(nota)[:300]} if nota else {})})
            n += 1
    salvar(login, dados)
    return n


@_transacao
def concluir(login: str, fid: str, por: str) -> dict | None:
    """Closed by the person (board button or his words): resolved, with who and when."""
    dados = carregar(login)
    fio = next((f for f in dados["fios"] if str(f.get("id")) == str(fid)), None)
    if not fio or fio.get("estado") == "resolvido":
        return None
    fio.update({"estado": "resolvido", "atualizado": time.time(), "concluido_por": str(por)[:120]})
    salvar(login, dados)
    return fio


@_transacao
def reabrir(login: str, fid: str) -> dict | None:
    dados = carregar(login)
    fio = next((f for f in dados["fios"] if str(f.get("id")) == str(fid)), None)
    if not fio or fio.get("estado") == "aberto":
        return None
    fio.update({"estado": "aberto", "atualizado": time.time()})
    fio.pop("adiar_ate", None)
    salvar(login, dados)
    return fio


def a_conferir(login: str) -> list:
    return sorted((f for f in carregar(login)["fios"] if f.get("estado") == "a_conferir"),
                  key=lambda f: -f.get("atualizado", 0))


@_transacao
def juntar_duplicata(login: str, duplicada: str, original: str, por: str) -> dict:
    """The same loose end recorded twice: the copy leaves the list (with the Pasta it goes to Arquivo-morto, never
    deleted) and what it said stays in the original's `juntou`. Only the operator, only with the same title."""
    if not str(por or "").startswith("operador:"):
        raise ValueError("quem junta é o operador: por='operador: <motivo>'")
    dados = carregar(login)
    por_id = {str(f.get("id")): f for f in dados["fios"]}
    copia, orig = por_id.get(str(duplicada)), por_id.get(str(original))
    if not copia or not orig or copia is orig:
        raise ValueError("as duas pendências precisam existir e ser diferentes")
    norm = lambda t: " ".join(str(t or "").lower().split())  # noqa: E731
    if norm(copia.get("titulo")) != norm(orig.get("titulo")):
        raise ValueError("títulos diferentes: não são a mesma pendência")
    orig["juntou"] = (orig.get("juntou") or []) + [{
        "id": copia.get("id"), "detalhe": copia.get("detalhe", ""), "fontes": copia.get("fontes", ""),
        "proximo_passo": copia.get("proximo_passo", ""), "criado": copia.get("criado"), "por": por, "em": time.time()}]
    dados["fios"] = [f for f in dados["fios"] if f is not copia]
    salvar(login, dados)
    return orig


@_transacao
def ignorar(login: str, fid: str) -> dict | None:
    """The person tapped "Ignorar": close it and remember the subject as noise for later rounds."""
    dados = carregar(login)
    fio = next((f for f in dados["fios"] if f.get("id") == fid), None)
    if not fio:
        return None
    fio.update({"estado": "ignorado", "atualizado": time.time()})
    dados["ruido"] = (dados.get("ruido", []) + [fio.get("titulo", "")])[-50:]
    salvar(login, dados)
    return fio


@_transacao
def adiar(login: str, fid: str, dias: int = 1) -> dict | None:
    dados = carregar(login)
    fio = next((f for f in dados["fios"] if f.get("id") == fid), None)
    if not fio:
        return None
    fio.update({"estado": "adiado", "adiar_ate": time.strftime("%Y-%m-%d", time.localtime(time.time() + dias * 86400)),
                "atualizado": time.time()})
    salvar(login, dados)
    return fio


def obter(login: str, fid: str) -> dict | None:
    return next((f for f in carregar(login)["fios"] if f.get("id") == fid), None)


def mensagem(fio: dict, urgente: bool = False) -> str:
    """One loose end as a phone message (the buttons go below it)."""
    partes = [("⚠️ *Precisa de você*\n" if urgente else "") + f"🧵 *{fio.get('titulo', '')}*"]
    if fio.get("detalhe"):
        partes.append(str(fio["detalhe"]))
    if fio.get("ligacoes"):
        partes.append(f"🔗 *Ligação:* {fio['ligacoes']}")
    if fio.get("proximo_passo"):
        partes.append(f"👉 *Posso:* {fio['proximo_passo']}")
    if fio.get("prazo"):
        partes.append(f"📅 Prazo: {fio['prazo']}")
    return "\n\n".join(partes)


def botoes(login: str, fid: str) -> list:
    base = f"fio:{_login(login)}:{fid}"
    return [{"id": f"{base}:fazer", "titulo": "✅ Faz pra mim"}, {"id": f"{base}:amanha", "titulo": "⏰ Amanhã"},
            {"id": f"{base}:ignorar", "titulo": "🙈 Ignorar"}]


def abertos(login: str, limite: int = 8) -> list:
    hoje = time.strftime("%Y-%m-%d")
    lista = [f for f in carregar(login)["fios"]
             if f.get("estado", "aberto") == "aberto" or (f.get("estado") == "adiado" and str(f.get("adiar_ate", "")) <= hoje)]
    lista.sort(key=lambda f: (PRIORIDADE.get(str(f.get("prioridade", "media")).lower(), 1), str(f.get("prazo") or "9999")))
    return lista[:limite]


def resolvidos_recentes(login: str, dias: int = 7, limite: int = 8) -> list:
    """Closed loose ends (resolved or ignored) of the last days, so no round alerts about them again."""
    corte = time.time() - dias * 86400
    lista = [f for f in carregar(login)["fios"]
             if f.get("estado") in ("resolvido", "ignorado") and f.get("atualizado", 0) > corte]
    return sorted(lista, key=lambda f: -f.get("atualizado", 0))[:limite]


def linha(f: dict) -> str:
    extras = [x for x in (f.get("dono") and f"de {f['dono']}", f.get("prazo") and f"prazo {f['prazo']}",
                          f.get("prioridade") and f"prioridade {f['prioridade']}") if x]
    texto = f"[{f.get('id')}] {f.get('titulo', '')}"
    if f.get("proximo_passo"):
        texto += f" → {f['proximo_passo']}"
    if f.get("ligacoes"):
        texto += f" (liga com: {f['ligacoes']})"
    return texto + (f" ({', '.join(extras)})" if extras else "")


def linha_curta(f: dict) -> str:
    """For the list that goes with every message (20/10, token): id, title, deadline and priority; the next step and
    the links stay in `fios` acao "listar" (the full line)."""
    extras = [x for x in (f.get("prazo") and f"prazo {f['prazo']}", f.get("prioridade") and f"prioridade {f['prioridade']}")
              if x]
    return f"[{f.get('id')}] {_curto(f.get('titulo', ''), 110)}" + (f" ({', '.join(extras)})" if extras else "")


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
    dados = carregar(login)
    regs = dados["fios"]
    if dados.get("ruido"):
        partes.append("## A pessoa pediu para NÃO trazer (ignorou) — não avise nada parecido\n" +
                      "\n".join(f"- {r}" for r in dados["ruido"][-20:]))
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

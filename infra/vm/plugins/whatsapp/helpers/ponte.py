"""Talk to the host's ponte_whatsapp (infra/vm/ponte_whatsapp.py).

The bridge holds the Meta token and the phone numbers; here people are addressed only by
their login name, so the agent can reach no one but the registered users.
"""

import hashlib
import json
import os
import re
import tempfile
import time
import urllib.request
from pathlib import Path

URL = "http://host.docker.internal:8789/enviar"
_abrir = urllib.request.urlopen  # the bridge call (tests replace it in their own copy)
PEDIDOS: dict[str, dict] = {}  # login -> code the agent asked for on WhatsApp (pedir_codigo)
CHAVE = Path("/a0/usr/whatsapp/.chave")
CAIXA_TESTES = Path("/a0/usr/testes/celular.jsonl")  # phone messages of "teste_*" logins (tests)


def chave() -> str:
    try:
        return CHAVE.read_text().strip()
    except OSError:
        return ""


CAMPOS_BILHETE = ("usuario", "conversa", "gatilho", "botao", "texto", "audio", "anexos")  # same as the bridge's


def resumo_entrega(dados: dict) -> str:
    return hashlib.sha256(json.dumps({k: dados.get(k) for k in CAMPOS_BILHETE}, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()


def entrega_da_ponte(dados: dict) -> bool:
    """The delivery really came from the bridge: it carries a one-time ticket that only the bridge (on the host, outside
    this container) keeps, and the bridge spends it now. The agent can read the shared key, so without this it could
    fake a phone message or a button press — an "aprovar" for its own action (12/10 review). Test logins (teste_*)
    reach no one and own nothing, so their tools may still post without a ticket (one that comes is checked)."""
    if not dados.get("bilhete"):
        return str(dados.get("usuario") or "").startswith("teste_")
    req = urllib.request.Request(URL.rsplit("/", 1)[0] + "/conferir",
                                 data=json.dumps({"bilhete": dados["bilhete"], "resumo": resumo_entrega(dados)}).encode(),
                                 headers={"Content-Type": "application/json", "X-Chave": chave()})
    try:
        with _abrir(req, timeout=10) as r:
            return bool(json.loads(r.read() or b"{}").get("ok"))
    except Exception as exc:
        print(f"whatsapp: bridge ticket check failed: {exc}", flush=True)
        return False


URGENTE = re.compile(r"^\W*(precisa de voc[eê]|urgente|decis[aã]o|aten[cç][aã]o|bloquead|falh|erro|⚠️|❗|🚨)", re.I)


def enviar(usuario: str, texto: str = "", arquivo: str = "", legenda: str = "", botoes: list | None = None,
           tipo: str = "", sempre: bool = False) -> str:
    """'' when sent, else the reason it was not. botoes: up to 3 [{"id", "titulo"}] reply buttons.
    tipo: "resposta" (default: answer to the person), "urgente" (needs them now: goes even in quiet hours) or
    "progresso" (held during their quiet hours and delivered together afterwards).
    sempre: send even when identical to a recent notice (a new request that happens to read the same, e.g. a code)."""
    if not usuario:
        return "conversa sem dono"
    if usuario.startswith("teste_"):  # test logins: what would reach the phone is recorded, nothing is sent
        CAIXA_TESTES.parent.mkdir(parents=True, exist_ok=True)
        with CAIXA_TESTES.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"em": time.time(), "usuario": usuario, "texto": texto, "arquivo": arquivo,
                                "legenda": legenda, "botoes": botoes or [], "tipo": tipo}, ensure_ascii=False) + "\n")
        return ""
    corpo = {"usuario": usuario, "texto": formatar(texto) if texto else "", "arquivo": arquivo, "legenda": legenda,
             "botoes": botoes or [], "tipo": tipo or ("urgente" if botoes else "resposta")}
    marca = _chave_aviso(texto, arquivo, botoes)
    janela = REPETIDO_H.get(corpo["tipo"])
    if janela and texto and not sempre and _ja_avisado(usuario, marca, janela):
        _segurar(usuario, texto, corpo["tipo"], f"igual a um aviso das últimas {janela} h")
        return ""  # it reached the phone already: for the caller this one is delivered
    req = urllib.request.Request(URL, data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json", "X-Chave": chave()})
    try:
        with _abrir(req, timeout=180) as r:
            r.read()
        if corpo["tipo"] != "resposta" and texto:
            _lembrar_aviso(usuario, texto, marca)
        return ""
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()).get("erro") or str(e)
        except Exception:
            return str(e)
    except Exception as exc:
        return str(exc)


AVISOS = Path("/a0/usr/whatsapp/avisos")  # notices sent by rounds/tasks, one .jsonl per person (last 60)
# 12/10 review (first piece of the notices gate, §4.3): the same notice could reach the phone 3-4 times (duplicate
# rounds, a round re-reporting what it already reported). An identical notice (same text, file and buttons) inside
# the window is held, not sent, and logged in <login>.segurados.jsonl. Answers to the person are never held.
REPETIDO_H = {"urgente": 6, "progresso": 12}


def _chave_aviso(texto: str, arquivo: str = "", botoes: list | None = None) -> str:
    base = "|".join([re.sub(r"\s+", " ", (texto or "").strip().lower()), arquivo or "",
                     ",".join(str((b or {}).get("id", "")) for b in botoes or [])])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _ler_jsonl(arq: Path) -> list[dict]:
    try:
        linhas = arq.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    itens = []
    for linha in linhas:
        try:
            itens.append(json.loads(linha))
        except ValueError:
            continue
    return itens


def _gravar_jsonl(arq: Path, itens: list[dict]) -> None:
    AVISOS.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=AVISOS, prefix=f".{arq.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in itens))
        os.chmod(tmp, 0o644)
        os.replace(tmp, arq)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _ja_avisado(usuario: str, marca: str, horas: float) -> bool:
    limite = time.time() - horas * 3600
    return any(i.get("chave") == marca and i.get("em", 0) >= limite for i in _ler_jsonl(AVISOS / f"{usuario}.jsonl"))


def _lembrar_aviso(usuario: str, texto: str, marca: str = "") -> None:
    """Keep what a round sent to the phone: when he answers it in the phone chat, that chat knows what he means
    (and the same notice is not sent twice)."""
    try:
        arq = AVISOS / f"{usuario}.jsonl"
        itens = _ler_jsonl(arq)[-59:] + [{"em": time.time(), "texto": texto[:1500], "chave": marca}]
        _gravar_jsonl(arq, itens)
    except OSError:
        pass


def _segurar(usuario: str, texto: str, tipo: str, motivo: str) -> None:
    try:
        arq = AVISOS / f"{usuario}.segurados.jsonl"
        _gravar_jsonl(arq, _ler_jsonl(arq)[-199:] + [{"em": time.time(), "tipo": tipo, "motivo": motivo,
                                                       "texto": texto[:500]}])
    except OSError:
        pass


def avisos_recentes(usuario: str, horas: float = 24, maximo: int = 6) -> list[dict]:
    limite = time.time() - horas * 3600
    return [i for i in _ler_jsonl(AVISOS / f"{usuario}.jsonl") if i.get("em", 0) >= limite][-maximo:]


def formatar(texto: str) -> str:
    """Agent markdown -> WhatsApp formatting (*bold*, _italic_, ~strike~, ```mono```)."""
    t = texto.replace("\r\n", "\n")
    t = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", t, flags=re.M)          # headings
    t = re.sub(r"\*\*(.+?)\*\*", r"*\1*", t)                         # bold
    t = re.sub(r"(?<![\w*])__(.+?)__(?![\w*])", r"*\1*", t)
    t = re.sub(r"~~(.+?)~~", r"~\1~", t)
    t = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", r"\1", t)                 # images -> path
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", t)  # links
    t = re.sub(r"^\s*[-*]\s+", "• ", t, flags=re.M)                  # bullets
    linhas = []
    for linha in t.split("\n"):                                      # tables -> "a · b · c"
        if re.match(r"^\s*\|?\s*:?-{3,}", linha):
            continue
        if linha.strip().startswith("|") and linha.strip().endswith("|"):
            celulas = [c.strip() for c in linha.strip().strip("|").split("|")]
            linha = " · ".join(c for c in celulas if c)
        linhas.append(linha)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()


def dono(context) -> str:
    """Owner login of a chat, the same rule the per-user separation uses (login_usuarios)."""
    import sys

    sep = sys.modules.get("login_usuarios_separacao")
    try:
        if sep is not None:
            return sep.dono_contexto(context)
        return (context.get_data("dono") or "").lower()
    except Exception:
        return ""


TAREFAS = "/a0/usr/scheduler/tasks.json"
_tarefas = {"mtime": 0.0, "ids": {}}
SILENCIO = "SEM NOVIDADE"  # a scheduled round that answers starting with this is not sent to the phone


def tarefa(context) -> str:
    """Name of the scheduled task this chat runs, or "". The scheduler makes ordinary (USER) chats
    for its tasks, so the context type alone never said it; its task list does."""
    import json
    import os

    try:
        from agent import AgentContextType

        if context.type == AgentContextType.TASK:
            return context.name or "tarefa"
    except Exception:
        pass
    try:
        mtime = os.path.getmtime(TAREFAS)
        if mtime != _tarefas["mtime"]:
            with open(TAREFAS, encoding="utf-8") as f:
                lista = json.load(f).get("tasks", [])
            _tarefas["ids"] = {t.get("context_id") or t.get("uuid"): t.get("name") or "tarefa" for t in lista}
            _tarefas["mtime"] = mtime
    except Exception:
        return ""
    return _tarefas["ids"].get(context.id, "")


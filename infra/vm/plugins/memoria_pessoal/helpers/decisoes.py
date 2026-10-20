"""The person's decisions in one place (12/10 review, §4.2): what was decided stays decided until they change it.

12/10: decisions lived in 9 places (each chat's contexto.md and vector memory, the profile, the approvals, the
prospecting config, the skill, the docs...) and none was read in a structured way, so settled questions came back
(the orchestrator text decided on 11/10 returned through the loose ends, the summary and the weekly review).

- One active decision per `tema` (a canonical subject name, e.g. "aprovacoes.instagram"). A new decision on the same
  tema replaces the old one, which is kept as "substituida" (with who and when), so the history shows how it changed.
- /a0/usr/memoria/decisoes/<login>.json, one writer at a time (flock), written atomically (temp file + fsync +
  rename). An unreadable file is an error, never "no decisions" (the next write would wipe them).
- Every turn of the person's agent sees the active ones (extension _17_memoria_pessoal) and follows them instead of
  asking again; the agent records new ones with the `decisao` tool, quoting the person's words.
- 20/10 (ADR 0001): for the owner, once the Segundo Cérebro's Pasta is migrated, the decisions live there, one file
  each in Decisoes/ (plugins/cerebro/helpers/pasta.py); this module stays the only writer and keeps its lock.
"""

import fcntl
import importlib.util
import json
import sys
import os
import re
import tempfile
import threading
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

PASTA = Path("/a0/usr/memoria/decisoes")
TIPOS = {"decisao": "decisão", "permissao": "pode sem perguntar", "proibicao": "não pode", "preferencia": "preferência"}
ORDEM_TIPOS = ("proibicao", "permissao", "decisao", "preferencia")
MAX_PROMPT = 6000  # characters of the block that goes into every turn (~1.5k tokens; cached with the prompt)
ESPERA_TRAVA = 30  # seconds; writes take milliseconds
_DONO = threading.local()


class EstadoIlegivel(RuntimeError):
    pass


def pasta():
    """plugins/cerebro/helpers/pasta.py (the Segundo Cérebro's Pasta), reloaded when it changes; None if absent."""
    nome = "cerebro_pasta"
    caminho = Path(__file__).resolve().parents[2] / "cerebro" / "helpers" / "pasta.py"
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


def na_pasta(login: str) -> bool:
    p = pasta()
    return bool(p and p.ativa(login))


class DecisaoInvalida(ValueError):
    pass


def _login(login: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "", (login or "").lower()) or "matheus"


def arquivo(login: str) -> Path:
    return PASTA / f"{_login(login)}.json"


def tema_canonico(tema: str) -> str:
    """'Aprovações do Instagram' → 'aprovacoes-do-instagram'; dots separate levels ('prospeccao.fontes')."""
    t = unicodedata.normalize("NFKD", str(tema or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9.]+", "-", t)
    t = re.sub(r"-{2,}", "-", re.sub(r"\.{2,}", ".", t)).strip("-.")
    return t[:60]


def _texto(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


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
                    raise RuntimeError("o registro de decisões está ocupado há mais de 30 s; tente de novo") from None
                time.sleep(0.05)
        travas[chave] = 1
        try:
            yield
        finally:
            travas[chave] = 0
            fcntl.flock(fh, fcntl.LOCK_UN)


def carregar(login: str) -> dict:
    if na_pasta(login):
        p = pasta()
        try:
            itens = p.ler("decisoes")
        except p.Ilegivel as exc:
            raise EstadoIlegivel(f"uma decisão da Pasta não pôde ser lida ({str(exc)[:80]}); nada foi gravado.") from None
        for x in itens:
            x["id"] = int(x["id"])
        return {"decisoes": sorted(itens, key=lambda x: x["id"])}
    arq = arquivo(login)
    d = {}
    if arq.exists():
        for tentativa in range(3):
            try:
                d = json.loads(arq.read_text(encoding="utf-8"))
                if not isinstance(d, dict):
                    raise ValueError("não é um objeto JSON")
                break
            except (OSError, ValueError) as exc:
                if tentativa == 2:
                    raise EstadoIlegivel(f"o registro de decisões ({arq.name}) não pôde ser lido ({str(exc)[:80]}); "
                                         "nada foi gravado.") from None
                time.sleep(0.2)
    d.setdefault("decisoes", [])
    return d


def _salvar(login: str, d: dict) -> None:
    with _exclusivo(login):
        if na_pasta(login):
            pasta().gravar("decisoes", d["decisoes"])
            return
        PASTA.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=PASTA, prefix=f".{_login(login)}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, arquivo(login))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def _vigente(x: dict, agora: float) -> bool:
    return x.get("estado") == "ativa" and not (x.get("valido_ate") and x["valido_ate"] < agora)


def ativas(login: str, agora: float | None = None) -> list[dict]:
    agora = agora or time.time()
    return [x for x in carregar(login)["decisoes"] if _vigente(x, agora)]


def _achar(d: dict, ref, agora: float) -> dict | None:
    """By number ("7", "#7") or by tema; only active decisions."""
    ref = str(ref or "").strip().lstrip("#")
    vivas = [x for x in d["decisoes"] if _vigente(x, agora)]
    if ref.isdigit():
        return next((x for x in vivas if x["id"] == int(ref)), None)
    tema = tema_canonico(ref)
    return next((x for x in vivas if x["tema"] == tema), None)


def registrar(login: str, tema: str, decisao: str, tipo: str = "decisao", citacao: str = "", origem: str = "",
              por: str = "agente", valido_ate: float | None = None, agora: float | None = None, area: str = "",
              liga: list | None = None) -> dict:
    """Record a decision; one active per tema (a new one replaces the old). Returns the record plus "efeito":
    "nova" | "substituiu" (with "anterior") | "igual" (same text again: nothing changes)."""
    agora = agora or time.time()
    tema_c, valor, tipo = tema_canonico(tema), _texto(decisao).rstrip(" .;"), str(tipo or "decisao").strip().lower()
    if not tema_c:
        raise DecisaoInvalida("falta o `tema` (nome curto do assunto, ex.: aprovacoes.instagram)")
    if len(valor) < 8:
        raise DecisaoInvalida("falta a `decisao` (o que foi decidido, numa frase)")
    if tipo not in TIPOS:
        raise DecisaoInvalida(f"`tipo` deve ser um de: {', '.join(TIPOS)}")
    with _exclusivo(login):
        d = carregar(login)
        antiga = _achar(d, tema_c, agora)
        if antiga and antiga["valor"].lower() == valor.lower() and antiga["tipo"] == tipo:
            if citacao and not antiga.get("citacao"):
                antiga["citacao"] = _texto(citacao)[:400]
                _salvar(login, d)
            return {**antiga, "efeito": "igual"}
        nova = {"id": max((x["id"] for x in d["decisoes"]), default=0) + 1, "tema": tema_c, "tipo": tipo,
                "valor": valor[:600], "citacao": _texto(citacao)[:400], "origem": _texto(origem)[:200],
                "por": _texto(por)[:120] or "agente", "em": agora, "estado": "ativa"}
        if valido_ate:
            nova["valido_ate"] = float(valido_ate)
        if area:
            nova["area"] = _texto(area)[:40].lower()
        if liga:
            nova["liga"] = [str(r) for r in liga if r][:10]
        if antiga:
            antiga.update(estado="substituida", fim_em=agora, fim_por=nova["por"], substituida_por=nova["id"])
            nova["substitui"] = antiga["id"]
        d["decisoes"].append(nova)
        _salvar(login, d)
    return {**nova, "efeito": "substituiu" if antiga else "nova", **({"anterior": antiga} if antiga else {})}


def revogar(login: str, ref, motivo: str = "", por: str = "agente", agora: float | None = None) -> dict | None:
    """The decision stops counting (the person changed their mind and there is no new rule): by number or tema."""
    agora = agora or time.time()
    with _exclusivo(login):
        d = carregar(login)
        x = _achar(d, ref, agora)
        if not x:
            return None
        x.update(estado="revogada", fim_em=agora, fim_por=_texto(por)[:120] or "agente", motivo=_texto(motivo)[:200])
        _salvar(login, d)
        return dict(x)


def historico(login: str, tema: str) -> list[dict]:
    tema_c = tema_canonico(tema)
    return [x for x in carregar(login)["decisoes"] if x["tema"] == tema_c]


def buscar(login: str, texto: str = "", agora: float | None = None) -> list[dict]:
    """Active decisions whose tema, text or quote contain every word searched (accents ignored)."""
    palavras = tema_canonico(texto).replace(".", "-").split("-")
    achadas = []
    for x in ativas(login, agora):
        alvo = tema_canonico(" ".join([x["tema"], x["valor"], x.get("citacao", "")]))
        if all(p in alvo for p in palavras if p):
            achadas.append(x)
    return achadas


def _data(ts: float) -> str:
    return time.strftime("%d/%m", time.localtime(ts))


def linha(x: dict) -> str:
    return f"- #{x['id']} **{x['tema']}** ({TIPOS.get(x['tipo'], x['tipo'])}, {_data(x['em'])}): {x['valor']}"


def texto_para_prompt(login: str, limite: int = MAX_PROMPT, agora: float | None = None) -> str:
    """The active decisions as a compact list, prohibitions first; empty string when there are none."""
    try:
        vivas = ativas(login, agora)
    except EstadoIlegivel as exc:
        return f"(não consegui ler o registro de decisões: {exc}; pergunte só o que for mesmo dele)"
    vivas.sort(key=lambda x: (ORDEM_TIPOS.index(x["tipo"]) if x["tipo"] in ORDEM_TIPOS else 9, x["tema"]))
    linhas, total = [], 0
    for i, x in enumerate(vivas):
        ln = linha(x)
        if total + len(ln) > limite:
            linhas.append(f"- …(mais {len(vivas) - i}: use a ferramenta `decisao` com acao \"listar\")")
            break
        linhas.append(ln)
        total += len(ln) + 1
    return "\n".join(linhas)

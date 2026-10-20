"""Assuntos (20/10, glossary): themes Matheus keeps discussing with the agent, each with where it stopped ("onde
parou"). One file per assunto in the Pasta's Assuntos/; this module is the only writer (one at a time: file lock).
An assunto can end in a Decisão, give Pendências, or stop; nothing is deleted (desfazer moves it to Arquivo-morto)."""

import fcntl
import importlib.util
import re
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ESTADOS = ("andamento", "parado", "encerrado")
ESPERA_TRAVA = 30


def pasta():
    nome = "cerebro_pasta"
    caminho = Path(__file__).resolve().parent / "pasta.py"
    antigo = sys.modules.get(nome)
    if antigo is None or getattr(antigo, "_mtime", None) != caminho.stat().st_mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = caminho.stat().st_mtime
        if antigo is not None and hasattr(antigo, "RAIZ"):
            modulo.RAIZ = antigo.RAIZ
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _texto(s, n: int = 600) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


@contextmanager
def _exclusivo():
    p = pasta()
    (p.RAIZ / "Assuntos").mkdir(parents=True, exist_ok=True)
    with open(p.RAIZ / "Assuntos" / ".lock", "a") as fh:
        limite = time.time() + ESPERA_TRAVA
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() > limite:
                    raise RuntimeError("os assuntos estão ocupados há mais de 30 s; tente de novo") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def todos() -> list[dict]:
    return sorted(pasta().ler("assuntos"), key=lambda a: a.get("criado", 0))


def abertos(limite: int = 20) -> list[dict]:
    vivos = [a for a in todos() if a.get("estado") in ("andamento", "parado")]
    return sorted(vivos, key=lambda a: -a.get("atualizado", 0))[:limite]


def achar(lista: list[dict], ref: str) -> dict | None:
    """By id, or by a title that contains every word given (accents ignored)."""
    ref = str(ref or "").strip()
    por_id = next((a for a in lista if str(a.get("id")) == ref), None)
    if por_id or not ref:
        return por_id
    p = pasta()
    palavras = [w for w in p.slug(ref, 200).split("-") if len(w) > 2]
    candidatos = [a for a in lista if palavras and all(w in p.slug(a.get("titulo", ""), 300) for w in palavras)]
    return candidatos[0] if len(candidatos) == 1 else None


def registrar(titulo: str, onde_parou: str = "", area: str = "", estado: str = "andamento", citacao: str = "",
              origem: str = "", por: str = "agente", liga: list | None = None, agora: float | None = None) -> dict:
    """A new assunto, or the same one (same title, still open) updated. Returns it with "efeito": nova|atualizou."""
    agora = agora or time.time()
    titulo = _texto(titulo, 120)
    if len(titulo) < 4:
        raise ValueError("falta o `titulo` do assunto (curto, ex.: 'preço do plano da Raiz')")
    estado = estado if estado in ESTADOS else "andamento"
    with _exclusivo():
        lista = todos()
        mesmo = next((a for a in lista if a.get("estado") != "encerrado"
                      and pasta().slug(a.get("titulo", "")) == pasta().slug(titulo)), None)
        if mesmo:
            return {**atualizar(mesmo["id"], onde_parou=onde_parou, estado=estado, citacao=citacao, por=por, liga=liga,
                                agora=agora, _lista=lista), "efeito": "atualizou"}
        novo = {"id": uuid.uuid4().hex[:6], "titulo": titulo, "area": _texto(area, 40).lower() or "geral",
                "estado": estado, "onde_parou": _texto(onde_parou), "criado": agora, "atualizado": agora,
                "origem": _texto(origem, 200), "por": _texto(por, 120) or "agente",
                "historico": [{"em": agora, "nota": _texto(onde_parou) or "assunto aberto",
                               **({"citacao": _texto(citacao, 300)} if citacao else {})}]}
        if liga:
            novo["liga"] = [str(r) for r in liga if r][:10]
        pasta().gravar("assuntos", lista + [novo])
    return {**novo, "efeito": "nova"}


def atualizar(ref: str, onde_parou: str = "", estado: str = "", citacao: str = "", por: str = "agente",
              liga: list | None = None, agora: float | None = None, _lista: list | None = None) -> dict:
    """Where it stopped now (kept in the history), and/or its state. KeyError when not found."""
    agora = agora or time.time()

    def mudar(lista):
        a = achar(lista, ref)
        if not a:
            raise KeyError(f"assunto não encontrado: {ref}")
        if onde_parou and _texto(onde_parou) != a.get("onde_parou"):
            a["onde_parou"] = _texto(onde_parou)
            a.setdefault("historico", []).append({"em": agora, "nota": a["onde_parou"],
                                                  **({"citacao": _texto(citacao, 300)} if citacao else {})})
        if estado in ESTADOS and estado != a.get("estado"):
            a["estado"] = estado
            a.setdefault("historico", []).append({"em": agora, "nota": f"→ {estado}"})
        if liga:
            a["liga"] = list(dict.fromkeys((a.get("liga") or []) + [str(r) for r in liga if r]))[:20]
        a["atualizado"], a["por"] = agora, _texto(por, 120) or a.get("por")
        pasta().gravar("assuntos", lista)
        return dict(a)

    if _lista is not None:
        return mudar(_lista)
    with _exclusivo():
        return mudar(todos())


def desfazer(ref: str) -> dict | None:
    """It should not have been recorded: the file goes to Arquivo-morto/ (kept, out of every list)."""
    with _exclusivo():
        lista = todos()
        a = achar(lista, ref)
        if not a:
            return None
        pasta().gravar("assuntos", [x for x in lista if x is not a])
        return a


def linha(a: dict) -> str:
    return f"[{a['id']}] {a.get('titulo')} ({a.get('area', 'geral')}, {a.get('estado')}): onde parou — " \
           f"{a.get('onde_parou') or 'nada ainda'}"

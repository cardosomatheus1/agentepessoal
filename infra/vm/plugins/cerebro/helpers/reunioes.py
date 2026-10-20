"""Reuniões (20/10, Playbook Lab "Setup inicial do OS"): one note per meeting in the Pasta's Reunioes/, with the summary,
who was there, the Decisões it made and the next steps (Pendências), linked as [[wiki links]]. This module is the only
writer of Reunioes/ (one at a time: file lock). File: Reunioes/AAAA-MM-DD-<slug do título>.md; the same meeting
recorded again (the pós-reunião hook runs on every `fios` save, the agent may add what he tells later) is merged into
the note, never overwritten with less: participants, decisions and next steps are joined, a different summary is
appended. An unreadable note stops the write (it would be lost)."""

import fcntl
import importlib.util
import json
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ESPERA_TRAVA = 30
PASTA_NOME = "Reunioes"
RESUMO_MAX = 4000


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


def como_lista(valor, n: int = 300, virgula: bool = False) -> list[str]:
    """A list from a list, a JSON list or a line/";" (and, for names, comma) separated string; empty items dropped,
    order kept, no repeats."""
    if isinstance(valor, str):
        bruto = valor.strip()
        if bruto.startswith("["):
            try:
                valor = json.loads(bruto)
            except ValueError:
                valor = re.split(r"[,\n;]", bruto.strip("[]"))
        else:
            valor = re.split(r"\n|;|,(?![^()]*\))" if virgula else r"\n|;", bruto)
    if not isinstance(valor, (list, tuple)):
        valor = [valor] if valor else []
    itens = [_texto(v.get("ref") or v.get("id") or v.get("titulo") if isinstance(v, dict) else v, n) for v in valor]
    return list(dict.fromkeys(i.strip(" -•") for i in itens if i and i.strip(" -•")))


@contextmanager
def _exclusivo():
    p = pasta()
    (p.RAIZ / PASTA_NOME).mkdir(parents=True, exist_ok=True)
    with open(p.RAIZ / PASTA_NOME / ".lock", "a") as fh:
        limite = time.time() + ESPERA_TRAVA
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() > limite:
                    raise RuntimeError("as reuniões estão ocupadas há mais de 30 s; tente de novo") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _arquivos() -> list[tuple[Path, dict]]:
    d = pasta().RAIZ / PASTA_NOME
    p = pasta()
    return [(f, p.ler_frontmatter(f.read_text(encoding="utf-8"), f.name))
            for f in sorted(d.glob("*.md")) if f.name != "indice.md"] if d.exists() else []


def todas() -> list[dict]:
    return sorted((c for _f, c in _arquivos()), key=lambda r: (r.get("data", ""), r.get("criado", 0)), reverse=True)


def data_valida(data: str) -> str:
    data = str(data or "").strip()[:10]
    try:
        time.strptime(data, "%Y-%m-%d")
        return data
    except ValueError:
        if data:
            raise ValueError(f"`data` da reunião em AAAA-MM-DD (veio {data!r})") from None
        return pasta().data()


def _resumo(antigo: str, novo: str) -> str:
    """Never less: the new one when it contains the old, the old when it contains the new, else both."""
    antigo, novo = str(antigo or "").strip(), str(novo or "").strip()
    if not novo or novo in antigo:
        return antigo
    if not antigo or antigo in novo:
        return novo[:RESUMO_MAX]
    return f"{antigo}\n\n{novo}"[:RESUMO_MAX]


def registrar(titulo: str, data: str = "", participantes=None, resumo: str = "", decisoes_refs=None,
              pendencias_refs=None, origem: str = "", por: str = "agente", area: str = "", evento_id: str = "",
              agora: float | None = None) -> dict:
    """Write (or merge into) the meeting's note. decisoes_refs/pendencias_refs: 'decisao:35' / 'pendencia:ab12cd'
    (become links) or plain text. Returns the note's fields plus "arquivo" (relative) and "efeito": nova|atualizou|igual."""
    agora = agora or time.time()
    p = pasta()
    titulo = _texto(titulo, 120)
    if len(titulo) < 4:
        raise ValueError("falta o `titulo` da reunião (ex.: 'Alinhamento NEXOS com o João')")
    data = data_valida(data)
    ident = f"{data}-{p.slug(titulo)}"
    novo = {"participantes": como_lista(participantes, 120, virgula=True), "decisoes": como_lista(decisoes_refs),
            "pendencias": como_lista(pendencias_refs)}
    with _exclusivo():
        destino = p.RAIZ / PASTA_NOME / f"{ident}.md"
        atual = p.ler_frontmatter(destino.read_text(encoding="utf-8"), destino.name) if destino.exists() else None
        if atual is None:
            nota = {"id": ident, "titulo": titulo, "data": data, "area": _texto(area, 40).lower() or "geral",
                    **novo, "resumo": str(resumo or "").strip()[:RESUMO_MAX], "origem": _texto(origem, 200),
                    "por": _texto(por, 120) or "agente", "criado": agora, "atualizado": agora}
            if evento_id:
                nota["evento_id"] = _texto(evento_id, 200)
            efeito = "nova"
        else:
            nota = dict(atual)
            for k, v in novo.items():
                nota[k] = list(dict.fromkeys((atual.get(k) or []) + v))
            nota["resumo"] = _resumo(atual.get("resumo"), resumo)
            if area and (atual.get("area") or "geral") == "geral":
                nota["area"] = _texto(area, 40).lower()
            if evento_id and not atual.get("evento_id"):
                nota["evento_id"] = _texto(evento_id, 200)
            if origem and not atual.get("origem"):
                nota["origem"] = _texto(origem, 200)
            efeito = "igual" if nota == atual else "atualizou"
            if efeito == "atualizou":
                nota["atualizado"], nota["por"] = agora, _texto(por, 120) or atual.get("por")
        if efeito != "igual":
            campos = {**nota, "status": "registrada", "tags": ["reuniao", p.slug(nota.get("area") or "geral")]}
            p.escrever(destino, p.frontmatter(campos) + corpo(nota))
        p.escrever(p.RAIZ / PASTA_NOME / "indice.md", indice(todas()))
    return {**nota, "arquivo": f"{PASTA_NOME}/{destino.name}", "efeito": efeito}


# ---------------------------------------------------------------- rendering
def _quando(data: str) -> str:
    try:
        return time.strftime("%d/%m/%Y", time.strptime(str(data), "%Y-%m-%d"))
    except ValueError:
        return str(data or "")


def corpo(r: dict) -> str:
    p = pasta()
    partes = [f"# {r.get('titulo')}", "",
              f"- Data: {_quando(r.get('data'))} · Área: {r.get('area') or 'geral'}"
              + (f" · Participantes: {', '.join(r['participantes'])}" if r.get("participantes") else ""), "",
              "## Resumo", r.get("resumo") or "(sem resumo ainda)", "",
              "## Participantes"] + ([f"- {x}" for x in r.get("participantes") or []] or ["- (não informados)"])
    partes += ["", "## Decisões"] + ([f"- {p.link(x)}" for x in r.get("decisoes") or []] or ["- nenhuma registrada"])
    partes += ["", "## Próximos passos"] + ([f"- {p.link(x)}" for x in r.get("pendencias") or []] or ["- nenhum registrado"])
    if r.get("origem"):
        partes += ["", f"_Origem: {r['origem']}_"]
    return "\n".join(partes).rstrip() + "\n"


def indice(lista: list[dict]) -> str:
    linhas = ["# Reunioes", "", f"{len(lista)} reuniões. Cada uma é um arquivo desta pasta.", ""]
    linhas += [f"- [[{PASTA_NOME}/{r['id']}]] — {_quando(r.get('data'))} · {r.get('area') or 'geral'}"
               + (f" · {len(r.get('pendencias') or [])} próximo(s) passo(s)" if r.get("pendencias") else "")
               for r in lista]
    return "\n".join(linhas) + "\n"


def linha(r: dict) -> str:
    return (f"{r.get('arquivo') or PASTA_NOME + '/' + str(r.get('id'))}: {r.get('titulo')} ({_quando(r.get('data'))}) — "
            f"{len(r.get('decisoes') or [])} decisão(ões), {len(r.get('pendencias') or [])} próximo(s) passo(s)")

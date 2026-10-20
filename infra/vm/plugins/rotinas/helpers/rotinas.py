"""Routines (Agent Zero skills tagged "rotina" in /a0/usr/skills/<slug>/SKILL.md): list, read, save, correct, adjust.

Public helper: tools/salvar_rotina.py and the end-of-chat reviewer (memory front) both go through here, so the
rules are the same for the agent and for the reviewer:
- a correction equal to one already kept (normalised text) is refused;
- each correction carries the date and who wrote it ("por");
- "ajustar" (swap a passage) only works on the version the caller read: it passes the hash `ler` returned;
- from LIMITE accumulated corrections on, the answer asks for the steps to be rewritten clean (`salvar` with
  consolidar=True and the hash read: the corrections section leaves, the previous file is kept in .versoes/).
Every change is also logged in <slug>/.versoes/diario.jsonl.
Scheduled routines (scheduler tasks) keep their corrections in AGENDADAS/<uuid>/correcoes.md, same rules
(corrigir_agendada: the "Aplicar" of helpers/autoavaliacao.py)."""

import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

SKILLS = Path("/a0/usr/skills")
AGENDADAS = Path("/a0/usr/rotinas/agendadas")  # corrections of scheduled routines (scheduler tasks)
SECAO = "## Correções do usuário"
LIMITE = 8  # from this many accumulated corrections on, the steps should be rewritten clean
_LINHA = re.compile(r"^- (\d{2}/\d{2}/\d{4}(?: \(por [^)]*\))?: )?")


def slug(nome: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(nome or "").lower().translate(str.maketrans("áàâãéêíóôõúçü", "aaaaeeiooouuc"))).strip("-")
    return s[:50] or "rotina"


def arquivo(nome: str) -> Path:
    return SKILLS / slug(nome) / "SKILL.md"


def hash_de(texto: str) -> str:
    """Version of a routine's text: ajustar/consolidar only take the one the caller last read."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]


def normal(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def correcoes(texto: str) -> list[str]:
    """The corrections kept in a routine's text, without date and author."""
    if SECAO not in texto:
        return []
    secao = texto[texto.index(SECAO):].split("\n")[1:]
    fim = next((i for i, l in enumerate(secao) if l.startswith("## ")), len(secao))
    return [_LINHA.sub("", l).strip() for l in secao[:fim] if l.startswith("- ")]


def pede_reescrita(n: int) -> bool:
    return n >= LIMITE


def _frente(texto: str) -> dict:
    """name, description and trigger_patterns of the SKILL.md front matter (the format salvar writes)."""
    if not texto.startswith("---"):
        return {}
    bloco = texto[3:].split("\n---", 1)[0]
    try:
        import yaml

        lido = yaml.safe_load(bloco)
        if isinstance(lido, dict):
            tags = lido.get("tags")
            return {**{k: v for k, v in lido.items() if k != "tags"},
                    "tags": json.dumps(tags if isinstance(tags, list) else [tags], ensure_ascii=False)}
    except Exception:
        pass  # no yaml here, or a front matter it cannot read: the simple reading below
    dados, lista = {"trigger_patterns": []}, None
    for linha in bloco.splitlines():
        if lista and re.match(r"\s+- ", linha):
            dados[lista].append(linha.split("- ", 1)[1].strip().strip('"'))
            continue
        lista = None
        m = re.match(r"(\w+):\s*(.*)", linha)
        if m:
            chave, valor = m.groups()
            if chave == "trigger_patterns" and not valor:
                lista = chave
            else:
                dados[chave] = valor.strip().strip('"')
    return dados


@contextmanager
def _trava():
    SKILLS.mkdir(parents=True, exist_ok=True)
    with open(SKILLS / ".rotinas.lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _gravar(arq: Path, texto: str) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=arq.parent, prefix=f".{arq.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(texto)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, arq)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _diario(arq: Path, **registro) -> None:
    try:
        d = arq.parent / ".versoes" / "diario.jsonl"
        d.parent.mkdir(parents=True, exist_ok=True)
        with open(d, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"quando": time.strftime("%Y-%m-%dT%H:%M:%S"), **registro}, ensure_ascii=False) + "\n")
    except OSError:
        pass  # the log never blocks a change


def _texto(arq: Path) -> str:
    return arq.read_text(encoding="utf-8") if arq.exists() else ""


# ---------- public ----------

def listar() -> list[dict]:
    """[{nome, descricao, gatilhos, n_correcoes}] of the routines (skills tagged "rotina")."""
    saida = []
    for arq in sorted(SKILLS.glob("*/SKILL.md")):
        try:
            texto = arq.read_text(encoding="utf-8")
        except OSError:
            continue
        f = _frente(texto)
        if '"rotina"' not in f.get("tags", ""):
            continue
        saida.append({"nome": f.get("name") or arq.parent.name, "descricao": f.get("description", ""),
                      "gatilhos": f.get("trigger_patterns") or [], "n_correcoes": len(correcoes(texto))})
    return saida


def ler(nome: str) -> dict | None:
    """{texto, hash} of the routine as it is now, or None when it does not exist."""
    texto = _texto(arquivo(nome))
    return {"texto": texto, "hash": hash_de(texto)} if texto else None


def corrigir(nome: str, correcao: str, por: str = "agente") -> dict:
    """Add a correction. {ok, motivo, n_correcoes, pede_reescrita}; motivo: gravada|repetida|nao_existe|vazia."""
    return _corrigir(arquivo(nome), correcao, por)


def arquivo_agendada(uuid: str) -> Path:
    """Corrections of a scheduled routine (a scheduler task, not a skill): its prompt stays as the scheduler keeps it
    and the round gets these appended at start (monologue/start/_30_correcoes_agendada.py)."""
    return AGENDADAS / (re.sub(r"[^A-Za-z0-9_-]", "", str(uuid or "")) or "sem-id") / "correcoes.md"


def corrigir_agendada(uuid: str, nome: str, correcao: str, por: str = "agente") -> dict:
    """Same rules as corrigir (dated, author, no repeats, diário), for a scheduled routine; its file is born here."""
    cabeca = f"# Correções da rotina agendada {' '.join(str(nome or uuid).split())} ({uuid})\n"
    return _corrigir(arquivo_agendada(uuid), correcao, por, criar=cabeca)


def correcoes_agendada(uuid: str) -> list[str]:
    return correcoes(_texto(arquivo_agendada(uuid)))


def _corrigir(arq: Path, correcao: str, por: str, criar: str = "") -> dict:
    correcao = " ".join(str(correcao or "").split())
    with _trava():
        atual = _texto(arq) or criar
        if not atual:
            return {"ok": False, "motivo": "nao_existe", "n_correcoes": 0, "pede_reescrita": False}
        existentes = correcoes(atual)
        n = len(existentes)
        if not correcao:
            return {"ok": False, "motivo": "vazia", "n_correcoes": n, "pede_reescrita": pede_reescrita(n)}
        if normal(correcao) in {normal(c) for c in existentes}:
            return {"ok": False, "motivo": "repetida", "n_correcoes": n, "pede_reescrita": pede_reescrita(n)}
        texto = atual.rstrip()
        if SECAO not in texto:
            texto += f"\n\n{SECAO} (valem acima dos passos)"
        autor = " ".join(str(por or "agente").replace(")", "").split())
        texto += f"\n- {time.strftime('%d/%m/%Y')} (por {autor}): {correcao}\n"
        _gravar(arq, texto)
    _diario(arq, acao="corrigir", por=autor, correcao=correcao)
    return {"ok": True, "motivo": "gravada", "n_correcoes": n + 1, "pede_reescrita": pede_reescrita(n + 1)}


def ajustar(nome: str, trecho: str, novo: str, hash_lido: str, por: str = "agente") -> dict:
    """Swap one passage for another in the version the caller read.
    {ok, motivo, hash, n_correcoes, pede_reescrita}; motivo: ajustada|nao_existe|nao_relida|vazio|nao_achou|repetido."""
    arq = arquivo(nome)
    with _trava():
        atual = _texto(arq)
        r = {"ok": False, "hash": hash_de(atual) if atual else "", "n_correcoes": len(correcoes(atual))}
        r["pede_reescrita"] = pede_reescrita(r["n_correcoes"])
        if not atual:
            return {**r, "motivo": "nao_existe"}
        if not hash_lido or str(hash_lido).strip() != r["hash"]:
            return {**r, "motivo": "nao_relida"}
        if not str(trecho or "").strip():
            return {**r, "motivo": "vazio"}
        vezes = atual.count(trecho)
        if vezes != 1:
            return {**r, "motivo": "nao_achou" if not vezes else "repetido", "vezes": vezes}
        texto = atual.replace(trecho, str(novo or ""), 1)
        _gravar(arq, texto)
    _diario(arq, acao="ajustar", por=str(por or "agente"), trecho=trecho, novo=novo)
    n = len(correcoes(texto))
    return {"ok": True, "motivo": "ajustada", "hash": hash_de(texto), "n_correcoes": n, "pede_reescrita": pede_reescrita(n)}


def _lista(texto) -> str:
    if isinstance(texto, list):
        return "\n".join(f"{i}. {p}" for i, p in enumerate(texto, 1))
    return str(texto or "").strip()


def salvar(nome: str, descricao: str, passos, quando_usar: str = "", entradas: str = "", verificar: str = "",
           entregar: str = "", aprovacao: str = "", gatilhos=None, dono: str = "", consolidar: bool = False,
           hash_lido: str = "", por: str = "agente") -> dict:
    """Write the routine. The corrections already kept stay, unless consolidar=True with the hash read (they are now
    inside the steps): then the section leaves and the previous file is kept in .versoes/.
    {ok, motivo, arquivo, hash, n_correcoes, pede_reescrita}; motivo: salva|consolidada|incompleta|nao_relida."""
    arq = arquivo(nome)
    if not (nome and descricao and passos):
        return {"ok": False, "motivo": "incompleta", "arquivo": str(arq)}
    gat = [g for g in (gatilhos or []) if str(g).strip()] if isinstance(gatilhos, list) else \
          [g.strip() for g in str(gatilhos or "").split(",") if g.strip()]
    dono = str(dono or "").lower()
    s = slug(nome)
    frente = ["---", f"name: {s}", f'description: "{descricao.strip().replace(chr(34), chr(39))}"',
              "version: 1.0.0", f'tags: ["rotina"{", " + chr(34) + dono + chr(34) if dono else ""}]']
    if gat:
        frente.append("trigger_patterns:")
        frente += [f'  - "{g}"' for g in gat[:12]]
    frente.append("---")
    corpo = [f"# {nome.strip()}", "",
             f"Rotina salva em {time.strftime('%d/%m/%Y')}" + (f" por {dono}" if dono else "") + ".", "",
             "## Quando usar", quando_usar.strip() or descricao.strip(), "",
             "## Entradas e acessos", entradas.strip() or "(nenhuma)", "",
             "## Passos", _lista(passos), "",
             "## Como verificar que deu certo", verificar.strip() or "(confira o resultado antes de entregar)", "",
             "## O que entregar", entregar.strip() or "(resumo curto do que foi feito)", "",
             "## Precisa de aprovação do usuário", aprovacao.strip() or "(siga as regras de aprovações)"]
    with _trava():
        atual = _texto(arq)
        if consolidar:
            if not atual or not hash_lido or str(hash_lido).strip() != hash_de(atual):
                return {"ok": False, "motivo": "nao_relida", "arquivo": str(arq)}
            guardada = arq.parent / ".versoes" / f"SKILL-{time.strftime('%Y%m%d-%H%M%S')}.md"
            _gravar(guardada, atual)
        elif SECAO in atual:  # keep what the user taught on re-save
            corpo += ["", atual[atual.index(SECAO):].strip()]
        texto = "\n".join(frente + corpo) + "\n"
        _gravar(arq, texto)
    _diario(arq, acao="consolidar" if consolidar else "salvar", por=str(por or "agente"))
    n = len(correcoes(texto))
    return {"ok": True, "motivo": "consolidada" if consolidar else "salva", "arquivo": str(arq), "hash": hash_de(texto),
            "n_correcoes": n, "pede_reescrita": pede_reescrita(n)}

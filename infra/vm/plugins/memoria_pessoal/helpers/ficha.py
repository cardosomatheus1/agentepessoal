"""The person's profile ("Sobre você", /a0/usr/memoria/usuarios/<login>.md) as a bounded list of entries.

Before (14/10): free text the agent rewrote with the file editor, cut at 12,000 characters in the prompt, so the newest
lines were the ones lost; anything could go in, including text read from a lead's DM or an e-mail. Now (from Hermes,
tools/memory_tool_store.py, MIT):
- one entry per "- " line, written only by the `ficha` tool (add / patch / remove) through this helper;
- a ceiling (TETO, ~4,000 characters): a full ficha refuses the new entry and returns the current ones, so the agent
  consolidates (patch/remove) instead of the oldest facts silently falling off;
- no duplicates; every entry passes helpers/protecao.py (facts, never orders, secrets or third-party text);
- the same lock and atomic write as the decisions (flock per person, temp file + fsync + rename); an unreadable file
  is an error, never "empty"; every change is appended to <login>.diario.jsonl (who, when, before, after).
The old free-text file is converted once by `migrar` (the operator runs it; the original is kept as a backup).
20/10 (ADR 0001): for the owner, once the Segundo Cérebro's Pasta is migrated, the ficha is Contexto/perfil.md there
(plugins/cerebro/helpers/pasta.py); this module stays its only writer, with the same rules.
"""

import fcntl
import importlib.util
import json
import os
import re
import sys
import tempfile
import threading
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

PASTA = Path("/a0/usr/memoria/usuarios")
TETO = 4000  # characters of entries (~1k tokens in every turn)
MAX_ENTRADA = 600
ESPERA_TRAVA = 30
MARCA = "Mantida pela ferramenta `ficha`"
_DONO = threading.local()


class EstadoIlegivel(RuntimeError):
    pass


class FormatoAntigo(RuntimeError):
    pass


def _protecao():
    """helpers/protecao.py next to this file, reloaded when it changes."""
    nome = "memoria_pessoal_protecao"
    caminho = Path(__file__).resolve().parent / "protecao.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _login(login: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "", (login or "").lower()) or "matheus"


def pasta():
    """plugins/cerebro/helpers/pasta.py (the Segundo Cérebro's Pasta), reloaded when it changes; None if absent."""
    nome = "cerebro_pasta"
    caminho = Path(__file__).resolve().parents[2] / "cerebro" / "helpers" / "pasta.py"
    if nome not in sys.modules and not caminho.exists():
        return None
    antigo = sys.modules.get(nome)
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


def arquivo(login: str) -> Path:
    if na_pasta(login):
        return pasta().RAIZ / "Contexto" / "perfil.md"
    return PASTA / f"{_login(login)}.md"


def _texto(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _chave(s: str) -> str:
    """Comparison form: no accents, case, punctuation or spacing differences."""
    t = unicodedata.normalize("NFKD", _texto(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9@]+", " ", t).strip()


@contextmanager
def _exclusivo(login: str):
    """One writer at a time per person, across threads and processes; re-entrant in the same thread (as decisoes)."""
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
                    raise RuntimeError("a ficha está ocupada há mais de 30 s; tente de novo") from None
                time.sleep(0.05)
        travas[chave] = 1
        try:
            yield
        finally:
            travas[chave] = 0
            fcntl.flock(fh, fcntl.LOCK_UN)


def _ler_bruto(login: str) -> str | None:
    arq = arquivo(login)
    if not arq.exists():
        return None
    for tentativa in range(3):
        try:
            return arq.read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            if tentativa == 2:
                raise EstadoIlegivel(f"a ficha ({arq.name}) não pôde ser lida ({str(exc)[:80]}); nada foi gravado.") from None
            time.sleep(0.2)
    return None


def migrada(bruto: str | None) -> bool:
    return bruto is None or MARCA in bruto[:400]


def _entradas_de(bruto: str) -> list[str]:
    return [_texto(ln[2:]) for ln in bruto.splitlines() if ln.startswith("- ") and _texto(ln[2:])]


def entradas(login: str) -> list[str]:
    """The current entries. FormatoAntigo while the old free-text file was not migrated yet."""
    bruto = _ler_bruto(login)
    if not migrada(bruto):
        raise FormatoAntigo("a ficha ainda está no formato antigo (texto livre); o operador precisa migrá-la")
    return _entradas_de(bruto or "")


def uso(lista: list[str]) -> int:
    return sum(len(e) + 3 for e in lista)  # "- " + newline


def _render(login: str, lista: list[str]) -> str:
    if na_pasta(login):
        cab = pasta().frontmatter({"status": "validado", "tags": ["contexto", "perfil"]})
        return cab + _render_simples(login, lista)
    return _render_simples(login, lista)


def _render_simples(login: str, lista: list[str]) -> str:
    return (f"# Sobre {_login(login)}\n\n> {MARCA} (add, patch, remove), uma entrada por linha, até {TETO} caracteres. "
            "Não edite à mão.\n\n" + "".join(f"- {e}\n" for e in lista))


def _diario(login: str, registro: dict) -> None:
    with open(PASTA / f"{_login(login)}.diario.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"em": time.time(), **registro}, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _salvar(login: str, lista: list[str], registro: dict) -> None:
    with _exclusivo(login):
        PASTA.mkdir(parents=True, exist_ok=True)
        destino = arquivo(login)
        destino.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=f".{_login(login)}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(_render(login, lista))
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, destino)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        _diario(login, registro)


def numeradas(lista: list[str]) -> str:
    return "\n".join(f"{i}. {e}" for i, e in enumerate(lista, 1))


def _cheia(lista: list[str], extra: int, o_que: str) -> dict:
    return {"ok": False, "motivo": "cheia",
            "mensagem": (f"A ficha está com {uso(lista)}/{TETO} caracteres; {o_que} passaria do teto em "
                         f"{uso(lista) + extra - TETO}. Consolide antes: junte entradas parecidas (acao \"patch\") ou "
                         "tire as velhas/menos importantes (acao \"remove\"), e tente de novo. Entradas atuais:\n"
                         + numeradas(lista))}


def _recusa(texto: str) -> str:
    motivo = _protecao().ameaca(texto, ficha=True)
    if motivo:
        return (f"Não gravei: o texto {motivo}. A ficha guarda fatos sobre a pessoa, nas palavras de quem conta; "
                "permissões e proibições vão na ferramenta `decisao`, e o que veio de terceiros não entra.")
    return ""


def _localizar(lista: list[str], ref: str) -> tuple[int | None, str]:
    """By number ("3", "#3") or by a piece of text that appears in exactly one entry."""
    ref = str(ref or "").strip()
    if re.fullmatch(r"#?\d+", ref):
        i = int(ref.lstrip("#")) - 1
        return (i, "") if 0 <= i < len(lista) else (None, f"não há entrada {ref} (a ficha tem {len(lista)})")
    if len(_chave(ref)) < 3:
        return None, "diga qual entrada (o número ou um trecho dela, em `trecho`)"
    achadas = [i for i, e in enumerate(lista) if ref in e] or [i for i, e in enumerate(lista) if _chave(ref) in _chave(e)]
    if not achadas:
        return None, f"nenhuma entrada tem {ref!r}"
    if len(achadas) > 1:
        return None, "o trecho aparece em mais de uma entrada; use o número:\n" + "\n".join(
            f"{i + 1}. {lista[i]}" for i in achadas)
    return achadas[0], ""


def adicionar(login: str, texto: str, por: str = "agente", origem: str = "") -> dict:
    texto = _texto(texto)
    if len(texto) < 4:
        return {"ok": False, "motivo": "vazio", "mensagem": "Não gravei: falta o `texto` (o fato, numa frase)."}
    if len(texto) > MAX_ENTRADA:
        return {"ok": False, "motivo": "longa", "mensagem": f"Não gravei: a entrada passa de {MAX_ENTRADA} caracteres; resuma."}
    if recusa := _recusa(texto):
        return {"ok": False, "motivo": "protecao", "mensagem": recusa}
    with _exclusivo(login):
        lista = entradas(login)
        chave = _chave(texto)
        igual = next((e for e in lista if _chave(e) == chave or chave in _chave(e)), None)
        if igual:
            return {"ok": False, "motivo": "duplicada", "mensagem": f"Já está na ficha: «{igual}». Nada mudou."}
        if uso(lista) + len(texto) + 3 > TETO:
            return _cheia(lista, len(texto) + 3, "esta entrada")
        nova = lista + [texto]
        _salvar(login, nova, {"acao": "add", "depois": texto, "por": _texto(por)[:120], "origem": _texto(origem)[:200]})
    return {"ok": True, "mensagem": f"Anotado na ficha ({uso(nova)}/{TETO} caracteres): {texto}"}


def trocar(login: str, trecho: str, novo: str, por: str = "agente", origem: str = "") -> dict:
    """patch: inside the one entry that has `trecho`, `trecho` becomes `novo` (a number replaces the whole entry)."""
    novo = _texto(novo)
    if len(novo) < 2:
        return {"ok": False, "motivo": "vazio", "mensagem": "Não troquei: falta o `novo` (para apagar use acao \"remove\")."}
    with _exclusivo(login):
        lista = entradas(login)
        i, erro = _localizar(lista, trecho)
        if i is None:
            return {"ok": False, "motivo": "nao_achou", "mensagem": f"Não troquei: {erro}."}
        antes = lista[i]
        ref = str(trecho or "").strip()
        if re.fullmatch(r"#?\d+", ref) or ref not in antes:
            depois = novo
        else:
            if antes.count(ref) > 1:
                return {"ok": False, "motivo": "ambigua", "mensagem": "Não troquei: o trecho aparece 2 vezes na entrada; "
                        "mande o trecho maior ou o número dela com o texto inteiro em `novo`."}
            depois = _texto(antes.replace(ref, novo))
        if len(depois) > MAX_ENTRADA:
            return {"ok": False, "motivo": "longa", "mensagem": f"Não troquei: a entrada passaria de {MAX_ENTRADA} caracteres."}
        if recusa := _recusa(depois):
            return {"ok": False, "motivo": "protecao", "mensagem": recusa.replace("Não gravei", "Não troquei")}
        outra = next((e for j, e in enumerate(lista) if j != i and _chave(e) == _chave(depois)), None)
        if outra:
            return {"ok": False, "motivo": "duplicada", "mensagem": f"Não troquei: ficaria igual a «{outra}»; "
                    "remova uma das duas."}
        nova = lista[:i] + [depois] + lista[i + 1:]
        if uso(nova) > TETO and uso(nova) > uso(lista):
            return _cheia(lista, uso(nova) - uso(lista), "a troca")
        _salvar(login, nova, {"acao": "patch", "antes": antes, "depois": depois, "por": _texto(por)[:120],
                              "origem": _texto(origem)[:200]})
    return {"ok": True, "mensagem": f"Ficha atualizada ({uso(nova)}/{TETO}): «{antes}» → «{depois}»"}


def remover(login: str, trecho: str, por: str = "agente", origem: str = "") -> dict:
    with _exclusivo(login):
        lista = entradas(login)
        i, erro = _localizar(lista, trecho)
        if i is None:
            return {"ok": False, "motivo": "nao_achou", "mensagem": f"Não removi: {erro}."}
        saiu = lista[i]
        nova = lista[:i] + lista[i + 1:]
        _salvar(login, nova, {"acao": "remove", "antes": saiu, "por": _texto(por)[:120], "origem": _texto(origem)[:200]})
    return {"ok": True, "mensagem": f"Tirei da ficha ({uso(nova)}/{TETO}): {saiu}"}


def texto_para_prompt(login: str) -> tuple[str, bool]:
    """(text for the turn's prompt, migrated?). Old format: the file as it is (cut long), so nothing is lost before the
    operator migrates it."""
    try:
        bruto = _ler_bruto(login)
    except EstadoIlegivel as exc:
        return f"(não consegui ler a ficha: {exc})", True
    if not migrada(bruto):
        texto = bruto.strip()
        return (texto[:12000] + "\n…(truncado)" if len(texto) > 12000 else texto), False
    lista = _entradas_de(bruto or "")
    if not lista:
        return "", True
    return "\n".join(f"- {e}" for e in lista) + f"\n({uso(lista)}/{TETO} caracteres)", True


def _entradas_antigas(bruto: str) -> list[str]:
    """Old free text → entries: each bullet (with its continuation lines) or loose paragraph line is one entry;
    headings, quotes and rules are dropped (they described sections, not facts)."""
    saida, atual = [], None
    for linha in bruto.splitlines():
        crua = linha.rstrip()
        limpa = crua.strip()
        if not limpa or limpa.startswith(("#", ">", "---", "<!--")):
            atual = None
            continue
        bala = re.match(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$", crua)
        if bala:
            atual = len(saida)
            saida.append(bala.group(1))
        elif atual is not None and crua[:1] in (" ", "\t"):
            saida[atual] += " " + limpa
        else:
            atual = len(saida)
            saida.append(limpa)
    return [_texto(e) for e in saida if _texto(e)]


def migrar(login: str, por: str = "operador", simular: bool = False, agora: float | None = None) -> dict:
    """Convert the old free-text ficha into entries (the operator runs it once per person, after the deploy).
    Keeps everything that passes the protection; entries it refuses stay only in the backup copy, listed in "fora".
    Over the ceiling it still writes (nothing is lost): the agent is then asked to consolidate on the next add."""
    agora = agora or time.time()
    with _exclusivo(login):
        bruto = _ler_bruto(login)
        if bruto is None:
            return {"efeito": "sem_ficha"}
        if migrada(bruto):
            return {"efeito": "ja_migrada", "entradas": len(_entradas_de(bruto))}
        lista, fora, vistas = [], [], set()
        for e in _entradas_antigas(bruto):
            chave = _chave(e)
            if chave in vistas:
                continue
            vistas.add(chave)
            motivo = _protecao().ameaca(e, ficha=True)
            if motivo:
                fora.append({"texto": e, "motivo": motivo})
            elif len(e) > MAX_ENTRADA:
                fora.append({"texto": e, "motivo": f"passa de {MAX_ENTRADA} caracteres"})
            else:
                lista.append(e)
        r = {"efeito": "simulado" if simular else "migrada", "entradas": len(lista), "uso": uso(lista), "teto": TETO,
             "acima_do_teto": uso(lista) > TETO, "fora": fora, "lista": lista}
        if simular:
            return r
        copia = PASTA / f"{_login(login)}.antes-ficha-{time.strftime('%Y%m%d-%H%M%S', time.localtime(agora))}.md"
        copia.write_text(bruto, encoding="utf-8")
        _salvar(login, lista, {"acao": "migrar", "por": _texto(por)[:120], "copia": copia.name,
                               "fora": [f["texto"] for f in fora]})
        r["copia"] = str(copia)
    return r

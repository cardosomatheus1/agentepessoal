"""Action ledger (12/10 review, §4.1): what the agent did in the world, with the result, kept where nothing can be changed
or deleted afterwards, and checked later by the Conferência (extension _45_conferencia.py).

- /a0/usr/central/agente.db, SQLite in WAL mode (many readers, one writer at a time, safe across processes).
- Table `acao` only grows: triggers refuse UPDATE and DELETE. Each row is one phase of an action (executada,
  falhou, cancelada…) with who, where (alvo), a hash and a short preview of the content, and a key tying the phases
  of the same action together (e.g. prosp:<action id>).
- registrar() never raises: the ledger must not stop the work it records (decision of 12/10: few locks).
- Test logins (teste_*) are not recorded, like the phone messages of tests.
"""

import hashlib
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path

PASTA = Path("/a0/usr/central")
BANCO = PASTA / "agente.db"
FASES = ("intencao", "executada", "falhou", "incerta", "verificada", "divergente", "cancelada")
VERBOS_COM_TEXTO = ("dm", "comentario")
JANELA_REPETIDA_H = 24

ESQUEMA = """
CREATE TABLE IF NOT EXISTS acao (
  id TEXT PRIMARY KEY,
  em REAL NOT NULL,
  fase TEXT NOT NULL CHECK (fase IN ('intencao','executada','falhou','incerta','verificada','divergente','cancelada')),
  login TEXT NOT NULL,
  origem TEXT NOT NULL,
  ator TEXT NOT NULL,
  ctx_id TEXT,
  ferramenta TEXT NOT NULL,
  verbo TEXT NOT NULL,
  alvo TEXT NOT NULL,
  conteudo_hash TEXT,
  conteudo_previa TEXT,
  chave TEXT,
  resultado TEXT,
  evidencia TEXT
);
CREATE INDEX IF NOT EXISTS acao_em ON acao(login, em);
CREATE INDEX IF NOT EXISTS acao_alvo ON acao(alvo, em);
CREATE INDEX IF NOT EXISTS acao_chave ON acao(chave);
CREATE TRIGGER IF NOT EXISTS acao_sem_update BEFORE UPDATE ON acao BEGIN SELECT RAISE(ABORT, 'o livro só acrescenta'); END;
CREATE TRIGGER IF NOT EXISTS acao_sem_delete BEFORE DELETE ON acao BEGIN SELECT RAISE(ABORT, 'o livro só acrescenta'); END;
CREATE TABLE IF NOT EXISTS alerta (chave TEXT PRIMARY KEY, em REAL NOT NULL, login TEXT NOT NULL, texto TEXT NOT NULL);
"""


def _conectar() -> sqlite3.Connection:
    PASTA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(BANCO, timeout=15)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=15000")
    con.executescript(ESQUEMA)
    return con


def _norm(texto: str) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip().lower()


def hash_conteudo(texto: str) -> str:
    return hashlib.sha256(_norm(texto).encode("utf-8")).hexdigest()[:20] if _norm(texto) else ""


def registrar(fase: str, login: str, origem: str, ferramenta: str, verbo: str, alvo: str, conteudo: str = "",
              chave: str = "", resultado: str = "", evidencia: dict | None = None, ctx_id: str = "",
              ator: str = "agente", em: float | None = None) -> str:
    """One phase of one action. Returns its id, or "" when it was not recorded (test login, bad phase, any error)."""
    login = str(login or "").lower()
    if not login or login.startswith("teste_") or fase not in FASES:
        return ""
    aid = f"{int((em or time.time()) * 1000):013d}-{uuid.uuid4().hex[:6]}"  # sorts by time
    try:
        with _conectar() as con:
            con.execute("INSERT INTO acao (id, em, fase, login, origem, ator, ctx_id, ferramenta, verbo, alvo, conteudo_hash,"
                        " conteudo_previa, chave, resultado, evidencia) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, em or time.time(), fase, login, origem, str(ator)[:120], ctx_id or None, ferramenta, verbo,
                         alvo, hash_conteudo(conteudo) or None, (str(conteudo)[:200] or None), chave or None,
                         (str(resultado)[:300] or None), json.dumps(evidencia, ensure_ascii=False)[:2000] if evidencia else None))
        return aid
    except Exception as exc:  # the ledger never stops the work it records
        print(f"central/livro: não registrei {verbo} {alvo}: {type(exc).__name__}: {exc}", flush=True)
        return ""


def _linhas(sql: str, args: tuple) -> list[dict]:
    try:
        with _conectar() as con:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute(sql, args).fetchall()]
    except Exception as exc:
        print(f"central/livro: leitura falhou: {exc}", flush=True)
        return []


def do_periodo(login: str, desde: float, ate: float | None = None) -> list[dict]:
    return _linhas("SELECT * FROM acao WHERE login = ? AND em >= ? AND em < ? ORDER BY em",
                   (str(login).lower(), desde, ate or time.time() + 1))


def logins() -> list[str]:
    return [r["login"] for r in _linhas("SELECT DISTINCT login FROM acao", ())]


def repetidas(login: str, agora: float | None = None, horas: float = JANELA_REPETIDA_H) -> list[dict]:
    """The same text to the same person executed twice or more inside the window: a message that may have gone out
    twice (11/10: Zen and Anna got the same DM twice)."""
    agora = agora or time.time()
    grupos = _linhas(
        "SELECT alvo, verbo, conteudo_hash, COUNT(*) AS vezes, MIN(em) AS primeira, MAX(em) AS ultima, "
        "MAX(conteudo_previa) AS previa FROM acao WHERE login = ? AND fase = 'executada' AND em >= ? "
        f"AND verbo IN ({','.join('?' * len(VERBOS_COM_TEXTO))}) AND conteudo_hash IS NOT NULL "
        "GROUP BY alvo, verbo, conteudo_hash HAVING COUNT(*) > 1",
        (str(login).lower(), agora - horas * 3600, *VERBOS_COM_TEXTO))
    return grupos


def novo_alerta(chave: str, login: str, texto: str) -> bool:
    """True the first time this finding is seen (then the Conferência tells the person once)."""
    try:
        with _conectar() as con:
            cur = con.execute("INSERT OR IGNORE INTO alerta (chave, em, login, texto) VALUES (?,?,?,?)",
                              (chave, time.time(), str(login).lower(), texto[:1000]))
            return cur.rowcount == 1
    except Exception as exc:
        print(f"central/livro: alerta não gravado: {exc}", flush=True)
        return False


def conferir(login: str, agora: float | None = None) -> list[dict]:
    """Findings that need a look, each with a stable key: {"chave", "texto"}. No model, no network."""
    achados = []
    for g in repetidas(login, agora):
        quando = " e ".join(time.strftime("%d/%m %H:%M", time.localtime(t)) for t in (g["primeira"], g["ultima"]))
        oque = "a mesma mensagem no Direct" if g["verbo"] == "dm" else "o mesmo comentário"
        achados.append({"chave": f"repetida:{g['alvo']}:{g['conteudo_hash']}:{g['vezes']}",
                        "texto": f"⚠️ *Conferência*: {oque} para {g['alvo'].split(':', 1)[-1]} foi registrado "
                                 f"{g['vezes']} vezes ({quando}): «{(g['previa'] or '')[:120]}». Confira a conversa no "
                                 "Instagram; se saiu repetida, me diga se apago a cópia."})
    return achados


ROTULOS = {"dm": "mensagens no Direct", "comentario": "comentários", "seguir_curtir": "seguir e curtir",
           "aviso": "avisos no celular", "segredo": "senhas usadas (só o nome)", "pesquisa": "pesquisas"}


def resumo(login: str, desde: float, ate: float | None = None, limite: int = 25) -> str:
    """What was done in the period, by kind, with the latest ones listed (for "o que você fez hoje?")."""
    linhas = [r for r in do_periodo(login, desde, ate) if r["fase"] in ("executada", "falhou", "cancelada", "divergente")]
    if not linhas:
        return "Nada registrado no livro nesse período."
    contagem: dict = {}
    for r in linhas:
        chave = (r["verbo"], r["fase"])
        contagem[chave] = contagem.get(chave, 0) + 1
    topo = "; ".join(f"{ROTULOS.get(v, v)} {'feitos' if f == 'executada' else f}: {n}"
                     for (v, f), n in sorted(contagem.items()))
    detalhe = [f"- {time.strftime('%d/%m %H:%M', time.localtime(r['em']))} {r['fase']} · {ROTULOS.get(r['verbo'], r['verbo'])} · "
               f"{r['alvo'].split(':', 1)[-1]}" + (f" · «{r['conteudo_previa'][:80]}»" if r["conteudo_previa"] else "")
               + (f" · {r['resultado'][:80]}" if r["resultado"] and r["fase"] != "executada" else "")
               for r in linhas[-limite:]]
    return topo + "\n" + "\n".join(detalhe)

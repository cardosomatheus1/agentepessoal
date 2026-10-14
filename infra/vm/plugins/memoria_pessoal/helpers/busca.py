"""Search the person's old conversations (from Hermes tools/session_search_tool.py, MIT: SQLite FTS5, no model).

- Source: /a0/usr/chats/<id>/chat.json (log items "user"/"response" of agent 0, the last 1000 of each chat). The
  index keeps what it saw, so older messages a chat log already dropped stay findable.
- Index: /a0/usr/memoria/busca.db, incremental: a chat is re-read only when its file changed, and only the items
  newer than what was indexed go in. A deleted chat leaves the index. A broken index is rebuilt from the chats.
- Per person: every row carries the chat owner (data "dono", or DONO for chats from before logins), and a search
  only sees rows of the person asking — Fernanda never sees Matheus's chats. Helper chats (subordinates, parallel
  workers: output_data parent_context_id) are working space, not conversations, and are not indexed.
- Scheduled rounds and the triggers chat are searchable but come after the person's own conversations (Hermes:
  routine vocabulary otherwise buries what the person said).
"""

import importlib.util
import json
import os
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path

CHATS = Path("/a0/usr/chats")
BANCO = Path("/a0/usr/memoria/busca.db")
TEMPO_MAX_S = 20  # indexing done per search at most (the first build continues on the next searches)
MAX_TEXTO = 4000
POR_CONVERSA = 2
_TRAVA = threading.Lock()

ESQUEMA = """
CREATE TABLE IF NOT EXISTS conversas (id TEXT PRIMARY KEY, mtime REAL, ate REAL, dono TEXT, rotina INTEGER,
                                      nome TEXT, oculta INTEGER);
CREATE VIRTUAL TABLE IF NOT EXISTS msgs USING fts5(texto, conversa UNINDEXED, papel UNINDEXED, em UNINDEXED,
                                                   dono UNINDEXED, rotina UNINDEXED,
                                                   tokenize='unicode61 remove_diacritics 2');
"""


def _conversas():
    nome = "memoria_pessoal_conversas"
    caminho = Path(__file__).resolve().parent / "conversas.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _abrir(banco: Path) -> sqlite3.Connection:
    banco.parent.mkdir(parents=True, exist_ok=True)
    for tentativa in range(2):
        con = sqlite3.connect(str(banco), timeout=30)
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(ESQUEMA)
            con.execute("SELECT count(*) FROM conversas").fetchone()
            return con
        except sqlite3.DatabaseError:
            con.close()
            if tentativa:
                raise
            for sufixo in ("", "-wal", "-shm"):  # derived data: rebuilt from the chats
                try:
                    os.unlink(f"{banco}{sufixo}")
                except OSError:
                    pass
    raise RuntimeError("índice indisponível")


def _ler_chat(arq: Path) -> dict | None:
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def atualizar(chats: Path | None = None, banco: Path | None = None, tempo_max: float = TEMPO_MAX_S,
              tarefas: Path | None = None) -> dict:
    """Bring the index up to date (most recently changed chats first, within tempo_max seconds).
    Returns {"lidas": chats read, "faltam": chats still to read, "removidas": chats gone}."""
    chats, banco = chats or CHATS, banco or BANCO
    cv = _conversas()
    inicio = time.time()
    with _TRAVA:
        con = _abrir(banco)
        try:
            vistos = {r[0]: (r[1], r[2]) for r in con.execute("SELECT id, mtime, ate FROM conversas")}
            arquivos = []
            try:
                for d in os.scandir(chats):
                    arq = Path(d.path) / "chat.json"
                    try:
                        arquivos.append((arq.stat().st_mtime, d.name, arq))
                    except OSError:
                        continue
            except OSError:
                return {"lidas": 0, "faltam": 0, "removidas": 0, "erro": f"sem a pasta {chats}"}
            presentes = {nome for _, nome, _ in arquivos}
            removidas = [cid for cid in vistos if cid not in presentes]
            for cid in removidas:
                con.execute("DELETE FROM msgs WHERE conversa = ?", (cid,))
                con.execute("DELETE FROM conversas WHERE id = ?", (cid,))
            mudados = sorted(((m, n, a) for m, n, a in arquivos if vistos.get(n, (None,))[0] != m), reverse=True)
            lidas = 0
            for mtime, cid, arq in mudados:
                if lidas and time.time() - inicio > tempo_max:
                    break
                _indexar(con, cv, cid, arq, mtime, vistos.get(cid, (None, 0.0))[1] or 0.0, tarefas)
                con.commit()
                lidas += 1
            con.commit()
            return {"lidas": lidas, "faltam": len(mudados) - lidas, "removidas": len(removidas)}
        finally:
            con.close()


def _indexar(con, cv, cid: str, arq: Path, mtime: float, ate: float, tarefas: Path | None) -> None:
    c = _ler_chat(arq)
    if c is None:  # being written right now: try again on the next search
        return
    dados = c.get("data") or {}
    oculta = bool((c.get("output_data") or {}).get("parent_context_id"))
    itens = cv.itens((c.get("log") or {}).get("logs") or [])
    primeira = next((x["texto"] for x in itens if x["tipo"] == "user"), "")
    rotina = int(cv.e_rotina(cid, primeira, dados, tarefas))
    dono = cv.dono(dados)
    novo_ate, completo = ate, True
    if not oculta:
        for x in itens:
            if x["em"] <= ate:
                continue
            if not x["pronta"]:  # an answer still being written: index it on a later pass
                completo = False
                break
            if x["tipo"] == "user":
                texto = cv.texto_dele(x["texto"])
                papel = "ele" if texto else "aviso"
                texto = texto or x["texto"]
            else:
                texto, papel = x["texto"], "agente"
            texto = texto.strip()[:MAX_TEXTO]
            if texto:
                con.execute("INSERT INTO msgs (texto, conversa, papel, em, dono, rotina) VALUES (?, ?, ?, ?, ?, ?)",
                            (texto, cid, papel, x["em"], dono, rotina))
            novo_ate = max(novo_ate, x["em"])
    con.execute("UPDATE msgs SET dono = ?, rotina = ? WHERE conversa = ? AND (dono != ? OR rotina != ?)",
                (dono, rotina, cid, dono, rotina))
    con.execute("INSERT OR REPLACE INTO conversas (id, mtime, ate, dono, rotina, nome, oculta) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cid, mtime if completo else 0.0, novo_ate, dono, rotina, str(c.get("name") or "")[:120], int(oculta)))


def _consulta(texto: str, juntar: str = " ") -> str:
    """Free text -> a safe FTS5 query: each word quoted (no operators can break it), longer words as prefixes."""
    palavras = [p for p in re.findall(r"\w+", str(texto or "").lower()) if len(p) > 1][:10]
    return juntar.join(f'"{p}"*' if len(p) >= 4 else f'"{p}"' for p in palavras)


def buscar(login: str, texto: str, limite: int = 8, chats: Path | None = None, banco: Path | None = None,
           tempo_max: float = TEMPO_MAX_S, tarefas: Path | None = None) -> dict:
    """{"resultados": [{conversa, nome, em, papel, trecho, rotina}], "faltam": chats not indexed yet}."""
    login = str(login or "").strip().lower()
    estado = atualizar(chats, banco, tempo_max, tarefas)
    q = _consulta(texto)
    if not q or not login:
        return {"resultados": [], "faltam": estado.get("faltam", 0)}
    con = _abrir(banco or BANCO)
    try:
        linhas = []
        for juntar in (" ", " OR "):
            linhas = con.execute(
                "SELECT m.conversa, c.nome, m.em, m.papel, snippet(msgs, 0, '«', '»', '…', 16), m.rotina "
                "FROM msgs m LEFT JOIN conversas c ON c.id = m.conversa "
                "WHERE msgs MATCH ? AND m.dono = ? ORDER BY m.rotina, bm25(msgs) LIMIT 300",
                (_consulta(texto, juntar), login)).fetchall()
            if linhas:
                break
    except sqlite3.OperationalError:
        linhas = []
    finally:
        con.close()
    resultados, por = [], {}
    for cid, nome, em, papel, trecho, rotina in linhas:
        if por.get(cid, 0) >= POR_CONVERSA:
            continue
        por[cid] = por.get(cid, 0) + 1
        resultados.append({"conversa": cid, "nome": nome or "", "em": float(em), "papel": papel,
                           "trecho": re.sub(r"\s+", " ", trecho).strip(), "rotina": bool(int(rotina))})
        if len(resultados) >= limite:
            break
    return {"resultados": resultados, "faltam": estado.get("faltam", 0)}


def texto(r: dict, consulta: str) -> str:
    if not r["resultados"]:
        fim = (f" (o índice ainda está sendo montado: faltam {r['faltam']} conversas; busque de novo daqui a pouco)"
               if r.get("faltam") else "")
        return f"Nada encontrado nas conversas antigas para {consulta!r}{fim}. Tente outras palavras."
    quem = {"ele": "a pessoa", "agente": "você", "aviso": "aviso"}
    linhas = [f"- {time.strftime('%d/%m/%Y %H:%M', time.localtime(x['em']))} · conversa {x['conversa']}"
              + (f" «{x['nome'][:60]}»" if x["nome"] else "") + (" (rotina)" if x["rotina"] else "")
              + f" · {quem.get(x['papel'], x['papel'])}: {x['trecho']}" for x in r["resultados"]]
    if r.get("faltam"):
        linhas.append(f"(índice ainda incompleto: faltam {r['faltam']} conversas)")
    return "\n".join(linhas)

"""Live panels made on request (22/10, from Claude Duet: "a sales dashboard that refreshes itself at 5:30 every morning,
right before your brief", with what to do about it). Each panel is a recipe (where to read, which numbers, which
conclusions) and the last values the agent read: /a0/usr/painel/vivos/<login>/<id>.json. A scheduled routine of the
agent refreshes it (the tool says how to create it); the Painel page shows every panel with the time it was read and
the source of each number. Values are plain text and numbers, checked here (no HTML, bounded sizes)."""

import json
import os
import re
import time
import uuid
from pathlib import Path

PASTA = Path(os.environ.get("PAINEL_PASTA", "/a0/usr/painel")) / "vivos"
MAX_PAINEIS = 12
MAX_NUMEROS, MAX_CONCLUSOES, MAX_LINHAS, MAX_COLUNAS = 12, 5, 30, 8
VELHO_S = 26 * 3600  # not refreshed for more than a day: marked old on the page
HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _login(login: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "", (login or "").lower()) or "matheus"


def _pasta(login: str) -> Path:
    return PASTA / _login(login)


def _txt(v, n: int) -> str:
    texto = re.sub(r"<[^>]*>", "", " ".join(str(v if v is not None else "").split()))
    return texto[:n]


def _gravar(arq: Path, d: dict) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(f".{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, arq)


def listar(login: str, agora: float | None = None) -> list:
    agora = time.time() if agora is None else agora
    saida = []
    for arq in sorted(_pasta(login).glob("*.json")):
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        d["velho"] = bool(d.get("dados")) and agora - float(d.get("atualizado") or 0) > VELHO_S
        saida.append(d)
    return sorted(saida, key=lambda d: d.get("criado", 0))


def obter(login: str, pid: str) -> dict | None:
    arq = _pasta(login) / f"{re.sub(r'[^a-z0-9]', '', str(pid))}.json"
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def criar(login: str, titulo: str, receita: str, hora: str = "06:30", agora: float | None = None) -> dict:
    titulo, receita, hora = _txt(titulo, 80), _txt(receita, 2000), str(hora or "06:30").strip()
    if len(titulo) < 3 or len(receita) < 20:
        return {"ok": False, "erro": "diga o título e a receita (de onde ler, quais números, que conclusões)"}
    if not HORA.match(hora):
        return {"ok": False, "erro": "hora no formato HH:MM (antes do resumo das 7:45, ex.: 06:30)"}
    if len(listar(login)) >= MAX_PAINEIS:
        return {"ok": False, "erro": f"já há {MAX_PAINEIS} painéis; peça para apagar um antes"}
    pid = uuid.uuid4().hex[:8]
    d = {"id": pid, "titulo": titulo, "receita": receita, "hora": hora, "criado": agora or time.time(), "dados": None}
    _gravar(_pasta(login) / f"{pid}.json", d)
    return {"ok": True, "painel": d}


def _numero(n) -> dict | None:
    if not isinstance(n, dict) or not _txt(n.get("rotulo"), 60):
        return None
    return {"rotulo": _txt(n.get("rotulo"), 60), "valor": _txt(n.get("valor"), 40),
            "variacao": _txt(n.get("variacao"), 40), "fonte": _txt(n.get("fonte"), 120)}


def salvar(login: str, pid: str, numeros=None, conclusoes=None, tabela=None, agora: float | None = None) -> dict:
    """The values the agent read now. Every number says where it came from (Duet: summaries cite their source)."""
    d = obter(login, pid)
    if not d:
        return {"ok": False, "erro": f"painel {pid} não existe"}
    nums = [x for x in (_numero(n) for n in (numeros or [])[:MAX_NUMEROS]) if x]
    if not nums:
        return {"ok": False, "erro": "mande pelo menos um número: {rotulo, valor, fonte, variacao?}"}
    sem_fonte = [n["rotulo"] for n in nums if not n["fonte"]]
    if sem_fonte:
        return {"ok": False, "erro": f"número sem fonte: {', '.join(sem_fonte)} (diga de onde veio: planilha, e-mail, sistema)"}
    tab = None
    if isinstance(tabela, dict) and isinstance(tabela.get("colunas"), list) and isinstance(tabela.get("linhas"), list):
        colunas = [_txt(c, 30) for c in tabela["colunas"][:MAX_COLUNAS]]
        linhas = [[_txt(c, 40) for c in (l if isinstance(l, list) else [])[:len(colunas)]] for l in tabela["linhas"][:MAX_LINHAS]]
        tab = {"colunas": colunas, "linhas": linhas}
    d["dados"] = {"numeros": nums, "conclusoes": [_txt(c, 240) for c in (conclusoes or [])[:MAX_CONCLUSOES] if _txt(c, 240)],
                  "tabela": tab}
    d["atualizado"] = agora or time.time()
    _gravar(_pasta(login) / f"{d['id']}.json", d)
    return {"ok": True, "painel": d}


def apagar(login: str, pid: str) -> bool:
    arq = _pasta(login) / f"{re.sub(r'[^a-z0-9]', '', str(pid))}.json"
    if not arq.exists():
        return False
    arq.unlink()
    return True


def prompt_rotina(d: dict) -> str:
    """The prompt of the scheduled routine that refreshes the panel."""
    return (f"Atualize o painel vivo «{d['titulo']}» (id {d['id']}). Receita: {d['receita']}\n"
            "Leia SÓ as fontes da receita (só leitura: nada de enviar, apagar ou mudar). Depois chame a ferramenta "
            f"painel_vivo acao \"salvar\" com id \"{d['id']}\", `numeros` (cada um com rotulo, valor, fonte e, se houver, "
            "variacao contra o período anterior), até 5 `conclusoes` curtas do que fazer com isso (o que preocupa, o que "
            "melhorou, o que investigar) e, se ajudar, uma `tabela` {colunas, linhas}. Número que não deu para ler fica de "
            "fora, e você diz qual faltou numa conclusão. Resposta final: uma linha com o que mudou de mais importante.")

"""Browser downloads with their real name, and the agent told where they are.

21/10, Matheus asked for an Outlook attachment (76437182_CL.xlsx): the agent clicked Baixar, looked for the file and
said it was "inside the browser". Playwright had saved it as /a0/usr/downloads/browser/<uuid>, no name and no
extension, and nothing told the agent. Now every download is also saved as /a0/usr/downloads/<real name> and the next
browser result says so ("Arquivo baixado: ...").
"""

import json
import re
import time
from pathlib import Path

PASTA = Path("/a0/usr/downloads")
REGISTRO = PASTA / "baixados.jsonl"
MANTER = 50  # registry lines kept


def nome_seguro(sugerido: str, pasta: Path = PASTA) -> Path:
    """The suggested file name, cleaned of path parts and odd characters, not overwriting an existing file."""
    nome = Path(str(sugerido or "").replace("\\", "/")).name.strip()
    nome = re.sub(r"[^\w.\- ()]+", "_", nome).strip(" .") or "download"
    base, ext = (nome.rsplit(".", 1) + [""])[:2] if "." in nome else (nome, "")
    alvo = pasta / nome
    n = 2
    while alvo.exists():
        alvo = pasta / (f"{base} ({n}).{ext}" if ext else f"{base} ({n})")
        n += 1
    return alvo


def registrar(caminho: Path, url: str = "", registro: Path = REGISTRO, agora: float | None = None) -> dict:
    item = {"caminho": str(caminho), "url": str(url or "")[:300], "em": agora if agora is not None else time.time(),
            "avisado": False}
    linhas = ler(registro)[-(MANTER - 1):] + [item]
    registro.parent.mkdir(parents=True, exist_ok=True)
    registro.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in linhas), encoding="utf-8")
    return item


def ler(registro: Path = REGISTRO) -> list[dict]:
    try:
        return [json.loads(l) for l in registro.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def a_avisar(registro: Path = REGISTRO) -> list[dict]:
    """Downloads not yet reported to the agent; marks them reported."""
    linhas = ler(registro)
    novos = [i for i in linhas if not i.get("avisado")]
    if novos:
        for i in linhas:
            i["avisado"] = True
        registro.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in linhas), encoding="utf-8")
    return novos


def aviso(itens: list[dict]) -> str:
    if not itens:
        return ""
    partes = []
    for i in itens:
        p = Path(i["caminho"])
        try:
            kb = f" ({max(1, round(p.stat().st_size / 1024))} KB)"
        except OSError:
            kb = ""
        partes.append(f"{p}{kb}")
    return "\n\n📥 Arquivo baixado e salvo com o nome real: " + "; ".join(partes) + \
        ". Use esse caminho (ele está no servidor, você pode ler ou anexar)."


async def salvar(download, pasta: Path = PASTA, registro: Path = REGISTRO) -> Path | None:
    """Playwright 'download' handler: keep a named copy and register it."""
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        alvo = nome_seguro(download.suggested_filename, pasta)
        await download.save_as(str(alvo))
        registrar(alvo, getattr(download, "url", ""), registro)
        return alvo
    except Exception as exc:  # never break the browser over this
        print(f"navegador_rapido: download: {exc}", flush=True)
        return None

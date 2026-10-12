#!/usr/bin/env python3
"""Daily health check of the agent VM (12/10 review, §4.6): one phone notice, and only when something is wrong.

Checks: disk, the three containers, the web UI, the model proxy, the phone bridge, the hourly backup, and scheduled
routines (in error, stuck "running", or a daily one that has not run for over a day). Runs from
agentepessoal-saude.timer (8h50 Bahia); `saude.py` alone prints the result, `--avisar` also sends the notice (at most
one a day). Last result in /var/lib/agentepessoal/saude.json. Python standard library only."""

import datetime as dt
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ESTADO = Path("/var/lib/agentepessoal")
TAREFAS = Path("/opt/a0/usr/scheduler/tasks.json")
CHAVE = Path("/opt/a0/usr/whatsapp/.chave")
CONTEINERES = ("agent-zero", "android", "ws-scrcpy")
DISCO_MAX = 85  # % used
BACKUP_MAX_H = 26
RODANDO_MAX_H = 3
HIBERNACAO_FALHOU = Path("/var/lib/agentepessoal/hibernacao_falhou")  # written by hibernate.sh
BINDER = Path("/sys/module/binder_linux")  # the phone container needs it
# 12/10 review: the backup said "done" but nobody ever restored from it. Every day these copies come back from S3 to a
# temporary folder and must open (JSON parses, SQLite passes integrity_check) and keep up with the live file.
CRITICOS = ("prospeccao/matheus.json", "memoria/decisoes/matheus.json", "scheduler/tasks.json", "central/agente.copia.db")
USR = Path("/opt/a0/usr")
ATRASO_MAX = 3 * 3600


def _data(texto) -> dt.datetime | None:
    if not texto:
        return None
    try:
        d = dt.datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def problemas_das_rotinas(tarefas: list, agora: dt.datetime) -> list[str]:
    """Routines in error, stuck running, or daily ones that did not run for over a day (disabled ones are fine)."""
    saida = []
    for t in tarefas:
        nome, estado = t.get("name") or t.get("uuid"), t.get("state")
        if estado == "disabled" or t.get("type") not in (None, "scheduled"):
            continue
        if estado == "error":
            saida.append(f"rotina «{nome}» em erro")
            continue
        mudou = _data(t.get("updated_at"))
        if estado == "running" and mudou and agora - mudou > dt.timedelta(hours=RODANDO_MAX_H):
            saida.append(f"rotina «{nome}» marcada como rodando há mais de {RODANDO_MAX_H} h")
            continue
        s = t.get("schedule") or {}
        diaria = all(str(s.get(k, "*")) == "*" for k in ("day", "month", "weekday"))
        ultima = _data(t.get("last_run"))
        criada = _data(t.get("created_at"))
        if diaria and s and criada and agora - criada > dt.timedelta(hours=30):
            if ultima is None or agora - ultima > dt.timedelta(hours=30):
                saida.append(f"rotina diária «{nome}» não roda há mais de 30 h")
    return saida


def problema_do_disco(usado: float, total: float) -> str:
    pct = 100 * usado / total if total else 0
    return f"disco da VM em {pct:.0f}% (limite {DISCO_MAX}%)" if pct >= DISCO_MAX else ""


def mensagem(problemas: list[str]) -> str:
    return ("🩺 *Saúde da VM do agente*: " + ("1 coisa" if len(problemas) == 1 else f"{len(problemas)} coisas")
            + " fora do normal:\n" + "\n".join(f"• {p}" for p in problemas)
            + "\n\nNenhum dado foi perdido. É manutenção: encaminhe ao Claude Code se aparecer de novo amanhã.")


def _http(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code  # it answered: the service is up
    except Exception:
        return 0


def _cmd(*args: str) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return ""


def problema_da_copia(nome: str, local: Path, copia: Path | None, agora: float) -> str:
    """What is wrong with one file restored from S3 ('' when it would restore fine)."""
    import sqlite3

    if copia is None or not copia.exists():
        return f"backup: {nome} não está no S3"
    try:
        if nome.endswith(".db"):
            con = sqlite3.connect(f"file:{copia}?mode=ro", uri=True)
            try:
                integro = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            finally:
                con.close()
            if not integro:
                return f"backup: a cópia de {nome} no S3 está corrompida"
        else:
            json.loads(copia.read_text(encoding="utf-8"))
    except Exception:
        return f"backup: a cópia de {nome} no S3 não abre"
    try:
        if agora - local.stat().st_mtime > ATRASO_MAX and local.read_bytes() != copia.read_bytes():
            return f"backup: {nome} mudou há mais de 3 h e o S3 ainda tem a versão antiga"
    except OSError:
        pass
    return ""


def _bucket() -> str:
    try:
        for linha in Path("/etc/agentepessoal.env").read_text().splitlines():
            if linha.startswith("BACKUP_BUCKET="):
                return linha.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


def conferir_backup() -> list[str]:
    """Restore the critical files from S3 into a temporary folder and check each one."""
    import tempfile

    bucket = _bucket()
    if not bucket:
        return ["backup: não achei o nome do bucket em /etc/agentepessoal.env"]
    problemas = []
    with tempfile.TemporaryDirectory(prefix="saude-backup-") as tmp:
        for nome in CRITICOS:
            destino = Path(tmp) / nome.replace("/", "__")
            _cmd("/usr/local/bin/aws", "s3", "cp", "--only-show-errors", f"s3://{bucket}/usr/{nome}", str(destino))
            if p := problema_da_copia(nome, USR / nome, destino if destino.exists() else None, time.time()):
                problemas.append(p)
    return problemas


def checar() -> list[str]:
    problemas = []
    uso = shutil.disk_usage("/")
    if p := problema_do_disco(uso.used, uso.total):
        problemas.append(p)
    for nome in CONTEINERES:
        if _cmd("docker", "inspect", "-f", "{{.State.Running}}", nome).strip() != "true":
            problemas.append(f"contêiner {nome} parado")
    if _http("http://127.0.0.1:50080/login") != 200:
        problemas.append("a interface do agente não responde")
    proxy = _http("http://127.0.0.1:8787/health")
    if not proxy:
        problemas.append("o proxy de modelos não responde")
    elif proxy != 200:
        problemas.append("o proxy de modelos não consegue gerar a chave da AWS (Bedrock)")
    if not _http("http://127.0.0.1:8789/"):
        problemas.append("a ponte do celular não responde")
    if not BINDER.exists():
        problemas.append("o driver do celular virtual (binder) não está carregado: o celular não sobe (kernel novo?)")
    try:
        if time.time() - HIBERNACAO_FALHOU.stat().st_mtime < 24 * 3600:
            problemas.append("a hibernação falhou e a VM foi desligada: religou do zero, sem as conversas abertas")
    except OSError:
        pass
    problemas += conferir_backup()
    feitos = _cmd("journalctl", "-t", "agentepessoal", "--since", f"-{BACKUP_MAX_H}h", "-o", "cat")
    if "backup to s3" not in feitos or " done" not in feitos:
        problemas.append(f"backup de hora em hora sem sucesso nas últimas {BACKUP_MAX_H} h")
    try:
        tarefas = json.loads(TAREFAS.read_text(encoding="utf-8")).get("tasks", [])
        problemas += problemas_das_rotinas(tarefas, dt.datetime.now(dt.timezone.utc))
    except (OSError, ValueError) as exc:
        problemas.append(f"lista de rotinas ilegível ({str(exc)[:60]})")
    return problemas


def avisar(texto: str) -> bool:
    marca = ESTADO / f"saude-aviso-{time.strftime('%F')}"
    if marca.exists():
        return False
    try:
        corpo = json.dumps({"usuario": "matheus", "texto": texto, "tipo": "progresso"}).encode()
        req = urllib.request.Request("http://127.0.0.1:8789/enviar", data=corpo, headers={
            "Content-Type": "application/json", "X-Chave": CHAVE.read_text().strip()})
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except Exception as exc:
        print(f"saude: aviso não entregue: {exc}", file=sys.stderr)
        return False
    marca.touch()
    return True


def main() -> int:
    problemas = checar()
    ESTADO.mkdir(parents=True, exist_ok=True)
    (ESTADO / "saude.json").write_text(json.dumps({"em": time.strftime("%FT%TZ", time.gmtime()), "problemas": problemas},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(problemas) or "tudo certo")
    if problemas and "--avisar" in sys.argv:
        avisar(mensagem(problemas))
    subprocess.run(["logger", "-t", "agentepessoal", f"saude: {len(problemas)} problema(s)"], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())

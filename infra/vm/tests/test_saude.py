"""Rules of the daily health check (infra/vm/saude.py), without touching the VM.
Run from the repository root: python3 infra/vm/tests/test_saude.py"""

import datetime as dt
import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def main() -> int:
    spec = importlib.util.spec_from_file_location("saude_teste", RAIZ / "infra" / "vm" / "saude.py")
    s = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(s)
    agora = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.timezone.utc)
    h = lambda horas: (agora - dt.timedelta(hours=horas)).isoformat()  # noqa: E731
    diaria = {"minute": "20,50", "hour": "9-19", "day": "*", "month": "*", "weekday": "*"}
    semanal = {"minute": "41", "hour": "8", "day": "*", "month": "*", "weekday": "1"}
    tarefas = [
        {"name": "ok", "type": "scheduled", "state": "idle", "schedule": diaria, "created_at": h(100), "last_run": h(2)},
        {"name": "erro", "type": "scheduled", "state": "error", "schedule": diaria, "created_at": h(100), "last_run": h(1)},
        {"name": "presa", "type": "scheduled", "state": "running", "schedule": diaria, "created_at": h(100),
         "updated_at": h(4), "last_run": h(28)},
        {"name": "rodando", "type": "scheduled", "state": "running", "schedule": diaria, "created_at": h(100),
         "updated_at": h(1), "last_run": h(20)},
        {"name": "parada", "type": "scheduled", "state": "idle", "schedule": diaria, "created_at": h(100), "last_run": h(40)},
        {"name": "semana", "type": "scheduled", "state": "idle", "schedule": semanal, "created_at": h(300), "last_run": h(150)},
        {"name": "nova", "type": "scheduled", "state": "idle", "schedule": diaria, "created_at": h(5), "last_run": None},
        {"name": "desligada", "type": "scheduled", "state": "disabled", "schedule": diaria, "created_at": h(100),
         "last_run": h(400)},
        {"name": "briefing", "type": "planned", "state": "idle", "created_at": h(100), "last_run": h(90)},
    ]
    obtido = s.problemas_das_rotinas(tarefas, agora)
    esperado = ["rotina «erro» em erro", "rotina «presa» marcada como rodando há mais de 3 h",
                "rotina diária «parada» não roda há mais de 30 h"]
    falhas = []
    if obtido != esperado:
        falhas.append(f"rotinas: esperado {esperado}, veio {obtido}")
    if s.problema_do_disco(60, 100) or not s.problema_do_disco(86, 100).startswith("disco da VM em 86%"):
        falhas.append("limite de disco (85%)")
    msg = s.mensagem(["a", "b"])
    if "2 coisas" not in msg or "• a" not in msg:
        falhas.append(f"mensagem: {msg!r}")
    # checar(): binder missing and a failed hibernation are reported (12/10 review); everything else stubbed as healthy
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="saude-"))
    s.TAREFAS = tmp / "tasks.json"
    s.TAREFAS.write_text('{"tasks": []}')
    s._http = lambda url: 200
    s._cmd = lambda *a: ("true" if a[0] == "docker" else
                         ("active" if "vigia-rede" in a[-1] else "inactive") if a[0] == "systemctl" else "backup to s3 ... done")
    s.REDE_ULTIMO, s.SOFTLOCKUP = tmp / "rede_ultimo.json", tmp / "softlockup_panic"
    s.hibernar_ligado = lambda: False
    s.shutil.disk_usage = lambda caminho: type("U", (), {"used": 10, "total": 100})()
    s.BINDER, s.HIBERNACAO_FALHOU = tmp / "sem_binder", tmp / "hibernacao_falhou"
    s.IO_URING, s.PANE = tmp / "io_uring_disabled", tmp / "pane_kernel.json"
    s.IO_URING.write_text("2\n")
    s.conferir_backup = lambda hermes=False: []  # restore check tested on its own below
    s.HIBERNACAO_FALHOU.touch()
    achados = s.checar()
    if not any("binder" in a for a in achados) or not any("hibernação falhou" in a for a in achados) or len(achados) != 2:
        falhas.append(f"checar: binder e hibernação deviam aparecer (e só eles): {achados}")
    s.BINDER.mkdir()
    s.HIBERNACAO_FALHOU.unlink()
    if s.checar():
        falhas.append(f"checar: tudo bem devia dar lista vazia: {s.checar()}")
    # 23/10: io_uring ligado de novo e uma pane recente aparecem; pane antiga não
    s.IO_URING.write_text("0\n")
    s.PANE.write_text('{"quando": "2026-10-23T21:49:44Z", "processo": "DelayedTaskSche", "onde": "do_raw_spin_lock", '
                      '"s3": "s3://b/incidentes/x.txt"}')
    achados = s.checar()
    if len(achados) != 2 or not any("io_uring" in a for a in achados) or not any("DelayedTaskSche" in a and "s3://" in a for a in achados):
        falhas.append(f"checar: io_uring ligado e pane recente deviam aparecer: {achados}")
    s.IO_URING.write_text("2\n")
    velho = __import__("time").time() - 3 * 86400
    __import__("os").utime(s.PANE, (velho, velho))
    if s.checar():
        falhas.append(f"checar: pane de 3 dias atrás não é mais aviso: {s.checar()}")
    # 24/10: sempre ligada: timer da hibernação de volta, vigia da rede parado, trava do kernel sem pane, religada pela rede
    agora_s = __import__("time").time()
    if s.problemas_de_ficar_ligada(False, "inactive", "active", "1", None, agora_s):
        falhas.append("ficar ligada: tudo certo devia dar lista vazia")
    if s.problemas_de_ficar_ligada(True, "active", "active", "", None, agora_s):
        falhas.append("ficar ligada: com HIBERNAR=1 o timer da hibernação ligado é normal")
    achados = s.problemas_de_ficar_ligada(False, "active", "inactive", "0",
                                          {"sem_rede_desde": "2026-10-23T23:22:00Z", "s3": "s3://b/incidentes/rede.txt"},
                                          agora_s, agora_s - 3600)
    if len(achados) != 4 or not any("hibernação automática voltou" in a for a in achados) \
            or not any("vigia da rede" in a for a in achados) or not any("trava do kernel" in a for a in achados) \
            or not any("sem internet" in a and "s3://b/incidentes/rede.txt" in a for a in achados):
        falhas.append(f"ficar ligada: os 4 problemas deviam aparecer: {achados}")
    if s.problemas_de_ficar_ligada(False, "inactive", "active", "1", {"sem_rede_desde": "x"}, agora_s, agora_s - 3 * 86400):
        falhas.append("ficar ligada: religada pela rede há 3 dias não é mais aviso")
    s.SOFTLOCKUP.write_text("0\n")
    if not any("trava do kernel" in a for a in s.checar()):
        falhas.append("checar: softlockup_panic=0 devia aparecer")
    s.SOFTLOCKUP.write_text("1\n")
    env = tmp / "agentepessoal.env"
    env.write_text("BACKUP_BUCKET=x\nHIBERNAR=1\n")
    import importlib.util as _iu
    spec2 = _iu.spec_from_file_location("saude_env", RAIZ / "infra" / "vm" / "saude.py")
    s2 = _iu.module_from_spec(spec2)
    spec2.loader.exec_module(s2)
    if not s2.hibernar_ligado(env) or s2.hibernar_ligado(tmp / "nao_existe"):
        falhas.append("hibernar_ligado: só com HIBERNAR=1 no env")
    env.write_text("HIBERNAR=0\n")
    if s2.hibernar_ligado(env):
        falhas.append("hibernar_ligado: HIBERNAR=0 é desligado")
    # restore check: a copy from S3 must open and keep up with the live file
    import json as _json
    import os
    import sqlite3

    vivo, copia = tmp / "vivo.json", tmp / "copia.json"
    vivo.write_text(_json.dumps({"a": 2}))
    copia.write_text(_json.dumps({"a": 1}))
    agora_s = __import__("time").time()
    os.utime(vivo, (agora_s - 3600, agora_s - 3600))
    if s.problema_da_copia("x.json", vivo, copia, agora_s):
        falhas.append("backup: diferença de 1 h é atraso normal do backup de hora em hora")
    os.utime(vivo, (agora_s - 5 * 3600, agora_s - 5 * 3600))
    if "versão antiga" not in s.problema_da_copia("x.json", vivo, copia, agora_s):
        falhas.append("backup: mudou há 5 h e o S3 não pegou deveria aparecer")
    copia.write_text("{cortado")
    if "não abre" not in s.problema_da_copia("x.json", vivo, copia, agora_s):
        falhas.append("backup: JSON cortado no S3 deveria aparecer")
    if "não está" not in s.problema_da_copia("x.json", vivo, None, agora_s):
        falhas.append("backup: arquivo ausente no S3 deveria aparecer")
    nota_viva, nota_copia = tmp / "indice.md", tmp / "indice_copia.md"  # 20/10: a note of the Pasta is Markdown
    nota_viva.write_text("# Decisoes\n")
    nota_copia.write_text("# Decisoes\n")
    if s.problema_da_copia("pasta/Decisoes/indice.md", nota_viva, nota_copia, agora_s):
        falhas.append("backup: nota Markdown da Pasta deveria abrir")
    nota_copia.write_text("\x00lixo")
    if "não abre" not in s.problema_da_copia("pasta/Decisoes/indice.md", nota_viva, nota_copia, agora_s):
        falhas.append("backup: nota sem título no S3 deveria aparecer")
    if "segundo_cerebro/pasta/Decisoes/indice.md" not in s.CRITICOS:
        falhas.append("backup: as decisões (na Pasta) estão entre os arquivos críticos")
    banco = tmp / "copia.db"
    con = sqlite3.connect(banco)
    con.execute("CREATE TABLE t (x)")
    con.commit()
    con.close()
    if s.problema_da_copia("central/agente.copia.db", tmp / "nao_existe.db", banco, agora_s):
        falhas.append("backup: banco íntegro no S3 não é problema")
    # virada ao Hermes: os contêineres, a interface e as rotinas são os do Hermes
    import datetime as _dt
    import time as _time
    s.DESTINO = tmp / "destino.json"
    s.DESTINO.write_text('{"padrao": "hermes"}')
    if not s.modo_hermes():
        falhas.append("virada: modo Hermes pela chave")
    (tmp / "hermes" / "convidados" / "ilia").mkdir(parents=True)
    (tmp / "hermes" / "convidados" / "ilia" / "porta").write_text("8660")
    nomes = s.conteineres_hermes(tmp / "hermes")
    if "hermes" not in nomes or "hermes-ilia" not in nomes or "agent-zero" in nomes:
        falhas.append(f"virada: contêineres do Hermes e dos convidados, não o A0: {nomes}")
    agora = _dt.datetime(2026, 10, 25, 12, tzinfo=_dt.timezone.utc)
    jobs = [{"name": "Resumo", "enabled": True, "state": "scheduled", "schedule": {"expr": "45 7 * * *"},
             "created_at": "2026-10-20T00:00:00+00:00", "last_run_at": "2026-10-23T10:45:00+00:00"},
            {"name": "Erro", "enabled": True, "state": "scheduled", "last_status": "error", "last_error": "boom"},
            {"name": "Pausada", "enabled": False, "state": "paused", "last_status": "error"}]
    achados = s.problemas_das_rotinas_hermes(jobs, agora)
    if len(achados) != 2 or not any("Resumo" in a and "30 h" in a for a in achados) or not any("Erro" in a for a in achados):
        falhas.append(f"virada: rotinas do Hermes em erro ou paradas (as pausadas não): {achados}")
    s.TICK = tmp / "tick"
    s.TICK.write_text("x")
    s.JOBS = tmp / "jobs.json"
    s.JOBS.write_text('{"jobs": []}')
    s.conteineres_hermes = lambda: ("hermes",)
    urls = []
    s._http = lambda url: urls.append(url) or 200
    s.checar()
    if not any("8642" in u for u in urls) or any("50080" in u for u in urls):
        falhas.append(f"virada: confere a API do Hermes e não a interface do A0: {urls}")
    import os as _os
    _os.utime(s.TICK, (_time.time() - 3600, _time.time() - 3600))
    if not any("relógio das rotinas" in a for a in s.checar()):
        falhas.append("virada: relógio do cron parado é problema")
    s.shutil.rmtree(tmp, ignore_errors=True)
    for f in falhas:
        print("FALHA", f)
    print("TESTES", 10 - len(falhas), 10)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

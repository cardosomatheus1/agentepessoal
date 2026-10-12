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
    s._cmd = lambda *a: "true" if a[0] == "docker" else "backup to s3 ... done"
    s.shutil.disk_usage = lambda caminho: type("U", (), {"used": 10, "total": 100})()
    s.BINDER, s.HIBERNACAO_FALHOU = tmp / "sem_binder", tmp / "hibernacao_falhou"
    s.HIBERNACAO_FALHOU.touch()
    achados = s.checar()
    if not any("binder" in a for a in achados) or not any("hibernação falhou" in a for a in achados) or len(achados) != 2:
        falhas.append(f"checar: binder e hibernação deviam aparecer (e só eles): {achados}")
    s.BINDER.mkdir()
    s.HIBERNACAO_FALHOU.unlink()
    if s.checar():
        falhas.append(f"checar: tudo bem devia dar lista vazia: {s.checar()}")
    s.shutil.rmtree(tmp, ignore_errors=True)
    for f in falhas:
        print("FALHA", f)
    print("TESTES", 4 - len(falhas), 4)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

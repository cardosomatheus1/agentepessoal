"""Wake-up for the next task: an unreadable tasks file keeps the wake-up already set (it used to delete it), a start
refused for a moment is retried by EventBridge, and "nothing scheduled" still removes it. Fake AWS, temporary folder.
Run from the repository root: python3 infra/vm/tests/test_despertar.py (needs boto3 and croniter for the import)."""

import datetime as dt
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


class AgendadorFalso:
    class exceptions:
        class ResourceNotFoundException(Exception):
            pass

        class ConflictException(Exception):
            pass

    def __init__(self):
        self.criados, self.apagados = [], []

    def create_schedule(self, **kw):
        self.criados.append(kw)

    def update_schedule(self, **kw):
        self.criados.append(kw)

    def delete_schedule(self, Name):
        self.apagados.append(Name)


def main() -> int:
    spec = importlib.util.spec_from_file_location("despertar_teste", RAIZ / "infra" / "vm" / "proximo_despertar.py")
    p = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)
    tmp = Path(tempfile.mkdtemp(prefix="despertar-"))
    falhas = []

    def ok(cond, msg):
        if not cond:
            falhas.append(msg)

    try:
        ag = AgendadorFalso()
        p.boto3 = type("B", (), {"client": staticmethod(lambda nome, region_name=None: ag if nome == "scheduler" else
                                                       type("S", (), {"get_caller_identity": lambda self: {"Account": "1"}})())})
        p.instancia = lambda: "i-teste"
        p.TAREFAS = tmp / "tasks.json"
        agora = dt.datetime(2026, 10, 12, 20, 0, tzinfo=dt.timezone.utc)

        p.TAREFAS.write_text('{"tasks": [{"name": "Resumo", "ty', encoding="utf-8")  # cut in half
        p.agendar(agora)
        ok(not ag.apagados and not ag.criados, "tarefas ilegíveis: o despertar que já estava fica")
        sys.argv = ["x", "--perto", "15"]
        ok(p.main() == 0, "--perto com tarefas ilegíveis não trava a hibernação")

        quando = (agora + dt.timedelta(hours=10)).isoformat()
        p.TAREFAS.write_text(json.dumps({"tasks": [{"name": "Resumo", "type": "planned", "state": "idle",
                                                     "plan": {"todo": [quando]}}]}), encoding="utf-8")
        p.agendar(agora)
        c = ag.criados[-1]
        ok(c["ScheduleExpression"] == "at(2026-10-13T05:55:00)", f"acorda 5 min antes: {c['ScheduleExpression']}")
        ok(c["Target"].get("RetryPolicy", {}).get("MaximumRetryAttempts", 0) >= 3, "partida recusada é tentada de novo")
        ok(json.loads(c["Target"]["Input"]) == {"InstanceIds": ["i-teste"]}, "liga esta VM")

        p.TAREFAS.write_text(json.dumps({"tasks": []}), encoding="utf-8")
        p.agendar(agora)
        ok(ag.apagados == [p.NOME], "sem nenhuma tarefa, o despertar sai (ficar dormindo é o certo)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for f in falhas:
        print("FALHA", f)
    print("despertar:", "ok" if not falhas else f"{len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

"""A guest past the day's limit (ponte_whatsapp writes /a0/usr/whatsapp/<login>/limite_hoje.txt) has their routines
paused; the next day the ones paused here come back (helpers/convidados.py decidir_pausa)."""

import datetime as dt
import importlib.util
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_ESTADO = {"ultimo": 0.0}


def convidados():
    nome, caminho = "login_usuarios_convidados", RAIZ / "helpers" / "convidados.py"
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


class LimiteConvidados(Extension):
    async def execute(self, **kwargs):
        if time.time() - _ESTADO["ultimo"] < 60:
            return
        _ESTADO["ultimo"] = time.time()
        try:
            from helpers.task_scheduler import TaskScheduler, TaskState

            c = convidados()
            hoje = dt.datetime.now(ZoneInfo("America/Bahia")).strftime("%Y-%m-%d")
            agenda = TaskScheduler.get()
            for login in c.CONVIDADOS:
                pasta = c.CELULAR / login
                marca, registro = pasta / "limite_hoje.txt", pasta / "rotinas_pausadas.json"
                passou = marca.exists() and marca.read_text().strip() == hoje
                pausadas = json.loads(registro.read_text()) if registro.exists() else []
                tarefas = [(t.uuid, str(getattr(t.state, "value", t.state))) for t in agenda.get_tasks()
                           if t.project_name == c.projeto(login)]
                pausar, voltar = c.decidir_pausa(passou, tarefas, pausadas)
                for u in pausar:
                    await agenda.update_task(u, state=TaskState.DISABLED)
                for u in voltar:
                    await agenda.update_task(u, state=TaskState.IDLE)
                if pausar or voltar or (pausadas and not passou):
                    novo = sorted(set(pausadas) | set(pausar)) if passou else []
                    pasta.mkdir(parents=True, exist_ok=True)
                    registro.write_text(json.dumps(novo))
                    print(f"login_usuarios: rotinas de {login}: pausadas {pausar}, voltaram {voltar}", flush=True)
        except Exception as exc:
            print(f"login_usuarios: limite dos convidados: {type(exc).__name__}: {exc}", flush=True)

"""Once every 6 hours: chats idle for 7 days are archived (helpers/arquivar.py). Copy first, then remove."""

import importlib.util
import json
import shutil
import time
from pathlib import Path

from helpers.extension import Extension

CHATS = Path("/a0/usr/chats")
ARQUIVO = Path("/a0/usr/chats_arquivo")
MARCA = Path("/a0/usr/marcas/limpeza_arquivar")
LOG = Path("/a0/usr/limpeza/log.jsonl")
INTERVALO = 6 * 3600

_spec = importlib.util.spec_from_file_location("limpeza_arquivar", Path(__file__).resolve().parents[3] / "helpers" / "arquivar.py")
arquivar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(arquivar)


def _na_hora() -> bool:
    try:
        if time.time() - MARCA.stat().st_mtime < INTERVALO:
            return False
    except OSError:
        pass
    MARCA.parent.mkdir(parents=True, exist_ok=True)
    MARCA.touch()
    return True


class ArquivarConversas(Extension):
    async def execute(self, **kwargs):
        if not CHATS.exists() or not _na_hora():
            return
        from agent import AgentContext
        from helpers import persist_chat
        from helpers.task_scheduler import TaskScheduler

        sched = TaskScheduler.get()
        tarefas = {t.uuid for t in sched.get_tasks()}
        itens = []
        for pasta in CHATS.iterdir():
            arq = pasta / "chat.json"
            if not arq.exists():
                continue
            try:
                data = (json.loads(arq.read_text(encoding="utf-8")) or {}).get("data") or {}
            except Exception:
                continue  # unreadable: leave it alone
            ctx = AgentContext.get(pasta.name)
            itens.append({"id": pasta.name, "mtime": arq.stat().st_mtime, "data": data,
                          "tem_tarefa": pasta.name in tarefas or bool(sched.get_tasks_by_context_id(pasta.name)),
                          "rodando": bool(ctx and ctx.is_running())})
        for ctxid in arquivar.escolher(itens):
            try:
                ARQUIVO.mkdir(parents=True, exist_ok=True)
                shutil.copytree(CHATS / ctxid, ARQUIVO / ctxid, dirs_exist_ok=True)
                ctx = AgentContext.get(ctxid)
                if ctx:
                    ctx.reset()
                AgentContext.remove(ctxid)
                persist_chat.remove_chat(ctxid)
                LOG.parent.mkdir(parents=True, exist_ok=True)
                with LOG.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"em": time.time(), "arquivada": ctxid}) + "\n")
            except Exception as exc:
                print(f"limpeza: não arquivei {ctxid}: {exc}", flush=True)

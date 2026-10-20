"""At each message of a chat's main agent, apply the model preset by owner/chat (helpers/modelo.py). Off while the
file modelo_por_dono.json does not exist; any failure leaves the chat's model as it was."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def modelo():
    nome, caminho = "login_usuarios_modelo", RAIZ / "helpers" / "modelo.py"
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def rotina(ctx) -> bool:
    try:
        from helpers.task_scheduler import TaskScheduler

        return bool(TaskScheduler.get().get_tasks_by_context_id(ctx.id))
    except Exception:
        return False


class ModeloPorDono(Extension):
    async def execute(self, loop_data=None, **kwargs):
        agent = self.agent
        if not agent or getattr(agent, "number", 1) != 0:
            return
        try:
            M = modelo()
            cfg = M.ler()
            ctx = agent.context
            if not cfg and not ctx.get_data(M.AUTO):
                return  # off (the usual case): nothing to set or to undo
            sep = sys.modules.get("login_usuarios_separacao")
            dono = sep.dono_contexto(ctx) if sep else (ctx.get_data("dono") or "")
            feito = M.aplicar(ctx, dono, rotina(ctx), cfg)
            if feito and feito != "manual":
                print(f"login_usuarios: modelo da conversa {ctx.id}: {feito}", flush=True)
        except Exception as exc:
            print(f"login_usuarios: modelo por dono não aplicado: {type(exc).__name__}: {exc}", flush=True)

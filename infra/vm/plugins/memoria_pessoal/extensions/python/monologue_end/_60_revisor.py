"""End of a turn in the person's phone chat: offer a routine when a task of several steps just worked, and every ~8 of
their messages review the conversation for decisions, routine corrections and facts about them (helpers/revisor.py).
Never in scheduled rounds or the triggers chat. Runs in a background thread: the turn is already over and the person
is not kept waiting for the model."""

import importlib.util
import sys
import threading
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
PLUGINS = RAIZ.parent
GUARDAR = {"memoria_pessoal_revisor": ("RODANDO",)}  # in-flight reviews survive a reload


def carregar(nome: str, caminho: Path):
    """A helper by path, reloaded when the file changes."""
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        for estado in GUARDAR.get(nome, ()):
            if antigo is not None and hasattr(antigo, estado):
                setattr(modulo, estado, getattr(antigo, estado))
        sys.modules[nome] = modulo
    return sys.modules[nome]


def meu(nome: str):
    return carregar(f"memoria_pessoal_{nome}", RAIZ / "helpers" / f"{nome}.py")


def rotinas():
    """rotinas/helpers/rotinas.py (another plugin's): None while it is not installed or lacks the interface, and
    routine corrections and suggestions stay off."""
    try:
        m = carregar("rotinas_helper_revisor", PLUGINS / "rotinas" / "helpers" / "rotinas.py")
    except Exception:
        return None
    return m if callable(getattr(m, "listar", None)) and callable(getattr(m, "corrigir", None)) else None


def ponte():
    return sys.modules.get("whatsapp_ponte") or carregar("whatsapp_ponte", PLUGINS / "whatsapp" / "helpers" / "ponte.py")


def conversa_do_celular(ctx, conversas, tarefa=None) -> str:
    """The login whose phone chat this is, or "" (any other chat: app, scheduled round, triggers, someone else's)."""
    login = str(ctx.get_data("whatsapp_de") or "").strip().lower()
    if not login or ctx.get_data("gatilhos_de"):
        return ""
    if conversas.e_rotina(ctx.id) or (tarefa is not None and tarefa(ctx)):
        return ""
    if str(ctx.get_data("dono") or login).strip().lower() != login:
        return ""
    return login


def _rodar(login: str, nome: str, ctx_id: str, logs: list, do_app: set) -> None:
    try:
        rv, cv = meu("revisor"), meu("conversas")
        enviar = lambda quem, texto: ponte().enviar(quem, texto, tipo="progresso")  # noqa: E731  (kept in avisos_recentes)
        rot = rotinas()
        r1 = rv.sugerir_rotina(login, nome, ctx_id, cv.turno(logs), do_app, meu("protecao"), rot,
                               texto_dele=cv.texto_dele, enviar=enviar)
        r2 = rv.revisar(login, nome, ctx_id, cv.itens(logs), do_app, meu("decisoes"), meu("ficha"), meu("protecao"), rot,
                        texto_dele=cv.texto_dele, enviar=enviar)
        for r in (r1, r2):
            if r.get("feito") and (r.get("aviso") or r.get("descartados")):
                print(f"memoria_pessoal: revisor {login}/{ctx_id}: aviso={r.get('aviso')!r} "
                      f"descartados={len(r.get('descartados') or [])}", flush=True)
    except Exception as exc:  # never visible to the person; the next turn tries again
        print(f"memoria_pessoal: revisor falhou: {type(exc).__name__}: {exc}", flush=True)


class Revisor(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent or self.agent.number != 0:
            return
        ctx = self.agent.context
        try:
            tarefa = getattr(sys.modules.get("whatsapp_ponte"), "tarefa", None)
            login = conversa_do_celular(ctx, meu("conversas"), tarefa)
            if not login:
                return
            logs = list(ctx.log.logs)
            do_app = set(ctx.get_data("_memoria_do_app") or [])
            nome = str(ctx.get_data("usuario_nome") or login.title())
            threading.Thread(target=_rodar, args=(login, nome, ctx.id, logs, do_app), daemon=True,
                             name="memoria-revisor").start()
        except Exception as exc:
            print(f"memoria_pessoal: revisor não iniciou: {type(exc).__name__}: {exc}", flush=True)

"""A reboot (or a crash) leaves scheduled tasks marked "running" with nothing running: the scheduler then never runs
them again (10/10: the prospecting round and "fios soltos" stayed stuck after the VM reboot). Every 10 minutes, a
task that has been "running" for more than 90 minutes with no live run goes back to idle.

A recurring task that ended in "error" is never run again either (the scheduler only runs idle tasks; 11/10: the
prospecting search and the NEXOS watch died for good when the model proxy was down during a reboot). A recurring
task in error for more than ERRO_MIN minutes goes back to idle, so it runs again at its next scheduled time; when the
error was a dropped connection (proxy or model not reachable for a moment) less than REPETIR_ERRO_MIN minutes ago, it
is run again right away, once per failed run (12/10 review: the round lost to a boot waited for its next time).

12/10: the check looked for the run only in the chat (ctx.task), but the scheduler keeps its own run (a DeferredTask
in TaskScheduler._running_deferred_tasks), so every scheduled run looked dead; and it counted the minutes from
last_run, the start of the PREVIOUS run. The search (2 runs a day) and the first execution round of the morning were
put back to idle minutes after starting, and the scheduler started them again in the same chat: 3 copies of each ran
at once and 4 «PRECISA DE VOCÊ» reached the phone. Now a run the scheduler still holds is never touched, and the
minutes count from when the task became "running" (updated_at).

Also 12/10: the loop detector paused the search round's chat (it kept opening the same profile while 3 copies ran);
a paused scheduled round never moves again, since nobody presses "resume", and the next run of the same round got
stuck behind it. A scheduled round paused for more than PAUSADA_MIN minutes is resumed once; paused again within 2
hours, the run is cancelled (the round runs again at its next time) and the chat unpaused.

14/10 (ideas from Hermes cron/scheduler_liveness and cron/unreachable_retry): a run the scheduler still holds was never
touched, so a round stuck mid-run (a model call that never came back, an await that never ends) stayed "running"
forever and the round never ran again. A live run whose chats (the round's and its helpers') get no new log item and
no model call for PARADA_MIN minutes is ended (the round runs again at its next time); a tool that legitimately takes
long (a terminal command running, an approval waiting for Matheus) keeps it alive. And the re-run after a dropped
connection now happens only when the run got no model call back (chat_model_call_after/_10_contar_chamadas.py): it did
nothing and spent nothing, so running it again cannot repeat an action. It runs again after 5, 15 and 30 minutes
(DEGRAUS); then it waits for its next time. The check now runs every minute, so the 5 minutes are 5 minutes."""

import json
import re
import sys
import time
from pathlib import Path

from helpers.extension import Extension

INTERVALO = 60
PRESA_MIN = 90
ERRO_MIN = 5
PAUSADA_MIN = 10
REPETIR_H = 2
REPETIR_ERRO_MIN = 60
DEGRAUS = (5, 15, 30)  # minutes after each failed run that never got a model call back
PARADA_MIN = 20
# tools that legitimately run long with nothing new in the log
LONGAS = {"code_execution_tool", "code_execution_remote", "input", "wait"}
CHAMADAS = "_limpeza_chamadas"  # chat_model_call_after/_10_contar_chamadas.py
CONEXAO = re.compile(r"connect|conex|timed? ?out|unreachable|refused|reset by peer|\b50[234]\b|bad gateway|"
                     r"service unavailable|name or service not known|temporary failure", re.I)
REPETIDAS = Path("/a0/usr/limpeza/repetidas.json")  # task -> {marca: failed run, tentativa, devida, feita}
PARADAS = Path("/a0/usr/limpeza/paradas.json")  # task -> {marca: activity seen, desde: when it last changed}
LOG = Path("/a0/usr/limpeza/log.jsonl")
PAUSAS = Path("/a0/usr/limpeza/pausadas.json")  # module state does not survive the job loop: kept in a file
MARCA = Path("/a0/usr/marcas/limpeza_rotinas")


def _na_hora(marca: Path, intervalo: float) -> bool:
    """True at most once per intervalo. Job-loop extensions are loaded again on every pass, so a module variable
    never kept the time (12/10 review: "every 10 minutes" ran every minute): the time lives in the marker's mtime."""
    try:
        if time.time() - marca.stat().st_mtime < intervalo:
            return False
    except OSError:
        pass
    try:
        marca.parent.mkdir(parents=True, exist_ok=True)
        marca.touch()
    except OSError:
        pass
    return True


def _vivo(tarefa) -> bool:
    if tarefa is None:
        return False
    try:
        return bool(tarefa.is_alive())
    except Exception:
        return True  # cannot tell: leave it alone


def _minutos(quando, agora: float) -> float:
    return (agora - quando.timestamp()) / 60 if quando else 9999


def _inicio_processo() -> float:
    """When this Agent Zero process started (boot time + the process start in clock ticks): no run is older."""
    try:
        import os

        with open("/proc/self/stat") as f:
            ticks = int(f.read().rsplit(")", 1)[1].split()[19])  # field 22, starttime
        with open("/proc/stat") as f:
            boot = next(int(l.split()[1]) for l in f if l.startswith("btime"))
        return boot + ticks / os.sysconf("SC_CLK_TCK")
    except Exception:
        return 0.0


def _pai_id(ctx) -> str:
    try:
        pid = ctx.get_output_data("parent_context_id") or ""
    except Exception:
        pid = ""
    return pid or ctx.get_data("_parallel_parent_context_id") or ctx.get_data("parent_context_id") or ""


def familia(raiz_id: str, contextos) -> list:
    """The round's chat and every chat it started (helpers in their own chats, parallel workers), at any depth."""
    por_id = {c.id: c for c in contextos}
    saida = []
    for c in por_id.values():
        x = c
        for _ in range(8):
            if x is None:
                break
            if x.id == raiz_id:
                saida.append(c)
                break
            x = por_id.get(_pai_id(x))
    return saida


def assinatura(contextos) -> str:
    """Changes with every new or updated log item and every model call that came back, in any of the chats."""
    partes = []
    for c in contextos:
        log = getattr(c, "log", None)
        chamadas = (c.get_data(CHAMADAS) or {}).get("n", 0)
        partes.append(f"{c.id}:{getattr(log, 'guid', '')}:{len(getattr(log, 'updates', None) or [])}:{chamadas}")
    return "|".join(sorted(partes))


def _agentes(ctx):
    agent, vistos = getattr(ctx, "agent0", None), set()
    while agent is not None and id(agent) not in vistos:
        vistos.add(id(agent))
        yield agent
        agent = (getattr(agent, "data", None) or {}).get("_subordinate")


def ferramenta_longa(contextos, pendentes=()) -> bool:
    """A terminal command (or another tool that is slow on purpose) is running, or an approval waits for Matheus."""
    for c in contextos:
        if c.id in pendentes:
            return True
        for agent in _agentes(c):
            tool = getattr(getattr(agent, "loop_data", None), "current_tool", None)
            if tool is not None and getattr(tool, "name", "") in LONGAS:
                return True
    return False


def _parada(t, agora: float, paradas: dict, atividade, longa) -> dict | None:
    """A live run whose activity did not change for PARADA_MIN minutes, with no long tool running, is ended."""
    sig = atividade(t.context_id)
    reg = paradas.get(t.uuid)
    if sig is None:
        paradas.pop(t.uuid, None)
        return None
    if (longa and longa(t.context_id)) or not reg or reg.get("marca") != sig:
        paradas[t.uuid] = {"marca": sig, "desde": agora}
        return None
    m = (agora - reg["desde"]) / 60
    if m <= PARADA_MIN:
        return None
    paradas.pop(t.uuid, None)
    return {"tarefa": t.uuid, "nome": t.name, "parada_min": int(m), "acao": "encerrar"}


def _novo_degrau(t, marca: str, quando, agora: float, rep: dict | None, chamadas) -> dict | None:
    """The next re-run of a failed run, or None. Only a dropped connection in a run that got no model call back (it
    did nothing); after the last step of DEGRAUS the round waits for its next time."""
    m = _minutos(quando, agora)
    if chamadas is None or m > REPETIR_ERRO_MIN or not CONEXAO.search(str(getattr(t, "last_result", "") or "")):
        return None
    if (chamadas(t.context_id) if t.context_id else None) != 0:  # unknown counts as "did something"
        return None
    seguida = rep and agora - float(rep.get("feita") or rep.get("devida") or 0) < REPETIR_H * 3600
    k = int(rep.get("tentativa", -1)) + 1 if seguida else 0
    if k >= len(DEGRAUS):
        return None
    return {"marca": marca, "tentativa": k, "devida": quando.timestamp() + DEGRAUS[k] * 60}


def destravar(tarefas, rodando: dict, tarefa_do_chat, agora: float, running, error, pausada=None,
              pausas: dict | None = None, inicio: float = 0.0, repetidas: dict | None = None, chamadas=None,
              atividade=None, longa=None, paradas: dict | None = None) -> list[dict]:
    """Which tasks go back to idle (or get resumed / cancelled / ended / run again). `rodando`: the scheduler's live
    runs by task uuid; `tarefa_do_chat(id)`: the run of the task's chat, or None; `pausada(id)`: the chat is paused;
    `pausas`: per task, when it was first seen paused and when it was last resumed (updated in place); `repetidas`:
    per task, the re-run planned after a failed run (updated in place); `chamadas(id)`: model calls that came back in
    the chat's current task (None = unknown); `atividade(id)`: a text that changes whenever the round's chats move
    (None = unknown); `longa(id)`: a slow tool runs; `paradas`: per task, the activity seen and since when."""
    pausas = {} if pausas is None else pausas
    soltas = []
    vistas = set()
    for t in tarefas:
        vistas.add(t.uuid)
        rep = repetidas.get(t.uuid) if repetidas is not None else None
        rep = rep if isinstance(rep, dict) else None  # the old format kept only the failed run's time
        if t.state == error and getattr(t, "schedule", None) is not None:
            quando = getattr(t, "last_run", None) or getattr(t, "updated_at", None)
            m = _minutos(quando, agora)
            marca = quando.isoformat() if quando else ""
            if repetidas is not None and marca and (rep is None or rep.get("marca") != marca):
                rep = _novo_degrau(t, marca, quando, agora, rep, chamadas)
                if rep:
                    repetidas[t.uuid] = rep
                else:
                    repetidas.pop(t.uuid, None)
            devida = bool(rep and not rep.get("feita") and agora >= rep["devida"])
            if m > ERRO_MIN or devida:
                item = {"tarefa": t.uuid, "nome": t.name, "erro_min": int(m)}
                if devida:
                    item.update(acao="repetir", degrau=rep["tentativa"] + 1)
                    rep["feita"] = agora
                soltas.append(item)
            continue
        if t.state != running:
            if t.uuid in pausas:
                pausas[t.uuid].pop("desde", None)  # a pause belongs to a run: the next run starts counting again
            if paradas is not None:
                paradas.pop(t.uuid, None)
            if rep:
                ultima = getattr(t, "last_run", None)
                parado = str(getattr(t.state, "value", t.state)) == "disabled"
                if parado or (ultima.isoformat() if ultima else "") != rep.get("marca") or (
                        rep.get("feita") and agora - rep["feita"] > REPETIR_H * 3600):
                    repetidas.pop(t.uuid, None)  # it ran since (or was switched off): the ladder starts over
                elif not rep.get("feita") and agora >= rep["devida"]:
                    soltas.append({"tarefa": t.uuid, "nome": t.name, "acao": "repetir", "degrau": rep["tentativa"] + 1})
                    rep["feita"] = agora
            continue
        reg = pausas.get(t.uuid) or {}
        if pausada and t.context_id and pausada(t.context_id):
            reg.setdefault("desde", agora)
            pausas[t.uuid] = reg
            m = (agora - reg["desde"]) / 60
            if m > PAUSADA_MIN:
                cancelar = agora - reg.get("retomada", 0) < REPETIR_H * 3600
                soltas.append({"tarefa": t.uuid, "nome": t.name, "pausada_min": int(m), "acao": "cancelar" if cancelar else "retomar"})
                pausas[t.uuid] = {} if cancelar else {"retomada": agora}
            continue
        reg.pop("desde", None)
        if reg:
            pausas[t.uuid] = reg
        if _vivo(rodando.get(t.uuid)) or _vivo(tarefa_do_chat(t.context_id) if t.context_id else None):
            if atividade and paradas is not None and t.context_id:
                item = _parada(t, agora, paradas, atividade, longa)
                if item:
                    soltas.append(item)
            continue
        quando = getattr(t, "updated_at", None) or getattr(t, "last_run", None)
        m = _minutos(quando, agora)
        if m > PRESA_MIN or (inicio and quando and quando.timestamp() < inicio):
            # a run never survives a restart: marked "running" before this process started means nothing runs it
            soltas.append({"tarefa": t.uuid, "nome": t.name, "presa_min": int(m)})
    for k in [k for k, v in pausas.items() if not v.get("desde") and agora - v.get("retomada", 0) > REPETIR_H * 3600]:
        del pausas[k]
    for registro in (paradas, repetidas):
        for k in [k for k in (registro or {}) if k not in vistas]:
            del registro[k]
    return soltas


class DestravarRotinas(Extension):
    async def execute(self, **kwargs):
        if not _na_hora(MARCA, INTERVALO):
            return
        try:
            from agent import AgentContext
            from helpers.task_scheduler import TaskScheduler, TaskState

            sched = TaskScheduler.get()
            with getattr(sched, "_running_tasks_lock", None) or _SemTrava():
                rodando = dict(getattr(sched, "_running_deferred_tasks", None) or {})

            def tarefa_do_chat(cid):
                ctx = AgentContext.get(cid)
                return getattr(ctx, "task", None) if ctx else None

            def pausada(cid):
                ctx = AgentContext.get(cid)
                return bool(ctx and getattr(ctx, "paused", False))

            try:
                pausas = json.loads(PAUSAS.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pausas = {}
            try:
                repetidas = json.loads(REPETIDAS.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                repetidas = {}
            try:
                paradas = json.loads(PARADAS.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                paradas = {}
            contextos = list(AgentContext.all())

            def chamadas(cid):
                ctx = AgentContext.get(cid)
                reg = ctx.get_data(CHAMADAS) if ctx else None
                return int(reg.get("n") or 0) if isinstance(reg, dict) else None

            def atividade(cid):
                chats = familia(cid, contextos)
                return assinatura(chats) if chats else None

            def longa(cid):
                revisor = sys.modules.get("aprovacoes_revisor")  # approvals waiting for Matheus (read only)
                return ferramenta_longa(familia(cid, contextos), getattr(revisor, "PENDENTES", None) or {})

            tarefas = {t.uuid: t for t in sched.get_tasks()}
            soltas = destravar(tarefas.values(), rodando, tarefa_do_chat, time.time(), TaskState.RUNNING, TaskState.ERROR,
                               pausada, pausas, _inicio_processo(), repetidas, chamadas, atividade, longa, paradas)
            PAUSAS.parent.mkdir(parents=True, exist_ok=True)
            PAUSAS.write_text(json.dumps(pausas), encoding="utf-8")
            REPETIDAS.write_text(json.dumps(repetidas), encoding="utf-8")
            PARADAS.write_text(json.dumps(paradas), encoding="utf-8")
            for s in soltas:
                ctx = AgentContext.get(tarefas[s["tarefa"]].context_id) if tarefas[s["tarefa"]].context_id else None
                if s.get("acao") == "retomar":
                    if ctx:
                        ctx.paused = False
                    continue
                if s.get("acao") in ("cancelar", "encerrar"):
                    sched.cancel_running_task(s["tarefa"])
                    if ctx:
                        ctx.paused = False
                        if s.get("acao") == "encerrar" and _vivo(getattr(ctx, "task", None)):
                            ctx.kill_process()  # controle_agente also ends the commands left in its terminals
                await sched.update_task(s["tarefa"], state=TaskState.IDLE)
                if s.get("acao") == "repetir":  # the run never got a model call back: run it again
                    try:
                        await sched.run_task_by_uuid(s["tarefa"])
                    except Exception as exc:
                        print(f"limpeza: could not re-run {s['nome']}: {exc}", flush=True)
            if soltas:
                LOG.parent.mkdir(parents=True, exist_ok=True)
                with LOG.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"em": time.time(), "rotinas_destravadas": soltas}, ensure_ascii=False) + "\n")
                print(f"limpeza: unstuck {len(soltas)} scheduled tasks: {soltas}", flush=True)
        except Exception as exc:
            print(f"limpeza: unstick check failed: {exc}", flush=True)


class _SemTrava:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

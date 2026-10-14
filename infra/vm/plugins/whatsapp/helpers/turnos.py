"""Phone requests that were running when the agent restarted (Hermes: tui_gateway/turn_marker.py,
gateway/restart_loop_guard.py, the resume of gateway/run_startup).

When memguard restarts the container, the request the person sent from the phone died in silence. Now
api/receber.py opens a mark per chat when a phone request starts (ARQ "turnos"), the final answer closes it
(_50_enviar_resposta), and on the job loop (_56_retomar_pedido) a mark left by a previous process is a request
that was cut short:
- his last message in it came less than RETOMAR_ATE ago: resumed, with the warning to check in the `livro`
  what was already done;
- older, already resumed once, or the agent is restarting in a loop (LACO starts, each less than
  LACO_INTERVALO after the one before): a question with the buttons "▶️ Retomar" / "🙈 Deixa" (ARQ "perguntas").
A mark of this same process whose chat stopped without a final answer (error, /parar) is dropped.
Every function is best-effort: a mark must never break a request.
"""

import contextlib
import fcntl
import json
import os
import time
from pathlib import Path

ARQ = Path("/a0/usr/whatsapp/turnos_abertos.json")   # {"turnos": {ctx_id: mark}, "perguntas": {ctx_id: mark}}
SUBIDAS = Path("/a0/usr/whatsapp/reinicios.json")    # {"processo": last seen, "subidas": [epoch, ...], "laco"}
RETOMAR_ATE = 15 * 60
LACO = 3
LACO_INTERVALO = 5 * 60
SEM_RESPOSTA = 60      # a mark of this process whose chat stopped this long ago ended without an answer
VIDA = 24 * 3600       # older marks and questions are forgotten
MAX_PEDIDOS = 5
MAX_TEXTO = 2000


def processo() -> str:
    """This process, across container restarts and reboots (pids repeat inside a container)."""
    partes = [str(os.getpid())]
    try:
        partes.append(Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19])  # start time, in ticks
    except (OSError, IndexError):
        pass
    try:
        partes.append(Path("/proc/sys/kernel/random/boot_id").read_text().strip()[:8])
    except OSError:
        pass
    return ":".join(partes)


@contextlib.contextmanager
def _trava():
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    with open(ARQ.with_name(ARQ.name + ".trava"), "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _ler(arq: Path) -> dict:
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar(arq: Path, dados: dict) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_name(f".{arq.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, arq)


def turnos() -> dict:
    return dict(_ler(ARQ).get("turnos") or {})


def perguntas() -> dict:
    return dict(_ler(ARQ).get("perguntas") or {})


def obter(ctx_id: str) -> dict | None:
    return turnos().get(ctx_id)


def pergunta_de(ctx_id: str) -> dict | None:
    """The question still waiting on him for chat ctx_id, if any."""
    return perguntas().get(ctx_id)


def _mudar(mexer) -> None:
    """Load, mexer(turnos, perguntas) in place, store; never raises."""
    try:
        with _trava():
            d = _ler(ARQ)
            t, q = dict(d.get("turnos") or {}), dict(d.get("perguntas") or {})
            mexer(t, q)
            _gravar(ARQ, {"turnos": t, "perguntas": q})
    except Exception as exc:
        print(f"whatsapp: open-request mark not saved: {exc}", flush=True)


def abrir(ctx_id: str, usuario: str, pedido: str, anexos: list | None = None, agora: float | None = None,
          proc: str | None = None) -> dict | None:
    """A phone request starts (or adds to the running one) in chat ctx_id. Returns the mark of a request the restart
    cut short in that chat when this message came before the job loop dealt with it (the caller tells the agent)."""
    agora, proc = agora or time.time(), proc or processo()
    cortado = {}

    def mexer(t, _q):
        m = t.get(ctx_id)
        if m and m.get("processo") == proc:  # the same request: one more message
            m["pedidos"] = (list(m.get("pedidos") or []) + [pedido[:MAX_TEXTO]])[-MAX_PEDIDOS:]
            m["anexos"] = list(m.get("anexos") or []) + list(anexos or [])
            m["ultima"] = agora
            return
        if m:  # left by the previous process: this message takes it on (and that counts as its one resume)
            cortado.update(m)
        t[ctx_id] = {"usuario": usuario, "pedidos": (list(cortado.get("pedidos") or []) + [pedido[:MAX_TEXTO]])[-MAX_PEDIDOS:],
                     "anexos": list(cortado.get("anexos") or []) + list(anexos or []), "desde": agora, "ultima": agora,
                     "processo": proc, "retomadas": int(cortado.get("retomadas") or 0) + (1 if m else 0)}

    _mudar(mexer)
    return cortado or None


def fechar(ctx_id: str) -> None:
    """The request got its final answer."""
    _mudar(lambda t, q: t.pop(ctx_id, None))


def tirar_pergunta(ctx_id: str) -> None:
    _mudar(lambda t, q: q.pop(ctx_id, None))


def _cadeia(subidas: list, agora: float) -> list:
    """The unbroken chain of starts up to now (each within LACO_INTERVALO of the next), oldest first."""
    cadeia, antes = [], agora
    for t in sorted(subidas, reverse=True):
        if antes - t > LACO_INTERVALO:
            break
        cadeia.append(t)
        antes = t
    return cadeia[::-1]


def subiu(proc: str | None = None, agora: float | None = None) -> tuple[bool, bool]:
    """Called on every job-loop pass: (new process?, did this process start in a restart loop?). A new process is
    recorded once (Hermes' breaker: starts chain while each comes within LACO_INTERVALO of the one before)."""
    agora, proc = agora or time.time(), proc or processo()
    d = _ler(SUBIDAS)
    if d.get("processo") == proc:
        return False, bool(d.get("laco"))
    cadeia = _cadeia([float(x) for x in d.get("subidas") or [] if isinstance(x, (int, float))], agora) + [agora]
    laco = len(cadeia) >= LACO
    try:
        _gravar(SUBIDAS, {"processo": proc, "subidas": cadeia[-20:], "laco": laco})
    except OSError as exc:
        print(f"whatsapp: restart not recorded: {exc}", flush=True)
    return True, laco


def planejar(marcas: dict, proc: str, agora: float, rodando, laco: bool) -> list[tuple[str, str, dict]]:
    """What to do with each open mark: [(acao, ctx_id, mark)], acao in descartar | retomar | perguntar | adotar.
    rodando(ctx_id) -> True/False, or None when the chat no longer exists."""
    plano = []
    for ctx_id, m in marcas.items():
        vivo = rodando(ctx_id)
        if agora - float(m.get("ultima") or m.get("desde") or 0) > VIDA:
            plano.append(("descartar", ctx_id, m))
        elif m.get("processo") == proc:
            if not vivo and agora - float(m.get("ultima") or 0) > SEM_RESPOSTA:
                plano.append(("descartar", ctx_id, m))  # stopped without a final answer (error, /parar)
        elif vivo:
            plano.append(("adotar", ctx_id, m))  # already running again (a new message started it)
        elif laco or int(m.get("retomadas") or 0) >= 1 or agora - float(m.get("ultima") or 0) >= RETOMAR_ATE:
            plano.append(("perguntar", ctx_id, m))
        else:
            plano.append(("retomar", ctx_id, m))
    return plano


def _resumo(m: dict, n: int = 120) -> str:
    texto = " ".join(" ".join(m.get("pedidos") or []).split())
    return texto if len(texto) <= n else texto[:n - 1].rsplit(" ", 1)[0] + "…"


def texto_retomada(m: dict, agora: float | None = None) -> str:
    """What the agent gets when the request is resumed."""
    pedidos = list(m.get("pedidos") or [])
    corpo = pedidos[-1] if len(pedidos) == 1 else "\n\n".join(f"{i}. {p}" for i, p in enumerate(pedidos, 1))
    hora = time.strftime("%H:%M", time.localtime(agora or time.time()))
    return (f"🔁 [Reiniciei no meio deste pedido (o servidor do agente reiniciou; retomado às {hora}). Antes de continuar, "
            "confira no `livro` (e no que já está nesta conversa) o que você já fez, para não repetir nada que envie, "
            "publique, pague ou mude algo fora daqui. Depois termine o pedido e responda normalmente.]\n\n"
            f"Pedido{'s' if len(pedidos) > 1 else ''} do celular:\n{corpo}")


def aviso_cortado(m: dict) -> str:
    """Put before a new phone message that arrived in a chat whose request the restart cut short."""
    return ("[Reiniciei no meio do pedido anterior desta conversa: «" + _resumo(m, 300) + "». Antes confira no `livro` "
            "o que já fez dele, para não repetir nada; se esta mensagem não o encerra, termine-o também.]\n\n")


def motivo(m: dict, laco: bool) -> str:
    return "laco" if laco else "retomado" if int(m.get("retomadas") or 0) >= 1 else "velho"


def pergunta(m: dict, ctx_id: str, por: str, agora: float | None = None) -> tuple[str, list]:
    """(text, buttons) asking whether to resume a request the restart cut short."""
    agora = agora or time.time()
    minutos = max(1, round((agora - float(m.get("ultima") or agora)) / 60))
    quando = f"há {minutos} min" if minutos < 120 else f"há {round(minutos / 60)} h"
    porque = {"laco": " Ele reiniciou várias vezes seguidas, então não retomei sozinho.",
              "retomado": " Eu já tinha retomado esse pedido uma vez e ele caiu de novo."}.get(por, "")
    usuario = str(m.get("usuario") or "")
    texto = (f"🔁 O agente reiniciou no meio do seu pedido «{_resumo(m)}» (de {quando}).{porque} "
             "Quer que eu retome? Antes de continuar eu confiro o que já tinha feito.")
    return texto, [{"id": f"rt:{usuario}:{ctx_id}:sim", "titulo": "▶️ Retomar"},
                   {"id": f"rt:{usuario}:{ctx_id}:nao", "titulo": "🙈 Deixa"}]


def rodada(achar, principal, agora: float | None = None, proc: str | None = None, retomar_fn=None) -> list[tuple]:
    """One job-loop pass. achar(ctx_id) -> chat or None; principal(login) -> the person's main phone chat or None.
    Resumes what it should and returns the phone messages to send: [(login, text, buttons)]."""
    agora, proc = agora or time.time(), proc or processo()
    retomar_fn = retomar_fn or retomar
    _, laco = subiu(proc, agora)
    velhas = [c for c, m in perguntas().items() if agora - float(m.get("perguntado_em") or 0) > VIDA]
    if velhas:
        _mudar(lambda t, q: [q.pop(c, None) for c in velhas])
    marcas = turnos()
    if not marcas:
        return []

    def rodando(cid):
        ctx = achar(cid)
        return None if ctx is None else bool(ctx.is_running())

    mensagens = []
    for acao, cid, m in planejar(marcas, proc, agora, rodando, laco):
        usuario = str(m.get("usuario") or "")
        if acao == "descartar":
            fechar(cid)
            continue
        if acao == "adotar":
            _mudar(lambda t, q, c=cid: t.get(c, {}).update(processo=proc))
            continue
        ctx = (achar(cid) or principal(usuario)) if acao == "retomar" else None
        if ctx is not None:
            try:
                retomar_fn(ctx, cid, m, agora)
                print(f"whatsapp: resumed the phone request of {cid} cut short by a restart", flush=True)
                mensagens.append((usuario, f"🔁 O agente reiniciou no meio do seu pedido «{_resumo(m)}». Já retomei; "
                                           "antes de continuar ele confere o que já tinha feito.", None))
                continue
            except Exception as exc:
                print(f"whatsapp: resume of {cid} failed, asking instead: {exc}", flush=True)
        texto, botoes = pergunta(m, cid, motivo(m, laco), agora)

        def mexer(t, q, c=cid, m=m):
            t.pop(c, None)
            q[c] = {**m, "perguntado_em": agora}
        _mudar(mexer)
        mensagens.append((usuario, texto, botoes))
    return mensagens


def retomar(ctx, ctx_id: str, m: dict, agora: float | None = None, entregar=None) -> None:
    """Hand the cut-short request of chat ctx_id back to ctx (the same chat, or the person's main phone chat when that
    one is gone) with Agent Zero's own objects; it becomes an open request of this process, counted as resumed.
    entregar(ctx, msg): how a chat that is running again gets it (receber's _intervir keeps an unread intervention)."""
    from agent import UserMessage
    from helpers import message_queue as mq

    agora = agora or time.time()
    texto = texto_retomada(m, agora)
    anexos = [a for a in m.get("anexos") or [] if Path(str(a)).exists()]
    novo = {k: v for k, v in m.items() if k != "perguntado_em"}
    novo.update(processo=processo(), retomadas=int(m.get("retomadas") or 0) + 1, ultima=agora)

    def mexer(t, q):
        t.pop(ctx_id, None)
        q.pop(ctx_id, None)
        t[ctx.id] = novo
    _mudar(mexer)
    ctx.set_data("whatsapp_ultima_entrada", agora)
    mq.log_user_message(ctx, texto, anexos, None, source=" (retomada)")
    msg = UserMessage(message=texto, attachments=anexos)
    if entregar is not None and ctx.is_running():
        entregar(ctx, msg)
    else:
        ctx.communicate(msg)

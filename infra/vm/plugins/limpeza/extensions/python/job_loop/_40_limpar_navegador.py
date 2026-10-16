"""Browser tabs pile up: every chat and every scheduled round keeps its pages open (and they are restored after a
restart). On 10/10 they reached 75 Chromium processes / 11.8 GB and froze the VM. Every 5 minutes this closes the
tabs of conversations that are not running and have been quiet for a while; the less memory is left, the shorter the
wait. A conversation that comes back simply opens a new tab. Each cleanup is logged to /a0/usr/limpeza/log.jsonl."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from helpers.extension import Extension

INTERVALO = 5 * 60
OCIOSA_MIN = 20          # normal: tabs of chats quiet for 20 min
OCIOSA_APERTO_MIN = 5    # memory below APERTO_MB: 5 min
APERTO_MB = 3000
CRITICO_MB = 1500        # below this: every chat that is not running right now
LOG = Path("/a0/usr/limpeza/log.jsonl")
PULSO = Path("/a0/usr/limpeza/ultima_verificacao.json")  # proof the check runs (diagnosis)
MARCA = Path("/a0/usr/marcas/limpeza_navegador")


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


def memoria_livre_mb() -> int:
    try:
        for linha in Path("/proc/meminfo").read_text().splitlines():
            if linha.startswith("MemAvailable:"):
                return int(linha.split()[1]) // 1024
    except Exception:
        pass
    return 99999


def _rodando(ctx) -> bool:
    tarefa = getattr(ctx, "task", None)
    try:
        return bool(tarefa and tarefa.is_alive())
    except Exception:
        return bool(tarefa)


def _minutos_parada(ctx) -> float:
    ultima = getattr(ctx, "last_message", None)
    if not isinstance(ultima, datetime):
        return 9999.0
    agora = datetime.now(ultima.tzinfo or timezone.utc)
    return (agora - ultima).total_seconds() / 60


def escolher(contextos: dict, livre_mb: int) -> list[tuple[str, str]]:
    """(context_id, why) of the browser sessions to close. contextos: context_id -> AgentContext or None."""
    limite = 0 if livre_mb < CRITICO_MB else OCIOSA_APERTO_MIN if livre_mb < APERTO_MB else OCIOSA_MIN
    fechar = []
    for cid, ctx in contextos.items():
        if ctx is None:
            fechar.append((cid, "conversa não existe mais"))
        elif float(ctx.get_data("navegador_em_uso_ate") or 0) > time.time():
            continue  # 16/10: someone is driving this tab through the live view (navegador_visual): never close it
        elif not _rodando(ctx) and _minutos_parada(ctx) >= limite:
            fechar.append((cid, f"parada há {int(_minutos_parada(ctx))} min (limite {limite} min, {livre_mb} MB livres)"))
    return fechar


class LimparNavegador(Extension):
    async def execute(self, **kwargs):
        if not _na_hora(MARCA, INTERVALO):
            return
        try:
            from agent import AgentContext
            from plugins._browser.helpers import runtime as modulo

            with modulo._runtime_lock:
                ids = list(modulo._runtimes)
            livre = memoria_livre_mb()
            PULSO.parent.mkdir(parents=True, exist_ok=True)
            PULSO.write_text(json.dumps({"em": time.time(), "livre_mb": livre, "sessoes_de_navegador": len(ids)}))
            fechadas = []
            for cid, motivo in escolher({cid: AgentContext.get(cid) for cid in ids}, livre):
                try:
                    await modulo.close_runtime(cid)
                    fechadas.append({"contexto": cid, "motivo": motivo})
                except Exception as exc:
                    print(f"limpeza: could not close browser of {cid}: {exc}", flush=True)
            if fechadas:
                LOG.parent.mkdir(parents=True, exist_ok=True)
                with LOG.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"em": time.time(), "livre_mb": livre, "fechadas": fechadas,
                                        "depois_mb": memoria_livre_mb()}, ensure_ascii=False) + "\n")
                print(f"limpeza: closed browser tabs of {len(fechadas)} idle chats ({livre} MB free before)", flush=True)
        except Exception as exc:
            print(f"limpeza: browser cleanup failed: {exc}", flush=True)

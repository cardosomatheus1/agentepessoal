"""One screen of what the agent is doing for a person (like Dots' Activity tab): running now, waiting on
them, scheduled tasks, latest important actions. The bridge adds today's spend and answers /painel."""

import json
import secrets
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from helpers.api import ApiHandler, Request, Response

CHAVE = Path("/a0/usr/whatsapp/.chave")
FUSO = ZoneInfo("America/Bahia")


def _dono(ctx) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    try:
        return ((sep.dono_contexto(ctx) if sep else ctx.get_data("dono")) or "matheus").lower()
    except Exception:
        return "matheus"


def _hora(dt) -> str:
    try:
        return dt.astimezone(FUSO).strftime("%d/%m %H:%M")
    except Exception:
        return "?"


def painel(usuario: str) -> str:
    from agent import AgentContext

    saida = []
    agora = []
    for ctx in AgentContext.all():
        if _dono(ctx) != usuario:
            continue
        try:
            rodando = ctx.is_running()
        except Exception:
            rodando = False
        if rodando:
            prog = " ".join(str(getattr(ctx.log, "progress", "") or "").split())[:90]
            agora.append(f"• {ctx.name or ctx.id}" + (f" — {prog}" if prog else ""))
    saida.append("⚙️ *Fazendo agora*\n" + ("\n".join(agora) if agora else "Nada rodando."))

    esperando = []
    rev = sys.modules.get("aprovacoes_revisor")
    for cid, p in (getattr(rev, "PENDENTES", {}) or {}).items():
        ctx = AgentContext.get(cid)
        if p.get("decisao") is None and ctx is not None and _dono(ctx) == usuario:
            esperando.append(f"• Aprovar: {p.get('resumo')} ({ctx.name or cid})")
    pon = sys.modules.get("whatsapp_ponte")
    pedido = (getattr(pon, "PEDIDOS", {}) or {}).get(usuario)
    if pedido and not pedido.get("codigo"):
        esperando.append(f"• Código pedido: {pedido.get('motivo') or pedido.get('servico') or 'verificação'}")
    saida.append("⏳ *Esperando você*\n" + ("\n".join(esperando) if esperando else "Nada."))

    tarefas = []
    try:
        from helpers.task_scheduler import ScheduledTask, TaskScheduler

        lim = sys.modules.get("agenda_limites")
        dados = lim.carregar() if lim else {}
        for t in TaskScheduler.get().get_tasks():
            ctx = AgentContext.get(t.context_id) if t.context_id else None
            if ctx is not None and _dono(ctx) != usuario:
                continue
            if ctx is None and usuario != "matheus":
                continue
            estado = getattr(t.state, "value", str(t.state))
            prox = ""
            if isinstance(t, ScheduledTask) and estado != "disabled":
                nxt = t.get_next_run()
                prox = f", próxima {_hora(nxt)}" if nxt else ""
            fim = ""
            if lim and isinstance(t, ScheduledTask):
                reg = dados.get(t.uuid, {})
                if reg.get("ate"):
                    fim = f", termina {datetime.fromtimestamp(reg['ate'], FUSO):%d/%m}"
            rotulo = {"idle": "ativa", "running": "rodando", "disabled": "pausada", "error": "com erro"}.get(estado, estado)
            tarefas.append(f"• {t.name} — {rotulo}{prox}{fim}")
    except Exception as exc:
        tarefas.append(f"(não consegui ler: {str(exc)[:80]})")
    saida.append("📅 *Tarefas agendadas*\n" + ("\n".join(tarefas) if tarefas else "Nenhuma."))

    ultimas = []
    try:
        linhas = Path(f"/a0/usr/aprovacoes/atividade/{usuario}.jsonl").read_text(encoding="utf-8").splitlines()[-5:]
        for linha in reversed(linhas):
            a = json.loads(linha)
            quando = datetime.fromtimestamp(a["em"], FUSO).strftime("%d/%m %H:%M")
            ultimas.append(f"• {quando} — {a.get('resumo')} ({a.get('decisao')})")
    except Exception:
        pass
    saida.append("📝 *Últimas ações importantes*\n" + ("\n".join(ultimas) if ultimas else "Nenhuma registrada."))
    return "\n\n".join(saida)


class Painel(ApiHandler):
    @classmethod
    def requires_auth(cls) -> bool:
        return False

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def requires_api_key(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            ok = secrets.compare_digest(request.headers.get("X-Chave", ""), CHAVE.read_text().strip())
        except OSError:
            ok = False
        if not ok:
            return Response('{"erro": "sem acesso"}', status=403, mimetype="application/json")
        usuario = str(input.get("usuario") or "").lower()
        return {"ok": True, "texto": painel(usuario)}

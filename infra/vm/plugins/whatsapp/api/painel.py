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


def _helper(nome: str, caminho: str):
    """A plugin helper shared with the plugin's own code through sys.modules, loaded here by path when missing and
    again when its file changed (12/10: after a deploy the panel kept the old prospecting code, without `painel`, until
    a tool reloaded it). A module loaded without the `_mtime` mark is kept as is. None when the plugin is not
    installed."""
    import importlib.util

    arquivo = Path(caminho)
    antigo = sys.modules.get(nome)
    if not arquivo.exists():
        return antigo
    if antigo is not None and getattr(antigo, "_mtime", arquivo.stat().st_mtime) == arquivo.stat().st_mtime:
        return antigo
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    modulo._mtime = arquivo.stat().st_mtime
    sys.modules[nome] = modulo
    return modulo


def lista_esperando(aprovacoes: list, pedido: dict | None, propostas: int, contas: list, rascunhos: int,
                    fios: list) -> list[str]:
    """/pendentes and the panel (12/10 review §7 item 2): the one list of what waits on the person."""
    linhas = [f"• Aprovar: {a['resumo']} ({a['conversa']})" for a in aprovacoes]
    if pedido and not pedido.get("codigo"):
        linhas.append(f"• Código pedido: {pedido.get('motivo') or pedido.get('servico') or 'verificação'}")
    if propostas:
        linhas.append(f"• Prospecção: {propostas} proposta(s) esperando o seu ✅ (os botões estão na mensagem de cada uma)")
    linhas += [f"• Conta: {c}" for c in contas]
    if rascunhos:
        linhas.append(f"• {rascunhos} resposta(s) de e-mail pronta(s) esperando você usar ou descartar")
    linhas += [f"• Fio solto: {f}" for f in fios]
    return linhas


def esperando(usuario: str) -> tuple[list[str], list]:
    """What waits on the person right now, plus the buttons of the first approval (to answer from /pendentes)."""
    from agent import AgentContext

    aprovacoes, botoes = [], []
    rev = sys.modules.get("aprovacoes_revisor")
    for cid, p in list((getattr(rev, "PENDENTES", {}) or {}).items()):
        ctx = AgentContext.get(cid)
        if p.get("decisao") is None and ctx is not None and _dono(ctx) == usuario:
            aprovacoes.append({"resumo": p.get("resumo"), "conversa": ctx.name or cid})
            if not botoes:
                botoes = [{"id": f"aprov:{cid}:{p['id']}:{d}", "titulo": t}
                          for d, t in (("aprovar", "Aprovar"), ("sempre", "Sempre permitir"), ("recusar", "Recusar"))]
    pedido = (getattr(sys.modules.get("whatsapp_ponte"), "PEDIDOS", {}) or {}).get(usuario)
    propostas, contas, rascunhos, fios = 0, [], 0, []
    try:
        pr = _helper("prospeccao_helper", "/a0/usr/plugins/prospeccao/helpers/prospeccao.py")
        propostas = sum(1 for a in pr.carregar(usuario)["acoes"] if a["estado"] == "proposta") if pr else 0
    except Exception:
        pass
    try:
        aux = _helper("auxiliar_helper", "/a0/usr/plugins/auxiliar/helpers/auxiliar.py")
        if aux:
            contas = [aux.linha_conta(c) for c in aux.contas_abertas(usuario, 7)[:5]]
            rascunhos = sum(1 for r in aux.carregar(usuario)["rascunhos"] if r.get("estado") == "pendente")
    except Exception:
        pass
    try:
        fi = _helper("fios_soltos_helper", "/a0/usr/plugins/fios_soltos/helpers/fios.py")
        fios = [str(f.get("titulo", ""))[:120] + (f" (prazo {f['prazo']})" if f.get("prazo") else "")
                for f in (fi.abertos(usuario, 3) if fi else [])]
    except Exception:
        pass
    return lista_esperando(aprovacoes, pedido, propostas, contas, rascunhos, fios), botoes


def linhas_rotinas(tarefas: list, mostrar: int = 6) -> str:
    """The panel's routines (12/10 review §7 item 11: one screen): the ones with an error or running always, then
    the next `mostrar` to run; the rest only counted. `tarefas`: {"linha", "estado", "quando" (next run or None)}."""
    if not tarefas:
        return "Nenhuma."
    primeiro = [t for t in tarefas if t["estado"] in ("error", "running")]
    proximas = sorted((t for t in tarefas if t not in primeiro and t["quando"]), key=lambda t: t["quando"])[:mostrar]
    resto = [t for t in tarefas if t not in primeiro and t not in proximas]
    ativas = sum(1 for t in resto if t["estado"] != "disabled")
    pausadas = len(resto) - ativas
    fim = " · ".join(x for x in (f"+{ativas} ativa(s)" if ativas else "", f"{pausadas} pausada(s)" if pausadas else "") if x)
    return "\n".join([t["linha"] for t in primeiro + proximas] + ([fim] if fim else []))


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

    linhas, _ = esperando(usuario)
    saida.append("⏳ *Esperando você*\n" + ("\n".join(linhas) if linhas else "Nada."))

    try:  # 12/10 review §7 item 11: funnel and stock straight from the register
        pr = _helper("prospeccao_helper", "/a0/usr/plugins/prospeccao/helpers/prospeccao.py")
        bloco = pr.painel(usuario) if pr and hasattr(pr, "painel") else ""
    except Exception as exc:
        bloco = f"(não consegui ler: {str(exc)[:80]})"
    if bloco:
        saida.append("🎯 *Prospecção*\n" + bloco)

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
            prox, nxt = "", None
            if isinstance(t, ScheduledTask) and estado != "disabled":
                nxt = t.get_next_run()
                prox = f", próxima {_hora(nxt)}" if nxt else ""
            fim = ""
            if lim and isinstance(t, ScheduledTask):
                reg = dados.get(t.uuid, {})
                if reg.get("ate"):
                    fim = f", termina {datetime.fromtimestamp(reg['ate'], FUSO):%d/%m}"
            rotulo = {"idle": "ativa", "running": "rodando", "disabled": "pausada", "error": "com erro"}.get(estado, estado)
            quando = nxt.timestamp() if nxt else None
            tarefas.append({"linha": f"• {t.name} — {rotulo}{prox}{fim}", "estado": estado, "quando": quando})
    except Exception as exc:
        tarefas.append({"linha": f"(não consegui ler: {str(exc)[:80]})", "estado": "error", "quando": None})
    saida.append("📅 *Rotinas*\n" + linhas_rotinas(tarefas))

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

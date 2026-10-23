"""Subagentes em segundo plano pela ponte do celular (23/10, Matheus: "Quero saber tbm se o paralelismo ta funcionando").

O `delegate_task` do Hermes sempre dispara os subagentes em segundo plano (em paralelo, até
delegation.max_concurrent_children). Numa sessão do API server (a ponte), o resultado só fica guardado para o PRÓXIMO
turno da sessão ("no model wake"): ao vivo, a pessoa recebeu "assim que terminarem eu mando os horários" e nada chegou
até ela escrever de novo. Aqui, num gancho `post_tool_call`: o disparo de uma sessão de pessoa (não de rotina, que o
Hermes já roda na hora) é seguido numa thread; quando o lote termina, a ponte recebe um pedido NA MESMA SESSÃO
(/conversa com "sessao"), o turno novo lê o resultado guardado e a resposta vai ao celular como qualquer outra.
"""
import json
import logging
import re
import sys
import threading
import time

log = logging.getLogger("agentepessoal.subagentes")
ROTINA = re.compile(r"^cron_[A-Za-z0-9]+_\d{8}_\d{6}$")
ESPERA_MAX = 3 * 3600
PAUSA = 5.0
AVISO = ("[Aviso automático: os subagentes que você disparou ({id}) terminaram. Use o resultado deles e responda a "
         "pessoa com o que ela pediu; não dispare de novo.]")
_seguindo: set = set()
_trava = threading.Lock()


def estado(delegation_id: str) -> dict | None:
    from tools import async_delegation  # o registro durável do próprio Hermes

    return async_delegation.get_durable_delegation(delegation_id)


def terminou(rec: dict | None) -> bool:
    return bool(rec) and (bool(rec.get("completed_at")) or str(rec.get("state") or "") in
                          ("completed", "error", "failed", "cancelled", "interrupted", "timeout", "stalled"))


def avisar(login: str, sessao: str, texto: str) -> None:
    botoes = sys.modules["agentepessoal_botoes"]
    try:
        r = botoes.conversa(login, texto, sessao=sessao)
        if r.get("ok"):
            return
        erro = r
    except Exception as exc:
        erro = f"{type(exc).__name__}: {exc}"
    log.warning("subagentes: aviso de %s para %s não saiu (%s)", sessao, login, str(erro)[:200])


def seguir(delegation_id: str, login: str, sessao: str, dormir=time.sleep, agora=time.time, estado_fn=None,
           avisar_fn=None) -> str:
    """Espera o lote terminar e acorda a sessão. Devolve "avisado", "tempo esgotado" ou "sumiu"."""
    estado_fn, avisar_fn = estado_fn or estado, avisar_fn or avisar
    fim = agora() + ESPERA_MAX
    try:
        while agora() < fim:
            try:
                rec = estado_fn(delegation_id)
            except Exception as exc:
                log.warning("subagentes: %s não lido: %s", delegation_id, exc)
                rec = {}
            if rec is None:
                return "sumiu"
            if terminou(rec):
                if str(rec.get("delivery_state") or "") == "delivered":
                    return "já entregue"  # a pessoa escreveu antes e o turno dela já leu o resultado
                avisar_fn(login, sessao, AVISO.format(id=delegation_id))
                return "avisado"
            dormir(PAUSA)
        return "tempo esgotado"
    finally:
        with _trava:
            _seguindo.discard(delegation_id)


def depois(tool_name="", args=None, result=None, session_id="", task_id="", **kw):
    """Gancho `post_tool_call`: um delegate_task que voltou "dispatched" numa conversa de pessoa é seguido."""
    if tool_name != "delegate_task" or not isinstance(result, str):
        return None
    sessao = str(session_id or task_id or "")
    if not sessao or ROTINA.match(sessao):
        return None
    try:
        dados = json.loads(result)
    except ValueError:
        return None
    if not isinstance(dados, dict) or dados.get("status") != "dispatched" or not dados.get("delegation_id"):
        return None
    login = sys.modules["agentepessoal_ponte_a0"].login_da_sessao(sessao)
    did = str(dados["delegation_id"])
    with _trava:
        if did in _seguindo:
            return None
        _seguindo.add(did)
    threading.Thread(target=seguir, args=(did, login, sessao), daemon=True, name=f"subagentes-{did[-8:]}").start()
    return None


def registrar(ctx) -> None:
    ctx.register_hook("post_tool_call", depois)

"""Quem fez cada chamada de modelo do Hermes (migração, fase 2), para o registro de uso do proxy (uso.jsonl, `/gasto`,
teto dos convidados): o middleware `llm_request` põe nos cabeçalhos da chamada o dono da conversa (X-A0-Dono), a
sessão (X-A0-Conversa) e, numa rodada do cron, o id da rotina (X-A0-Rotina). Só ids, nunca conteúdo; o proxy grava e
não manda para a AWS (bedrock_proxy.HOP_HEADERS). As chamadas internas do Hermes (compressão, título) não passam por
aqui: o proxy as marca como origem "hermes" pelo caminho (/hermes/bedrock) e mascara o cofre nelas também."""
import re
import sys

_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_LOGIN = re.compile(r"[a-z0-9_-]{1,32}")
_CRON = re.compile(r"cron_([A-Za-z0-9]{1,64})_\d{8}_\d{6}")
# Só nos SDKs que aceitam `extra_headers` (Anthropic e OpenAI); no Converse do boto3 o campo quebraria a chamada.
MODOS = frozenset({"anthropic_messages", "chat_completions", "codex_responses"})


def cabecalhos(sessao: str) -> dict:
    ponte = sys.modules["agentepessoal_ponte_a0"]
    sessao = str(sessao or "")
    saida = {}
    login = ponte.login_da_sessao(sessao) if sessao else ""
    if _LOGIN.fullmatch(login or ""):
        saida["X-A0-Dono"] = login
    if _ID.fullmatch(sessao):
        saida["X-A0-Conversa"] = sessao
    rotina = _CRON.fullmatch(sessao)
    if rotina:
        saida["X-A0-Rotina"] = rotina.group(1)
    return saida


def pedido_com_dono(request=None, session_id="", task_id="", api_mode="", **kw):
    """Middleware `llm_request`."""
    if not isinstance(request, dict) or api_mode not in MODOS:
        return None
    extra = cabecalhos(session_id or task_id)
    if not extra:
        return None
    novo = dict(request)
    novo["extra_headers"] = {**(request.get("extra_headers") or {}), **extra}
    return {"request": novo, "source": "agentepessoal", "reason": "uso: dono da chamada"}


def registrar(ctx) -> None:
    ctx.register_middleware("llm_request", pedido_com_dono)

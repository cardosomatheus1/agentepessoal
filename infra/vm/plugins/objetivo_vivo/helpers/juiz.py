"""Item 10 of docs/AUDITORIA_MATURIDADE_AGENTE.md: an independent judge of "done" (Hermes hermes_cli/goals.py, OpenClaw
"Final claim needs evidence"). Before the final answer of a request with real work, a cheap model compares his request
with the steps the tools show and the answer; when something that could be done is missing, or the answer claims
what the steps do not show, the answer does not go out and the agent continues (at most VEZES times per request; on
any failure of the judge the answer goes out as before).

21/10: the agent said the Outlook draft was addressed to Matheus and it was empty; it said an attachment was refused
and it had tried the OneDrive field; it stopped to ask what it could decide."""

import json
import re

VEZES = 2  # rejections per request; then the answer goes out
PASSOS_MIN = 3  # tool steps since his message before the judge looks
PROVAS_MAX = 25
PROVA_MAX = 320
CHAVE = "_juiz_do_pronto"  # context data: {"msg_id": str, "vezes": int}
TIPOS = {"tool", "code_exe", "browser", "mcp", "warning", "error"}

SISTEMA = """Você confere se um agente terminou o pedido de uma pessoa antes de ele responder. Recebe o pedido, os \
passos que as ferramentas mostram (as provas: um resumo curto e cortado de cada passo) e a resposta final que ele quer \
mandar. Responda só um JSON: {"pronto": true ou false, "falta": "o que falta, em uma frase curta (vazio se pronto)"}.
Barre (pronto = false) só quando houver falha CLARA, de um destes tipos:
1. a resposta diz que o resultado final aconteceu (enviado, salvo, publicado, cadastrado) e NENHUM passo mostra essa \
ação nem uma conferência dela;
2. uma parte importante do pedido claramente não foi feita, e o agente podia fazê-la sozinho;
3. o agente para para perguntar ou pedir uma decisão que ele mesmo podia tomar, ou desiste depois de tentar um caminho só;
4. a resposta promete fazer depois ("vou fazer", "em seguida") o que devia estar feito agora.
Nos outros casos, pronto = true. Não exija prova de cada detalhe (tamanho, texto do corpo, cada campo): as provas são \
resumidas, e só mostram o que foi feito depois da última mensagem da pessoa: partes do pedido feitas antes \
(arquivo preparado, revisão, conversa anterior) não aparecem e não são motivo para barrar. Pedir à pessoa o que só ela pode dar (senha, código, captcha, aprovação, pagamento, uma decisão dela) é \
pronto = true, assim como dizer com honestidade o que falhou depois de tentar caminhos diferentes."""


def _curto(texto, limite: int) -> str:
    t = " ".join(str(texto or "").split())
    return t if len(t) <= limite else t[: limite - 1] + "…"


def provas(itens) -> list[str]:
    """The tool steps since the person's last message, from the chat log (objects with .type, .heading, .content,
    .kvps), oldest first."""
    itens = list(itens or [])
    ultimo = max((i for i, x in enumerate(itens) if getattr(x, "type", "") == "user"), default=-1)
    saida = []
    for x in itens[ultimo + 1:]:
        if getattr(x, "type", "") not in TIPOS:
            continue
        kv = getattr(x, "kvps", None) or {}
        args = kv.get("tool_args") if isinstance(kv, dict) else None
        args = {k: v for k, v in (args or {}).items() if k not in ("thoughts", "headline")} if isinstance(args, dict) else {}
        cabeca = _curto(getattr(x, "heading", ""), 80)
        saida.append(_curto(f"[{x.type}] {cabeca} {json.dumps(args, ensure_ascii=False)[:160] if args else ''} → "
                            f"{getattr(x, 'content', '')}", PROVA_MAX))
    return saida[-PROVAS_MAX:]


def entrada(pedido: str, passos: list[str], resposta: str) -> str:
    linhas = "\n".join(f"{n}. {p}" for n, p in enumerate(passos, 1)) or "(nenhum)"
    return (f"PEDIDO DA PESSOA:\n{_curto(pedido, 1500)}\n\nPROVAS (passos das ferramentas, do mais antigo ao mais "
            f"novo):\n{linhas}\n\nRESPOSTA QUE O AGENTE QUER MANDAR:\n{_curto(resposta, 2500)}")


def veredito(texto) -> dict | None:
    """{"pronto": bool, "falta": str} from the judge's answer; None when unreadable (the answer then goes out)."""
    m = re.search(r"\{.*\}", str(texto or ""), re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("pronto"), bool):
        return None
    return {"pronto": d["pronto"], "falta": _curto(d.get("falta") or "", 300)}


def deve_julgar(estado: dict | None, passos: list[str], registro: dict | None) -> bool:
    """A request with a goal, real work (PASSOS_MIN tool steps) and judge rounds left for it."""
    if not isinstance(estado, dict) or not str(estado.get("pedido") or "").strip():
        return False
    if sum(1 for p in passos if not p.startswith(("[warning]", "[error]"))) < PASSOS_MIN:
        return False
    reg = registro if isinstance(registro, dict) else {}
    return not (reg.get("msg_id") == estado.get("msg_id") and int(reg.get("vezes") or 0) >= VEZES)


def contar(estado: dict, registro: dict | None) -> dict:
    reg = registro if isinstance(registro, dict) and registro.get("msg_id") == estado.get("msg_id") else {}
    return {"msg_id": estado.get("msg_id"), "vezes": int(reg.get("vezes") or 0) + 1}


def recado(falta: str) -> str:
    return ("⚖️ Conferência antes de responder: a resposta NÃO foi enviada, a tarefa ainda não está pronta. Falta: "
            f"{falta or 'cumprir o pedido inteiro'}. Continue e faça isso agora (tente outro caminho se o anterior "
            "falhou). Se for mesmo impossível, responda dizendo o que tentou, o que conseguiu e o que falta. Não mande "
            "a mesma resposta de novo.")

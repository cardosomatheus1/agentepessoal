"""Finer guards on the agent's steps (ideas from Hermes agent/tool_guardrails and iteration_budget).

The loop detector (tool_execute_after/_10_detector_loop.py) only catches the same action with the same result. It
missed two cases seen in practice:
- the same tool failing again and again with different arguments (a new selector, a new path each time);
- a helper (subordinate) working for 175 steps with no answer.

Here, as plain functions (tested in tests/suite.py):
- falhou(): the tool's answer is an error;
- Falhas: 3 failures in a row of the same tool give the agent a warning to change approach (the task goes on);
- teto(): step cap of a helper (A1+); A0 has none, helpers of a prospecting round get a high one;
- Resultados: a result identical to an earlier one of the same task (512+ characters) goes to the history as "igual
  ao resultado do passo N". Only the NEW history item changes, never an earlier one, so every prompt still starts
  with the whole previous prompt and the provider cache keeps working (see cache_prompt).
"""

import hashlib
import json
import math
import re

IGNORAR = {"response", "wait"}

# --- failures -------------------------------------------------------------------------------------------------------

FALHAS_AVISO = 3
# Agent Zero tools answer errors as text: "Error: …", "Browser click failed: …", "error reading <path>: …",
# "MCP … ERROR: …", "Tool 'x' not found", "A2A chat error: …", "Task failed to update: …"
ERRO = re.compile(
    r"^\s*(?:error\b|erro\b|exception\b|traceback\b|\[?error\]?:|"
    r"[\w .'\"-]{0,40}?\b(?:failed|error|exception)\b\s*:|"
    r"tool '[^']*' not found|task not found|task failed)", re.I)
CABECALHO = "⟦DADO EXTERNO"  # aprovacoes marks third-party text before this runs


def falhou(tool: str, mensagem: str) -> bool:
    """The tool's answer is an error message (not a command that printed the word "error" somewhere)."""
    if (tool or "") in IGNORAR or not isinstance(mensagem, str):
        return False
    texto = mensagem
    if texto.startswith(CABECALHO):
        texto = texto.split("⟧", 1)[-1]
    return bool(ERRO.match(texto[:400]))


def aviso_falhas(tool: str, n: int) -> str:
    return (f"\n\n⚠️ `{tool}` falhou {n} vezes seguidas, com argumentos diferentes. Tentar mais uma variação do mesmo "
            "jeito não deve resolver. Leia o erro acima, confira o que você está assumindo (página, caminho, nome, "
            "formato) e mude de abordagem: outra ferramenta, outro caminho ou um diagnóstico pequeno antes. Se o "
            "bloqueio for externo, diga ao usuário o que travou em vez de insistir.")


class Falhas:
    """Failures in a row per tool, kept in the agent's data (a dict tool -> count). A success of the tool clears it."""

    def __init__(self, contagem: dict | None):
        self.contagem = dict(contagem or {})

    def registrar(self, tool: str, falha: bool) -> int:
        """The tool's failures in a row after this call (0 on success)."""
        if not falha:
            self.contagem.pop(tool, None)
            return 0
        self.contagem[tool] = self.contagem.get(tool, 0) + 1
        return self.contagem[tool]


# --- step cap for helpers -------------------------------------------------------------------------------------------

TETO_AJUDANTE = 40
TETO_PROSPECCAO = 150  # helpers of a prospecting round browse a lot on purpose
AVISO_FRACAO = 0.8
PROSPECCAO = re.compile(r"prospec", re.I)


def teto(numero: int, nomes_raiz: list[str] | tuple = ()) -> int:
    """Step cap of an agent: 0 = none. The main agent (A0) has none; a helper (A1, A2…) of a prospecting round gets a
    high one; any other helper TETO_AJUDANTE."""
    if not numero:
        return 0
    if any(PROSPECCAO.search(n or "") for n in nomes_raiz):
        return TETO_PROSPECCAO
    return TETO_AJUDANTE


def passo_do_aviso(limite: int) -> int:
    return math.ceil(limite * AVISO_FRACAO) if limite else 0


def aviso_passos(passo: int, limite: int) -> str:
    return (f"\n\n⏳ Passo {passo} de no máximo {limite} para você, que é um ajudante. Pare de abrir coisas novas: "
            f"junte o que já tem e devolva o resultado agora com `response` (diga o que faltou). No passo {limite} "
            "você será parado e o que tiver feito vai para quem te chamou.")


def parada_passos(quem: str, limite: int, tool: str, resultado: str) -> str:
    """What the helper hands back to its superior when it hits the cap."""
    resultado = (resultado or "").strip()
    if len(resultado) > 2000:
        resultado = resultado[:2000] + " […]"
    return (f"⛔ O ajudante {quem} foi parado no teto de {limite} passos sem entregar a resposta final. Use o que ele já "
            "achou (último resultado abaixo e o histórico dele) ou siga você mesmo por outro caminho; não chame outro "
            f"ajudante para a mesma coisa.\n\nÚltima ferramenta: `{tool}`. Último resultado:\n{resultado}")


# --- delegations without talking to the person ----------------------------------------------------------------------
# 18/10: the main agent chained ~33 helper calls over 4 h (06:54-09:28 and 09:30-11:25) without one answer or
# notify_user; Matheus asked "Continua…?" four times and then "Oq ta fazendo?". A helper kept answering "não é conclusão
# global" and was simply sent again. Only the main agent (A0) is counted; a warning, the task goes on.

DELEGACOES_AVISO = 3
CONTATO = {"response", "notify_user"}


def delegou(tool: str, args) -> bool:
    """The step hands work to a helper: call_subordinate, or a parallel that starts at least one."""
    if tool == "call_subordinate":
        return True
    if tool != "parallel":
        return False
    try:
        texto = json.dumps(args or {}, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        texto = str(args)
    return "call_subordinate" in texto


class Delegacoes:
    """Helper calls of the main agent since it last spoke to the person (response or notify_user)."""

    def __init__(self, n):
        try:
            self.n = max(0, int(n or 0))
        except (TypeError, ValueError):
            self.n = 0

    def registrar(self, tool: str, args) -> int:
        if tool in CONTATO:
            self.n = 0
        elif delegou(tool, args):
            self.n += 1
        return self.n


def aviso_delegacoes(n: int) -> str:
    return (f"\n\n⚠️ Delegação nº {n} seguida sem falar com a pessoa. Se esta conversa tem alguém esperando (não é "
            "tarefa agendada): antes de delegar de novo, responda a qualquer mensagem nova dela e mande `notify_user` "
            "curto com o que já está pronto, o que falta e o próximo passo. Se o ajudante devolveu resultado parcial "
            "outra vez, não relance a mesma tarefa: entregue o que há e diga o que falta.")


# --- identical results ----------------------------------------------------------------------------------------------

REPETIDO_MIN = 512
ARGS_PREVIA = 120
# notices this plugin appends to a result: they stay visible after the stub (the result itself is what repeats)
AVISOS = ("\n\n⚠️ ATENÇÃO:", "\n\n⛔ LOOP:", "\n\n↻ A página mudou", "\n\n⏳ Passo ", "\n\n⚠️ `", "\n\n⚠️ Delegação nº ")


def separar(texto: str) -> tuple[str, str]:
    """(result, notices appended by this plugin)."""
    corte = min((i for i in (texto.find(a) for a in AVISOS) if i >= 0), default=-1)
    return (texto, "") if corte < 0 else (texto[:corte], texto[corte:])


def chave(conteudo: str) -> str:
    return hashlib.sha1(conteudo.strip().encode("utf-8", "ignore")).hexdigest()


def previa_args(args) -> str:
    try:
        texto = json.dumps(args or {}, sort_keys=True, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        texto = str(args)
    return texto if len(texto) <= ARGS_PREVIA else texto[:ARGS_PREVIA] + "…"


def stub(passo_antes: int, passo_agora: int, tool: str, args) -> str:
    atras = passo_agora - passo_antes
    quando = f"{atras} passo{'s' if atras != 1 else ''} atrás" if atras > 0 else "nesta tarefa"
    return (f"[igual ao resultado do passo {passo_antes} ({quando}): `{tool}` {previa_args(args)} devolveu exatamente o "
            "mesmo texto de antes, então ele não foi repetido aqui. Nada mudou; use aquele resultado.]")


class Resultados:
    """Results seen in the current task of one agent: key -> {"passo", "tool", "msg"}. `visivel(msg)` says the earlier
    copy is still whole in the history (not summarized away), so the stub never points at something gone."""

    def __init__(self, vistos: dict | None):
        self.vistos = vistos if vistos is not None else {}

    def trocar(self, tool: str, texto: str, args, passo: int, visivel) -> tuple[str, str]:
        """(text to keep in the history, key of this result or "" when it is not tracked)."""
        if tool in IGNORAR or not isinstance(texto, str):
            return texto, ""
        conteudo, avisos = separar(texto)
        if len(conteudo.strip()) < REPETIDO_MIN or falhou(tool, conteudo):
            return texto, ""
        k = chave(conteudo)
        antes = self.vistos.get(k)
        if antes and visivel(antes.get("msg")):
            return stub(antes["passo"], passo, tool, args) + avisos, ""
        self.vistos[k] = {"passo": passo, "tool": tool, "msg": None}
        return texto, k

    def guardar(self, k: str, msg) -> None:
        if k and k in self.vistos:
            self.vistos[k]["msg"] = msg


def visivel_no_historico(history, msg) -> bool:
    """The message is still in the history as itself: current topic, or an older topic not yet summarized, and not
    compressed on its own (large messages get a summary in place)."""
    if msg is None or getattr(msg, "summary", ""):
        return False
    topicos = [getattr(history, "current", None), *(getattr(history, "topics", None) or [])]
    for t in topicos:
        if t is None or getattr(t, "summary", ""):
            continue
        if any(m is msg for m in getattr(t, "messages", None) or []):
            return True
    return False

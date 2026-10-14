"""Is a phone message that arrives while the main chat works a complement of the running request, or a new one?

14/10: "Quero que vc acesse meu gov, procure minhas empresas, mei e veja as dividas" was running when, 30 s later,
"As dividas sao de das n pago (...)" arrived. Not a correction word, so it opened a parallel chat: two chats did the
same gov.br task, each in its own tab, and told Matheus contradicting things ("o login não avançou" in one tab while
the other was already logged in). A complement belongs to the running request, as an intervention; only a request
that stands on its own goes to a parallel chat ("Quanto é 17 vezes 3?" while a long task runs).

A small model decides (it reads meaning, not keywords); without an answer the caller falls back to timing.
"""

import json
import re
import urllib.request

URL = "http://host.docker.internal:8787/openai/v1/responses"
MODELO = "openai.gpt-6-luna"
ESPERA_S = 8  # the person is waiting on the phone; past this, timing decides


def _chamar(pedido: str) -> str:
    body = {"model": MODELO, "reasoning": {"effort": "low"}, "input": [{"role": "user", "content": pedido}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=ESPERA_S) as r:
        data = json.loads(r.read())
    return "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []) if c.get("type") == "output_text")


def pergunta(em_andamento: str, historico: str, nova: str) -> str:
    return f"""Uma pessoa conversa com um assistente pelo celular. O assistente está no meio de uma tarefa e chegou uma
mensagem nova dela. Decida se a mensagem nova é COMPLEMENTO da tarefa em andamento (detalhe, explicação, correção,
dado que faltava, pedido de pressa ou de mudança na mesma tarefa, resposta a uma pergunta do assistente) ou um
PEDIDO NOVO, que se resolve sozinho, sem a tarefa em andamento.

Tarefa em andamento (o último pedido dela): «{em_andamento[:600]}»
Últimas mensagens da conversa:
{historico[-1500:] or "(nenhuma)"}

Mensagem nova: «{nova[:800]}»

Na dúvida, é complemento (um pedido novo misturado na tarefa ainda é atendido; uma tarefa duplicada em outra
conversa confunde a pessoa). Responda só JSON: {{"complemento": true}} ou {{"complemento": false}}"""


def e_complemento(em_andamento: str, historico: str, nova: str, chamar=_chamar):
    """True/False from the model; None when it did not answer (timeout, error, unreadable reply)."""
    try:
        texto = chamar(pergunta(em_andamento or "", historico or "", nova or ""))
    except Exception:
        return None
    achado = re.search(r"\{.*?\}", texto or "", re.S)
    if not achado:
        return None
    try:
        valor = json.loads(achado.group(0)).get("complemento")
    except (ValueError, AttributeError):
        return None
    return valor if isinstance(valor, bool) else None

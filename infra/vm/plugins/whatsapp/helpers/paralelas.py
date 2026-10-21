"""What the person said in a parallel phone chat, handed to the main chat with his next message there.

A parallel chat gets the main chat's last messages (api/receber.py), but nothing came back the other way. In the
audit of 12-19/10, a detail he corrected while the main chat was busy (an e-mail with one digit too many) was typed
wrong again later in the main chat ("De novo vc colocou email errado"). Now his next message to the main chat carries
the last exchanges of the parallel chats that moved since the main chat last heard from him, once.
Plain functions, tested in tests/suite.py.
"""

import re

VISTAS = "whatsapp_paralelas_vistas"  # main chat data: parallel activity up to this time was already handed over
CABECALHO = "[Pedido feito pelo celular enquanto"
MAX_TROCAS = 4
CORTE = 300
# 21/10: with no mark yet in the main chat, one forward carried weeks-old parallel chats (gov.br, airsoft) before his
# "Sim": only chats that moved in the last hours count, and Agent Zero's opening greeting is not an exchange
JANELA = 6 * 3600
SAUDACAO = re.compile(r"^\W*hello\W+.{0,6}i'?m\W+\**agent zero", re.I)


def _texto_dele(texto: str) -> str:
    """His own words in a parallel chat (without the header that repeats the main chat's context)."""
    if texto.startswith(CABECALHO) and "\nPedido:\n" in texto:
        return texto.split("\nPedido:\n", 1)[1]
    return texto


def trocas(logs, n: int = MAX_TROCAS, corte: int = CORTE) -> list[str]:
    """The last n person/agent lines of a chat's log items (objects with .type and .content)."""
    linhas = []
    for item in logs or []:
        tipo = getattr(item, "type", "")
        if tipo not in ("user", "response"):
            continue
        texto = str(getattr(item, "content", "") or "")
        if tipo == "user":
            texto = _texto_dele(texto)
        texto = " ".join(texto.split())
        if texto and not (tipo == "response" and SAUDACAO.match(texto)):
            linhas.append(("Ele: " if tipo == "user" else "Você: ") + texto[:corte])
    return linhas[-n:]


def resumo(principal, paralelas, logs_de, agora: float) -> str:
    """Text to put before his message in the main chat ("" when no parallel chat moved since the main one last heard
    from him). Marks what was handed over, so it goes only once."""
    desde = max(float(principal.get_data(VISTAS) or 0), float(principal.get_data("whatsapp_ultima_entrada") or 0),
                agora - JANELA)
    blocos = []
    for p in paralelas or []:
        if p is principal or float(p.get_data("whatsapp_ultima_entrada") or 0) <= desde:
            continue
        linhas = trocas(logs_de(p))
        if linhas:
            blocos.append("\n".join(linhas))
    principal.set_data(VISTAS, agora)
    if not blocos:
        return ""
    return ("[Enquanto esta conversa estava ocupada, ele falou com você numa conversa paralela do celular. Últimas "
            "mensagens de lá:\n" + "\n---\n".join(blocos) +
            "\nSe ali ele corrigiu um dado (e-mail, nome, número) ou decidiu algo, isso vale também aqui.]\n\n")

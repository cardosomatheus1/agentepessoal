"""Chats idle for DIAS days are archived (copied to /a0/usr/chats_arquivo, then removed from the agent): a chat that
loaded a skill keeps the old text, and 183 chats piled up in 5 days (Matheus, 13/10: archive, never delete).
Never archived: the phone and trigger chats (found by their data key), the scheduled rounds' chats, a chat that has
a task, and a chat that is running."""

import time

DIAS = 7
NUNCA = ("whatsapp_de", "gatilhos_de")


def escolher(itens: list[dict], agora: float | None = None, dias: int = DIAS) -> list[str]:
    """itens: {"id", "mtime" (last write of chat.json), "data" (the chat's data), "tem_tarefa", "rodando"}."""
    agora = agora or time.time()
    out = []
    for i in itens:
        if agora - float(i.get("mtime") or agora) < dias * 86400:
            continue
        if i.get("tem_tarefa") or i.get("rodando"):
            continue
        if any((i.get("data") or {}).get(k) for k in NUNCA):
            continue
        out.append(i["id"])
    return out

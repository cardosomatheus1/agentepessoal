"""Channels (22/10, from Claude Duet: "start separate channels for different topics; they share the same memory"; a new
channel asks "What should Claude know about this channel?" and suggests tasks it can do there). A channel is an
ordinary chat of the agent with a name and a purpose: the purpose goes into that chat's instructions every turn
(extensions/python/system_prompt/_29_canal.py), the memory is the person's, as in any chat. The register
(/a0/usr/canais/<login>.json) only lists them: id, name, purpose, the chat that holds it."""

import json
import os
import re
import time
import uuid
from pathlib import Path

PASTA = Path(os.environ.get("CANAIS_PASTA", "/a0/usr/canais"))
MAX_CANAIS = 20
CHAVE = "canal"  # chat data: {"id", "nome", "proposito"} (saved with the chat)


def _login(login: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "", (login or "").lower()) or "matheus"


def _arq(login: str) -> Path:
    return PASTA / f"{_login(login)}.json"


def _txt(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def listar(login: str) -> list:
    try:
        d = json.loads(_arq(login).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return d if isinstance(d, list) else []


def _gravar(login: str, lista: list) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    tmp = _arq(login).with_suffix(f".{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _arq(login))


def novo(login: str, nome: str, proposito: str, conversa: str = "", agora: float | None = None) -> dict:
    nome = _txt(nome, 40).lstrip("#").strip()
    proposito = _txt(proposito, 600)
    if len(nome) < 2 or len(proposito) < 10:
        return {"ok": False, "erro": "diga o nome do canal e o propósito (o que o agente deve saber sobre este assunto)"}
    lista = listar(login)
    if any(c["nome"].lower() == nome.lower() for c in lista):
        return {"ok": False, "erro": f"já existe o canal #{nome}"}
    if len(lista) >= MAX_CANAIS:
        return {"ok": False, "erro": f"já há {MAX_CANAIS} canais"}
    canal = {"id": uuid.uuid4().hex[:8], "nome": nome, "proposito": proposito, "conversa": conversa,
             "criado": agora or time.time()}
    _gravar(login, lista + [canal])
    return {"ok": True, "canal": canal}


def atualizar(login: str, cid: str, **campos) -> dict | None:
    lista = listar(login)
    canal = next((c for c in lista if c["id"] == cid), None)
    if not canal:
        return None
    if "proposito" in campos and _txt(campos["proposito"], 600):
        canal["proposito"] = _txt(campos["proposito"], 600)
    if campos.get("conversa"):
        canal["conversa"] = str(campos["conversa"])
    _gravar(login, lista)
    return canal


def instrucao(canal: dict) -> str:
    """What goes into the channel chat's instructions every turn."""
    return (f"## Canal #{canal['nome']}\n"
            f"Esta conversa é o canal #{canal['nome']}. Propósito (o que ele quer que você saiba sobre este assunto): "
            f"{canal['proposito']}\n"
            "- Tudo aqui é sobre esse assunto; a memória é a mesma das outras conversas dele (use o que já sabe).\n"
            "- Ao terminar uma tarefa daqui, se houver uma próxima óbvia deste assunto, ofereça em uma linha.\n"
            "- Pedido de outro assunto: faça, e diga em uma linha que ele pode levar isso para o canal certo.")


def boas_vindas(canal: dict) -> str:
    """The first message of a new channel (Duet: "Want me to suggest tasks I can do here?")."""
    return (f"[Canal novo] Este é o canal #{canal['nome']}. Propósito: {canal['proposito']}\n"
            "Cumprimente em uma linha e sugira 3 tarefas concretas que você pode fazer aqui agora, a partir do que já "
            "sabe dele (memória, pendências em `fios`, e-mail e agenda se precisar, só lendo), cada uma em uma linha com "
            "o que entrega. Termine perguntando qual ajuda mais agora. Não faça nenhuma delas ainda.")

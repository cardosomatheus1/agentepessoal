"""Opening a chat sends only the recent steps in full; older steps go trimmed.

Opening a long chat sent its whole log to the browser: the Meta chat, with thousands of
steps (terminal output, page snapshots, memory notes), weighed 12.7 MB, and the phone took
seconds to parse it. The screen shows only the last ~60 entries anyway (older ones load on
"scroll up"), so here the newest KEEP entries go as they are, older ones up to MAX_ITEMS keep
their heading and type with content/arguments cut short, and steps older than that are left
out: Agent Zero itself saves only the last 1000 entries of a chat, so after a restart they
are gone anyway. The user's messages and the agent's answers are never cut or left out.
"util" entries (internal notes, hidden by default) are trimmed at any age. Nothing changes on
the server: the log in memory and on disk stays as it was.

Applied by wrapping state_snapshot.validate_snapshot_schema_v1, which build_snapshot_from_request
calls on the finished snapshot. Wrapping build_snapshot_from_request itself would sit between
login_usuarios's wrapper and its caller, and that wrapper reads the caller's frame.
"""

import json

MARCA = "_interface_celular_aliviar_v1"
KEEP = 150  # newest entries sent untouched
MAX_ITEMS = 1000  # entries sent at all (Agent Zero persists the same 1000)
CONTENT_MAX = 1500
VALUE_MAX = 400
CONVERSA = {"user", "response"}  # the conversation itself is never cut, however old


def _cortar(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    ocultos = len(texto) - limite
    return f"{texto[:limite]}\n\n<< {ocultos} caracteres ocultos (passo antigo; o completo fica salvo na conversa) >>"


def _valor(v):
    if isinstance(v, str):
        return _cortar(v, VALUE_MAX)
    if v is None or isinstance(v, (bool, int, float)):
        return v
    try:
        bruto = json.dumps(v, ensure_ascii=False)
    except Exception:
        bruto = str(v)
    return v if len(bruto) <= VALUE_MAX else _cortar(bruto, VALUE_MAX)


def _leve(item: dict) -> dict:
    # A copy: kvps is the live LogItem's own dict.
    novo = dict(item)
    if isinstance(novo.get("content"), str):
        novo["content"] = _cortar(novo["content"], CONTENT_MAX)
    kvps = novo.get("kvps")
    if isinstance(kvps, dict):
        novo["kvps"] = {k: _valor(v) for k, v in kvps.items()}
    return novo


def aliviar_logs(logs: list) -> list:
    if not isinstance(logs, list):
        return logs
    inteiros = len(logs) - KEEP
    enviados = len(logs) - MAX_ITEMS
    saida = []
    for i, item in enumerate(logs):
        if not isinstance(item, dict) or item.get("type") in CONVERSA:
            saida.append(item)
        elif i < enviados:
            continue
        elif i < inteiros or item.get("type") == "util":
            saida.append(_leve(item))
        else:
            saida.append(item)
    return saida


def aplicar() -> None:
    from helpers import state_snapshot

    # The mark holds the installed copy of this file: an updated file (reloaded by the
    # extensions) replaces the previous wrapper without a restart.
    instalado = getattr(state_snapshot, MARCA, None)
    if instalado is aliviar_logs:
        return
    atual = state_snapshot.validate_snapshot_schema_v1
    original = atual.__wrapped__ if instalado else atual

    def validate_snapshot_schema_v1(snapshot):
        try:
            if isinstance(snapshot, dict) and snapshot.get("logs"):
                snapshot["logs"] = aliviar_logs(snapshot["logs"])
        except Exception as exc:  # never block the screen over this
            print(f"interface_celular: histórico não aliviado: {exc}", flush=True)
        return original(snapshot)

    validate_snapshot_schema_v1.__wrapped__ = original
    state_snapshot.validate_snapshot_schema_v1 = validate_snapshot_schema_v1
    setattr(state_snapshot, MARCA, aliviar_logs)

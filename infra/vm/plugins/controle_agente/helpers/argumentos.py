"""Tool arguments wrapped twice by the model: {"tool_name": "browser", "tool_args": {"tool_name": "browser",
"tool_args": {"action": "click", ...}}}. The tool got no real argument and did its default. 21/10, 99Food: every click
and every typed field became "state", which only reports the page, so nothing happened, and the agent concluded the site
did not respond."""

ENVELOPE = {"tool_name", "tool_args", "thoughts", "headline"}


def desembrulhar(tool_name: str, args) -> bool:
    """Unwraps in place (the same dict reaches the tool). True when it changed something."""
    if not isinstance(args, dict):
        return False
    mudou = False
    for _ in range(3):
        interno = args.get("tool_args")
        nome = str(args.get("tool_name") or "").strip()
        if (not isinstance(interno, dict) or not set(args) <= ENVELOPE
                or (nome and nome.lower() != str(tool_name or "").lower())):
            break
        args.clear()
        args.update(interno)
        mudou = True
    return mudou


# 21/10, 99Food: the model wrote deltaY; the browser tool takes delta_y and drops unknown names in **kwargs, so every
# scroll moved 0 px and the +55 in the phone-code list was never reached.
def _snake(nome: str) -> str:
    import re
    return re.sub(r"(?<=[a-z0-9])([A-Z])", lambda m: "_" + m.group(1).lower(), nome)


def nomes_do_navegador(tool_name: str, args) -> bool:
    """browser args in camelCase (deltaY, browserId, toX...) become the snake_case the tool takes. In place."""
    if (tool_name or "").lower() != "browser" or not isinstance(args, dict):
        return False
    trocar = {k: _snake(k) for k in args if isinstance(k, str) and _snake(k) != k and _snake(k) not in args}
    for antigo, novo in trocar.items():
        args[novo] = args.pop(antigo)
    return bool(trocar)

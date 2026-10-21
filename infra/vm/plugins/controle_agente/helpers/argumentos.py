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

"""20/10: in text mode Claude (Sonnet) sometimes answers a tool call in its own native format,
`<invoke name="browser"><parameter name="action">click</parameter>...</invoke>`, instead of the JSON Agent Zero
reads. Agent Zero's _context_doctor drops that XML and warns "plain text instead of a tool call"; the model tries again
the same way and the request loops (the iFood logs task stalled 20 min). Here that XML becomes the JSON tool call."""

import json
import re

_INVOKE = re.compile(r'<(?:[\w-]+:)?invoke\s+name="([^"]+)"\s*>(.*?)(?:</(?:[\w-]+:)?invoke>|$)', re.S)
_PARAM = re.compile(r'<(?:[\w-]+:)?parameter\s+name="([^"]+)"\s*>(.*?)(?:</(?:[\w-]+:)?parameter>|(?=<(?:[\w-]+:)?parameter\s)|$)', re.S)
_PARECE_JSON = re.compile(r'^(?:[{\[]|-?\d|true$|false$|null$)')


def _valor(bruto: str):
    v = bruto.strip()
    if _PARECE_JSON.match(v):
        try:
            return json.loads(v)
        except ValueError:
            pass
    return v


def converter(texto: str) -> str | None:
    """The JSON tool call for the first `<invoke>` in `texto`, or None when there is none. Text before it goes to
    "thoughts" (what the model said it would do)."""
    if not isinstance(texto, str) or "invoke" not in texto:
        return None
    m = _INVOKE.search(texto)
    if not m:
        return None
    antes_cru = texto[:m.start()]
    inicio = antes_cru.find("{")
    if inicio >= 0:  # 20/10 21h: a valid JSON call followed by a stray empty <invoke>: the JSON wins (the empty XML
        try:          # call replaced it and the browser looped with no arguments, 99Food form)
            ja, _fim = json.JSONDecoder().raw_decode(antes_cru[inicio:])
            if isinstance(ja, dict) and ja.get("tool_name"):
                return None
        except ValueError:
            pass
    nome, corpo = m.group(1).strip(), m.group(2)
    args = {p.group(1).strip(): _valor(p.group(2)) for p in _PARAM.finditer(corpo)}
    antes = re.sub(r"</?(?:[\w-]+:)?(?:function_calls|tool_call)>", "", texto[:m.start()]).strip(" \n`")
    pensou = [antes[:500]] if antes and not antes.startswith("{") else []
    return json.dumps({"thoughts": pensou or [f"chamar {nome}"], "headline": f"Usando {nome}",
                       "tool_name": nome, "tool_args": args}, ensure_ascii=False)

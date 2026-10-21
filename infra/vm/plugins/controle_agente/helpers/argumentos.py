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


# Ported from Hermes Agent (tools/tool_search_validation.py, MIT, Nous Research): repair what is safe, then validate
# against the tool's parameters; an invalid call is NOT run and the model gets the accepted parameters back. A0 tools
# have no JSON schema, so the parameters come from execute()'s signature plus the names its body reads from
# kwargs/self.args. Like Hermes, it fails OPEN: when the accepted names cannot be known for sure, nothing is blocked.
IGNORAR = {"thoughts", "headline", "_tool_name"}

# Names the tool's own signature does not have but navegador_rapido turns into a real call before it runs (21/10: the
# check above refused browser wait's `timeout`, so "wait until the text shows" never ran). Shown to the model in the
# schema with what they do.
EXTRAS = {"browser": {
    "timeout": "segundos (action wait; até 60)",
    "text_gone": "action wait: espera este texto sumir",
    "load": "action wait: espera a página terminar de carregar",
    "direction": "action scroll sem ref: down ou up",
    "amount": "action scroll sem ref: quantos pixels",
    "accept": "action dialog: true = OK/aceitar a próxima janela do site, false = cancelar",
}}


def com_extras(tool_name: str, nomes: set | None) -> set | None:
    return None if nomes is None else nomes | set(EXTRAS.get(str(tool_name or "").lower(), {}))


def _nomes_lidos(no, alvo) -> set | None:
    """Literal names read as alvo.get("x") / alvo["x"]; None when alvo is used any other way."""
    import ast

    nomes, outros = set(), False
    pais = {}
    for pai in ast.walk(no):
        for filho in ast.iter_child_nodes(pai):
            pais[filho] = pai
    for n in ast.walk(no):
        if not alvo(n):
            continue
        pai = pais.get(n)
        if (isinstance(pai, ast.Attribute) and pai.attr == "get" and isinstance(pais.get(pai), ast.Call)
                and pais[pai].args and isinstance(pais[pai].args[0], ast.Constant)
                and isinstance(pais[pai].args[0].value, str)):
            nomes.add(pais[pai].args[0].value)
        elif (isinstance(pai, ast.Subscript) and pai.value is n and isinstance(pai.slice, ast.Constant)
              and isinstance(pai.slice.value, str)):
            nomes.add(pai.slice.value)
        else:
            outros = True
    return None if outros else nomes


def aceitos(execute) -> set | None:
    """The argument names a tool's execute() takes, or None when they cannot be known for sure."""
    import ast
    import inspect
    import textwrap

    try:
        arvore = ast.parse(textwrap.dedent(inspect.getsource(execute)))
    except Exception:
        return None
    fn = next((n for n in ast.walk(arvore) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
    if fn is None:
        return None
    nomes = {a.arg for a in fn.args.args + fn.args.kwonlyargs if a.arg != "self"}
    corpo = ast.Module(body=fn.body, type_ignores=[])
    if fn.args.kwarg:
        kw = fn.args.kwarg.arg
        lidos = _nomes_lidos(corpo, lambda n: isinstance(n, ast.Name) and n.id == kw)
        if lidos is None:
            return None
        nomes |= lidos
    lidos = _nomes_lidos(corpo, lambda n: isinstance(n, ast.Attribute) and n.attr == "args"
                         and isinstance(n.value, ast.Name) and n.value.id == "self")
    if lidos is None:
        return None
    nomes |= lidos
    return nomes or None


def conferir(tool_name: str, args, nomes: set | None) -> str:
    """'' when the call may run; else the error the model gets (the tool is NOT run)."""
    import difflib

    if not nomes or not isinstance(args, dict):
        return ""
    desconhecidos = [k for k in args if k not in nomes and k not in IGNORAR]
    if not desconhecidos:
        return ""
    partes = []
    for k in desconhecidos:
        parecido = difflib.get_close_matches(str(k).lower(), sorted(nomes), n=1, cutoff=0.6)
        partes.append(f"'{k}'" + (f" (você quis dizer '{parecido[0]}'?)" if parecido else ""))
    return (f"A chamada a '{tool_name}' NÃO foi executada: argumento desconhecido {', '.join(partes)}. "
            f"Argumentos que '{tool_name}' aceita: {', '.join(sorted(nomes))}. "
            "Chame de novo só com esses nomes, direto em tool_args.")


# The other half of Hermes' fix: the model sees each tool's real parameters. In native mode Agent Zero sends a plugin
# tool (the browser, ours) with an EMPTY schema ({"properties": {}, "additionalProperties": true}): the model had to
# guess names (deltaY, direction, seconds) and sometimes wrapped the call in the text-mode {"tool_name", "tool_args"}.
# Built from the tool file, without importing it: execute()'s parameters (type from the annotation when it is a plain
# one) plus the names the body reads; unknown -> None (Agent Zero's schema stays).
_TIPOS = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "list": "array", "dict": "object"}


def _tipo(anotacao) -> str:
    import ast

    if isinstance(anotacao, ast.Name):
        return _TIPOS.get(anotacao.id, "")
    if isinstance(anotacao, ast.Subscript) and isinstance(anotacao.value, ast.Name):
        return _TIPOS.get(anotacao.value.id, "")
    return ""  # unions, Any, None: no type, the model may send any


def esquema(fonte: str) -> dict | None:
    import ast

    try:
        arvore = ast.parse(fonte)
    except SyntaxError:
        return None
    fn = next((n for c in arvore.body if isinstance(c, ast.ClassDef) for n in c.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "execute"), None)
    if fn is None:
        return None
    segmento = ast.get_source_segment(fonte, fn) or ""

    class _Fonte:  # aceitos() reads the source through inspect.getsource
        pass

    import inspect

    original = inspect.getsource
    inspect.getsource = lambda _obj: segmento
    try:
        nomes = aceitos(_Fonte)
    finally:
        inspect.getsource = original
    if not nomes:
        return None
    props = {}
    for a in fn.args.args + fn.args.kwonlyargs:
        if a.arg == "self":
            continue
        tipo = _tipo(a.annotation) if a.annotation is not None else ""
        props[a.arg] = {"type": tipo} if tipo else {}
    for nome in sorted(nomes - set(props)):
        props[nome] = {}
    return {"type": "object", "properties": props, "additionalProperties": False}


def esquema_com_extras(base, tool_name: str):
    """The schema plus EXTRAS for this tool (a copy; the base may be cached)."""
    extras = EXTRAS.get(str(tool_name or "").lower())
    if not extras or not isinstance(base, dict) or not isinstance(base.get("properties"), dict):
        return base
    novo = dict(base, properties=dict(base["properties"]))
    for nome, texto in extras.items():
        novo["properties"][nome] = dict(novo["properties"].get(nome) or {}, description=texto)
    return novo

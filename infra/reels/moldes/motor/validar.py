"""Checks a ficha against its template's esquema.json before anything is rendered.

Rules that hold for every template: no dash characters (AR Board 13/10), no emoji (the renderer has no emoji font
and captions go without emoji), and a field marked "real" needs a value plus its origin in ficha["_origem"] (who
gave it: "dono" or "sistema"); without real data the template does not render and the agent picks another one.
"""
import re
from datetime import date

TRACO = re.compile("[—–]")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")
ORIGENS = {"dono", "sistema"}


def _texto(nome, v, regra, erros):
    if not isinstance(v, str):
        erros.append(f"{nome}: precisa ser texto"); return
    if regra.get("max") and len(v) > regra["max"]:
        erros.append(f"{nome}: {len(v)} letras, o máximo é {regra['max']}")
    if regra.get("min") and len(v.strip()) < regra["min"]:
        erros.append(f"{nome}: curto demais (mínimo {regra['min']} letras)")


def _valor(nome, v, regra, erros):
    tipo = regra.get("tipo", "texto")
    if tipo == "texto":
        _texto(nome, v, regra, erros)
    elif tipo in ("numero", "dinheiro", "porcentagem"):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            erros.append(f"{nome}: precisa ser número"); return
        if "min" in regra and v < regra["min"]: erros.append(f"{nome}: menor que {regra['min']}")
        if "max" in regra and v > regra["max"]: erros.append(f"{nome}: maior que {regra['max']}")
        if tipo == "dinheiro" and v < 0: erros.append(f"{nome}: valor negativo")
    elif tipo == "data":
        try: date.fromisoformat(v)
        except Exception: erros.append(f"{nome}: data no formato AAAA-MM-DD")
    elif tipo == "hora":
        if not (isinstance(v, str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v)): erros.append(f"{nome}: hora no formato HH:MM")
    elif tipo in ("foto", "filmagem", "logo"):
        if not isinstance(v, str) or not v: erros.append(f"{nome}: caminho da {tipo}")
    elif tipo == "escolha":
        if v not in regra.get("opcoes", []): erros.append(f"{nome}: escolha entre {regra.get('opcoes')}")
    elif tipo == "booleano":
        if not isinstance(v, bool): erros.append(f"{nome}: sim ou não (true/false)")
    elif tipo == "lista":
        if not isinstance(v, list): erros.append(f"{nome}: precisa ser lista"); return
        if "min" in regra and len(v) < regra["min"]: erros.append(f"{nome}: {len(v)} itens, o mínimo é {regra['min']}")
        if "max" in regra and len(v) > regra["max"]: erros.append(f"{nome}: {len(v)} itens, o máximo é {regra['max']}")
        item = regra.get("item")
        for i, x in enumerate(v):
            if isinstance(item, dict) and "tipo" in item:
                _valor(f"{nome}[{i + 1}]", x, item, erros)
            elif isinstance(item, dict):
                if not isinstance(x, dict): erros.append(f"{nome}[{i + 1}]: precisa ser objeto"); continue
                _campos(x, item, erros, f"{nome}[{i + 1}].")
    elif tipo == "objeto":
        if not isinstance(v, dict): erros.append(f"{nome}: precisa ser objeto"); return
        _campos(v, regra.get("campos", {}), erros, nome + ".")
    else:
        erros.append(f"{nome}: tipo desconhecido no esquema ({tipo})")


def _campos(ficha, campos, erros, pre=""):
    for nome, regra in campos.items():
        v = ficha.get(nome)
        if v is None or v == "" or v == []:
            if regra.get("obrigatorio", True): erros.append(f"{pre}{nome}: falta")
            continue
        _valor(pre + nome, v, regra, erros)
    for nome in ficha:
        if not nome.startswith("_") and nome not in campos and nome not in ("chamada", "final_extra", "nota"):
            erros.append(f"{pre}{nome}: campo que o molde não usa")


def _textos(x, caminho=""):
    if isinstance(x, str): yield caminho, x
    elif isinstance(x, dict):
        for k, v in x.items():
            if not k.startswith("_"): yield from _textos(v, f"{caminho}.{k}" if caminho else k)
    elif isinstance(x, list):
        for i, v in enumerate(x): yield from _textos(v, f"{caminho}[{i + 1}]")


def _reais(campos, ficha, pre=""):
    for nome, regra in campos.items():
        v = ficha.get(nome) if isinstance(ficha, dict) else None
        if regra.get("real") and v not in (None, "", []): yield pre + nome
        if regra.get("tipo") == "lista" and isinstance(regra.get("item"), dict) and "tipo" not in regra["item"] and isinstance(v, list):
            for i, x in enumerate(v): yield from _reais(regra["item"], x, f"{pre}{nome}[{i + 1}].")
        if regra.get("tipo") == "objeto" and isinstance(v, dict):
            yield from _reais(regra.get("campos", {}), v, f"{pre}{nome}.")


def validar(esquema: dict, ficha: dict) -> list[str]:
    erros = []
    campos = esquema.get("campos", {})
    _campos(ficha, campos, erros)
    for caminho, s in _textos(ficha):
        if TRACO.search(s): erros.append(f"{caminho}: sem travessão (— ou –)")
        if EMOJI.search(s): erros.append(f"{caminho}: sem emoji")
    origem = ficha.get("_origem", {})
    for nome, regra in campos.items():
        if regra.get("real") and regra.get("obrigatorio", True) and ficha.get(nome) in (None, "", []):
            erros.append(f"{nome}: dado real obrigatório; sem ele este molde não gera")
    for caminho in _reais(campos, ficha):
        raiz = caminho.split("[")[0].split(".")[0]
        if origem.get(caminho) not in ORIGENS and origem.get(raiz) not in ORIGENS:
            erros.append(f"{caminho}: dado real sem origem (_origem: dono ou sistema)")
    fmt = ficha.get("_formato")
    if fmt and fmt not in esquema.get("formatos", []):
        erros.append(f"_formato: {fmt} não é formato deste molde ({esquema.get('formatos')})")
    if "chamada" in ficha: _texto("chamada", ficha["chamada"], {"max": 32}, erros)
    if "final_extra" in ficha: _texto("final_extra", ficha["final_extra"], {"max": 70}, erros)
    return erros


def palavras_novas(agora, vistos) -> int:
    """Words a viewer must read in a scene: texts on screen not seen earlier in the video (one that was visible
    before, hidden at the end of the last scene and back again is not new), counting only words with a letter or
    digit ("·", "|", "+" are not words)."""
    return sum(1 for x in set(agora) - set(vistos) for w in x.split() if re.search(r"\w", w))

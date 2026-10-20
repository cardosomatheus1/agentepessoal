"""Anotação automática (20/10, Q8 of the grill): after each of Matheus's turns on the phone, a cheap model reads what HE
said in that turn and proposes Decisões, Pendências (new or done) and Assuntos (new or where they stopped); the code
checks each one (his literal words must be quoted, at most a few per turn) and writes them through the only writers
(decisoes.py, fios.py, assuntos.py). Then ONE line goes to his phone ("📌 Anotei …"); if he says nothing, it stays,
if he corrects ("era só ideia", "tira isso") the agent undoes it with the `cerebro` tool. Items born in the same turn
are linked to each other (Q17)."""

import json
import re
import time
import unicodedata
import urllib.request
from pathlib import Path

URL = "http://host.docker.internal:8787/openai/v1/responses"
MODELO = "openai.gpt-6-luna"
MAX_POR_TIPO = 3

PEDIDO = """Você mantém o Segundo Cérebro do Matheus. Leia SÓ o que o Matheus escreveu neste turno (a resposta do assistente
é contexto) e devolva JSON com o que deve ficar registrado. Na dúvida, não registre.

Definições:
- decisoes: uma escolha que ele JÁ fez e que vale daqui para a frente ("vamos cobrar R$ 497 de setup"). Pedido ao
  assistente ("faça X", "manda Y") NÃO é decisão. tema = nome curto canônico com pontos (ex.: raiz.preco-setup).
  tipo: decisao | permissao (o agente pode sem perguntar) | proibicao (não pode) | preferencia.
- pendencias: algo que ELE precisa fazer e ainda não fez. Frases como "ainda não terminei X", "tenho que fazer Y",
  "preciso mandar Z", "falta eu W" SEMPRE viram pendência (ex.: "ainda nao terminei a tarefa do MEI" → pendência
  "Terminar a tarefa do MEI"). Uma frase pode ter decisão E pendência E assunto: registre todos. Tarefa que ele pediu
  ao assistente NÃO é pendência dele. prazo só se ele disse uma data (AAAA-MM-DD); "essa semana" vai no detalhe.
- pendencias_feitas: id de uma pendência aberta (lista abaixo) que ele disse ter feito ("fiz o MEI").
- assuntos: tema que ele vem discutindo e que não terminou (plano, negócio, ideia levada pela metade), com onde
  parou agora. Use o id de um assunto aberto da lista quando for o mesmo tema. estado: andamento | parado | encerrado.
- area: raiz | nexos | orbyte | agente | pessoal | geral.
- citacao: trecho LITERAL de uma mensagem dele (5 a 25 palavras), copiado sem mudar nada.
No máximo 3 de cada. Nada a registrar: listas vazias.

Pendências abertas:
{pendencias}

Assuntos abertos:
{assuntos}

Decisões em vigor (temas):
{decisoes}

Turno:
Matheus: {dele}
Assistente: {resposta}

Responda só o JSON:
{{"decisoes": [{{"tema": "", "decisao": "", "tipo": "decisao", "area": "", "citacao": ""}}],
 "pendencias": [{{"titulo": "", "detalhe": "", "area": "", "prazo": "", "citacao": ""}}],
 "pendencias_feitas": [{{"id": "", "citacao": ""}}],
 "assuntos": [{{"id": "", "titulo": "", "onde_parou": "", "estado": "andamento", "area": "", "citacao": ""}}]}}"""

_DOBRA = str.maketrans({**dict.fromkeys("\"'`‘’‚‛“”„‟«»", "'"), **dict.fromkeys("‐‑‒–—―−", "-")})


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKC", str(t or "")).translate(_DOBRA).lower()
    return " ".join(t.split())


def citacao_confere(citacao: str, dele: list[str]) -> bool:
    """His own words, as written (only spacing, case and the shape of quotes/dashes may differ), 3+ words."""
    c = _norm(citacao).strip(" .,;:!?'-…")
    return len(c) >= 8 and len(c.split()) >= 3 and any(c in _norm(m) for m in dele)


def _curto(t, n: int) -> str:
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t if len(t) <= n else t[:n] + "…"


def montar_pedido(dele: list[str], resposta: str, pendencias: list, assuntos: list, decisoes: list) -> str:
    return PEDIDO.format(
        pendencias="\n".join(f"- [{f.get('id')}] {_curto(f.get('titulo'), 120)}" for f in pendencias[:30]) or "(nenhuma)",
        assuntos="\n".join(f"- [{a.get('id')}] {_curto(a.get('titulo'), 100)} — parou: {_curto(a.get('onde_parou'), 120)}"
                           for a in assuntos[:20]) or "(nenhum)",
        decisoes="\n".join(f"- {d.get('tema')}: {_curto(d.get('valor'), 90)}" for d in decisoes[:60]) or "(nenhuma)",
        dele="\n".join(_curto(m, 2000) for m in dele), resposta=_curto(resposta, 1200))


def chamar(pedido: str) -> str:
    body = {"model": MODELO, "reasoning": {"effort": "low"}, "input": [{"role": "user", "content": pedido}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                                             "X-A0-Dono": "matheus"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read())
    return "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []) if c.get("type") == "output_text")


def interpretar(saida: str) -> dict | None:
    achado = re.search(r"\{.*\}", saida or "", re.S)
    if not achado:
        return None
    try:
        d = json.loads(achado.group(0))
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    lista = lambda k: [x for x in (d.get(k) or []) if isinstance(x, dict)][:MAX_POR_TIPO]  # noqa: E731
    return {k: lista(k) for k in ("decisoes", "pendencias", "pendencias_feitas", "assuntos")}


def aplicar(propostas: dict, dele: list[str], origem: str, decisoes_mod, fios_mod, assuntos_mod,
            login: str = "matheus", agora: float | None = None) -> dict:
    """Check and write; {feito: [(tipo, ref, texto)], descartados: [motivo]}. Same-turn items are linked."""
    agora = agora or time.time()
    feito, descartados = [], []
    abertas = {str(f.get("id")): f for f in fios_mod.abertos(login, limite=200)}

    def ok(p, tipo) -> bool:
        if not citacao_confere(p.get("citacao", ""), dele):
            descartados.append(f"{tipo} sem citação literal dele")
            return False
        return True

    for p in propostas.get("pendencias_feitas") or []:
        fid = str(p.get("id") or "").strip()
        if fid in abertas and ok(p, "pendência feita"):
            fios_mod.mesclar(login, [{"id": fid, "estado": "resolvido", "prova": f"ele disse: “{_curto(p['citacao'], 200)}”",
                                      "fechado_em": agora}])
            feito.append(("pendencia-feita", f"pendencia:{fid}", abertas[fid].get("titulo", "")))
    novos = []
    for p in propostas.get("decisoes") or []:
        if ok(p, "decisão") and str(p.get("tema") or "").strip() and len(str(p.get("decisao") or "")) >= 8:
            r = decisoes_mod.registrar(login, p["tema"], p["decisao"], p.get("tipo") or "decisao",
                                       citacao=p["citacao"], origem=origem, por="captura", area=p.get("area") or "",
                                       agora=agora)
            if r.get("efeito") != "igual":
                novos.append(("decisao", f"decisao:{r['id']}", r["valor"]))
    for p in propostas.get("pendencias") or []:
        titulo = _curto(p.get("titulo"), 140)
        if ok(p, "pendência") and len(titulo) >= 6:
            ja = next((f for f in abertas.values() if _norm(f.get("titulo")) == _norm(titulo)), None)
            if ja:
                continue
            item = {"titulo": titulo, "detalhe": _curto(p.get("detalhe"), 400), "area": (p.get("area") or "geral").lower(),
                    "dono": "você", "origem": origem, "citacao": _curto(p["citacao"], 300), "por": "captura"}
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(p.get("prazo") or "")):
                item["prazo"] = p["prazo"]
            antes = {str(f.get("id")) for f in fios_mod.carregar(login)["fios"]}
            fios_mod.mesclar(login, [item])
            fid = next((str(f.get("id")) for f in fios_mod.carregar(login)["fios"] if str(f.get("id")) not in antes), "")
            if fid:
                novos.append(("pendencia", f"pendencia:{fid}", titulo))
    for p in propostas.get("assuntos") or []:
        if not ok(p, "assunto"):
            continue
        try:
            if str(p.get("id") or "").strip():
                a = assuntos_mod.atualizar(p["id"], onde_parou=p.get("onde_parou", ""), estado=p.get("estado", ""),
                                           citacao=p["citacao"], por="captura", agora=agora)
                novos.append(("assunto-atualizado", f"assunto:{a['id']}", f"{a['titulo']} — parou: {a.get('onde_parou')}"))
            elif len(str(p.get("titulo") or "")) >= 4:
                a = assuntos_mod.registrar(p["titulo"], onde_parou=p.get("onde_parou", ""), area=p.get("area", ""),
                                           estado=p.get("estado", "andamento"), citacao=p["citacao"], origem=origem,
                                           por="captura", agora=agora)
                novos.append(("assunto", f"assunto:{a['id']}", f"{a['titulo']} — parou: {a.get('onde_parou') or '…'}"))
        except KeyError:
            descartados.append("assunto com id desconhecido")
    refs = [r for _t, r, _x in novos]
    if len(refs) > 1:  # Q17: what one sentence produced stays linked
        ligar(refs, decisoes_mod, fios_mod, assuntos_mod, login)
    return {"feito": feito + novos, "descartados": descartados}


def ligar(refs: list, decisoes_mod, fios_mod, assuntos_mod, login: str) -> None:
    for ref in refs:
        outros = [r for r in refs if r != ref]
        tipo, _, ident = ref.partition(":")
        if tipo == "assunto":
            assuntos_mod.atualizar(ident, liga=outros, por="captura")
        elif tipo == "pendencia":
            atual = next((f for f in fios_mod.carregar(login)["fios"] if str(f.get("id")) == ident), {})
            fios_mod.mesclar(login, [{"id": ident, "liga": list(dict.fromkeys((atual.get("liga") or []) + outros))}])
        elif tipo == "decisao":
            with decisoes_mod._exclusivo(login):
                d = decisoes_mod.carregar(login)
                x = next((x for x in d["decisoes"] if str(x["id"]) == ident), None)
                if x:
                    x["liga"] = list(dict.fromkeys((x.get("liga") or []) + outros))
                    decisoes_mod._salvar(login, d)


ROTULO = {"decisao": "decisão", "pendencia": "pendência", "pendencia-feita": "pendência feita", "assunto": "assunto",
          "assunto-atualizado": "assunto"}


def aviso(feito: list) -> str:
    """The one line to his phone, '' when nothing new."""
    if not feito:
        return ""
    partes = [f"{ROTULO.get(t, t)}: «{_curto(texto, 90)}»" for t, _r, texto in feito[:4]]
    extra = f" (+{len(feito) - 4})" if len(feito) > 4 else ""
    return "📌 Anotei — " + " · ".join(partes) + extra + ". Se não era isso, é só me dizer."


def estado_arquivo(raiz: Path) -> Path:
    return raiz / ".captura.json"


def ler_estado(raiz: Path) -> dict:
    try:
        return json.loads(estado_arquivo(raiz).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"chats": {}, "ultimo": []}

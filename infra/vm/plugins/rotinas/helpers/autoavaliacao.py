"""Self-assessment of scheduled routines (Matheus, 20/10): at the end of each round a cheap model says in ONE line
whether the result was good and, when it sees an improvement to the routine, the agent proposes it to him on the
phone with ✅ Aplicar / ❌ Não. Nothing changes without his ok: "Aplicar" writes the change through the corrections
path of helpers/rotinas.py (corrigir_agendada: dated, with who approved, no repeats, diário), never the routine's
prompt or the scheduler's tasks.json.

- Rounds that failed for infra reasons (exception, rate limit, connection, login/captcha) are logged and never assessed
  by the model nor turned into a proposal; "SEM NOVIDADE" rounds (and the gate's skipped ones) are logged without a
  model call.
- At most one proposal per routine every DIAS_ENTRE days; never one equal to an earlier proposal (pending, applied
  or refused) or to a correction already in force.
- Log: PASTA/<uuid>.jsonl, append-only events ({"tipo": "avaliacao" | "proposta" | "resposta" | "envio_falhou"});
  past MAX_AVALIACOES the oldest assessments leave (proposals and answers always stay).
Entry points: autoavaliar() (end-of-round hook, in a background thread) and responder() (the phone buttons)."""

import fcntl
import importlib.util
import json
import re
import secrets
import sys
import time
import unicodedata
import urllib.request
from contextlib import contextmanager
from pathlib import Path

PASTA = Path("/a0/usr/rotinas/autoavaliacao")
RAIZ = Path(__file__).resolve().parents[1]
PLUGINS = RAIZ.parent if (RAIZ.parent / "whatsapp").exists() else Path("/a0/usr/plugins")
URL = "http://host.docker.internal:8787/openai/v1/responses"
MODELO = "openai.gpt-6-luna"  # same cheap model as the cerebro's anotação automática
DONO = "matheus"
DIAS_ENTRE = 7
MAX_AVALIACOES = 120
PREFIXO = "rta"

# a round that ended like this failed for infra reasons: nothing to learn about the routine itself
INFRA = re.compile(r"\b(429|rate.?limit|consulta limitada|timed? ?out|timeout|sem resposta em|connection|conex[aã]o|"
                   r"indispon[ií]vel|unavailable|captcha|verifica[cç][aã]o de seguran[cç]a|login expirou|"
                   r"sess[aã]o expirou|falhou por completo|erro (?:de|da|do) (?:rede|conector|ferramenta|servidor)|"
                   r"traceback|exception)\b", re.I)

PEDIDO = """Você avalia uma rodada de uma rotina agendada do Matheus (o agente roda sozinho e manda o resultado a ele).

Rotina: {nome}
O que a rotina pede (resumo):
{pedido}

Correções que o Matheus já aprovou para ela:
{correcoes}

Mudanças já propostas antes (não proponha de novo, nem parecidas):
{anteriores}

Resultado desta rodada:
{resultado}

Responda só o JSON:
{{"nota": 1, "linha": "", "falha_infra": false, "melhoria": ""}}
- nota: 1 (inútil) a 5 (exatamente o que ele precisa).
- linha: UMA frase curta, sem jargão, dizendo se o resultado foi bom e por quê.
- falha_infra: true se a rodada não deu certo por conexão, limite, login, captcha ou ferramenta fora do ar.
- melhoria: só se uma mudança pequena e concreta na rotina deixaria as próximas rodadas claramente melhores; uma
  frase no imperativo, escrita como regra a seguir sempre (ex.: "Junte os e-mails do mesmo remetente numa linha só").
  Nada que a rotina já peça, nada sobre falha de infra, nada que envie, pague ou apague algo. Na dúvida: ""."""


# ---- loading (by path, reloaded when the file changes; tests pass their own) ----

def _carregar(nome: str, caminho: Path, manter: bool = False):
    antigo = sys.modules.get(nome)
    if manter and antigo is not None:
        return antigo
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _rotinas():
    return _carregar("rotinas_helper", RAIZ / "helpers" / "rotinas.py")


def _enviar(login: str, texto: str, botoes: list) -> str:
    ponte = _carregar("whatsapp_ponte", PLUGINS / "whatsapp" / "helpers" / "ponte.py", manter=True)
    return ponte.enviar(login, texto, botoes=botoes, tipo="progresso", reenviar=True)


def chamar(pedido: str) -> str:
    body = {"model": MODELO, "reasoning": {"effort": "low"}, "input": [{"role": "user", "content": pedido}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                                             "X-A0-Dono": DONO})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read())
    return "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []) if c.get("type") == "output_text")


# ---- small pieces ----

def _curto(t, n: int) -> str:
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def normal(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def _id(uuid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(uuid or "")) or "sem-id"


def _arq(uuid: str) -> Path:
    return PASTA / f"{_id(uuid)}.jsonl"


@contextmanager
def _trava(uuid: str):
    PASTA.mkdir(parents=True, exist_ok=True)
    with open(PASTA / f".{_id(uuid)}.lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def eventos(uuid: str) -> list[dict]:
    try:
        linhas = _arq(uuid).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    saida = []
    for l in linhas:
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if isinstance(e, dict):
            saida.append(e)
    return saida


def _anotar(uuid: str, evento: dict, agora: float) -> dict:
    """Append one event (call with the lock held); past MAX_AVALIACOES the oldest assessments leave."""
    evento = {"em": round(agora), **evento}
    arq = _arq(uuid)
    arq.parent.mkdir(parents=True, exist_ok=True)
    with open(arq, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(evento, ensure_ascii=False) + "\n")
    todos = eventos(uuid)
    avaliacoes = [e for e in todos if e.get("tipo") == "avaliacao"]
    if len(avaliacoes) > MAX_AVALIACOES:
        sobra = {id(e) for e in avaliacoes[: len(avaliacoes) - MAX_AVALIACOES]}
        tmp = arq.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in todos if id(e) not in sobra),
                       encoding="utf-8")
        tmp.replace(arq)
    return evento


def propostas(uuid: str) -> list[dict]:
    """Proposals with their state: pendente | aplicada | recusada | nao_enviada."""
    lista, por_id = [], {}
    for e in eventos(uuid):
        if e.get("tipo") == "proposta":
            p = {**e, "estado": "pendente"}
            lista.append(p)
            por_id[e.get("id")] = p
        elif e.get("tipo") == "resposta" and e.get("id") in por_id:
            por_id[e["id"]]["estado"] = e.get("decisao")
            por_id[e["id"]]["resposta"] = e
        elif e.get("tipo") == "envio_falhou" and e.get("id") in por_id:
            por_id[e["id"]]["estado"] = "nao_enviada"
    return lista


def interpretar(saida: str) -> dict | None:
    """{nota 1-5, linha, falha_infra, melhoria} or None (no JSON, no valid grade, no line)."""
    achado = re.search(r"\{.*\}", saida or "", re.S)
    if not achado:
        return None
    try:
        d = json.loads(achado.group(0))
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    try:
        nota = int(d.get("nota"))
    except (TypeError, ValueError):
        return None
    linha = _curto(d.get("linha"), 200)
    if not 1 <= nota <= 5 or not linha:
        return None
    infra = d.get("falha_infra") is True or str(d.get("falha_infra")).strip().lower() in ("true", "sim", "1")
    melhoria = "" if infra else _curto(d.get("melhoria"), 400)
    return {"nota": nota, "linha": linha, "falha_infra": infra, "melhoria": melhoria}


def falha_de_infra(resultado: str, erro=None) -> str:
    """Why the round counts as an infra failure ('' when it does not)."""
    if isinstance(erro, BaseException):
        return f"{type(erro).__name__}: {_curto(erro, 120)}"
    texto = str(resultado or "").strip()
    if not texto:
        return "rodada sem resposta"
    m = INFRA.search(texto[:400])
    return f"«{m.group(0)}» no resultado" if m else ""


def pode_propor(uuid: str, melhoria: str, correcoes: list, agora: float) -> str:
    """'' when this proposal may go now, else why not: limite | repetida | ja_vale."""
    alvo = normal(melhoria)
    if alvo in {normal(c) for c in correcoes}:
        return "ja_vale"
    feitas = propostas(uuid)
    if any(normal(p.get("melhoria")) == alvo for p in feitas):
        return "repetida"
    if any(p["estado"] != "nao_enviada" and agora - float(p.get("em") or 0) < DIAS_ENTRE * 86400 for p in feitas):
        return "limite"
    return ""


def mensagem(nome: str, linha: str, melhoria: str) -> str:
    return (f"🔧 *Rotina {nome}*\n\nComo foi agora: {linha}\n\n👉 *Sugestão de melhoria:* {melhoria}\n\n"
            "Aplico na rotina? Só muda com o seu ok.")


def botoes(login: str, uuid: str, pid: str) -> list:
    base = f"{PREFIXO}:{login}:{_id(uuid)}.{pid}"
    return [{"id": f"{base}:aplicar", "titulo": "✅ Aplicar"}, {"id": f"{base}:nao", "titulo": "❌ Não"}]


# ---- public ----

def autoavaliar(uuid: str, nome: str, resultado, pedido: str = "", erro=None, chamar_modelo=None, enviar=None,
                R=None, agora: float | None = None, login: str = DONO) -> dict:
    """Assess one finished round and, when it fits, propose ONE improvement to Matheus.
    {"motivo": infra|sem_novidade|sem_avaliacao|avaliada|proposta|limite|repetida|ja_vale|envio_falhou,
     "avaliacao": {...} | None, "proposta": id | None}. Never raises for a bad model answer."""
    agora = agora or time.time()
    R = R or _rotinas()
    resultado = str(resultado or "")
    infra = falha_de_infra(resultado, erro)
    if infra:
        with _trava(uuid):
            _anotar(uuid, {"tipo": "avaliacao", "nota": None, "linha": f"falha de infra: {infra}", "infra": True}, agora)
        return {"motivo": "infra", "avaliacao": None, "proposta": None}
    if resultado.lstrip().upper().startswith("SEM NOVIDADE"):
        with _trava(uuid):
            _anotar(uuid, {"tipo": "avaliacao", "nota": None, "linha": "sem novidade"}, agora)
        return {"motivo": "sem_novidade", "avaliacao": None, "proposta": None}
    correcoes = R.correcoes_agendada(uuid)
    anteriores = [p.get("melhoria", "") for p in propostas(uuid)][-10:]
    pedido_txt = PEDIDO.format(nome=nome, pedido=_curto(pedido, 3000) or "(sem texto)",
                               correcoes="\n".join(f"- {c}" for c in correcoes) or "(nenhuma)",
                               anteriores="\n".join(f"- {a}" for a in anteriores) or "(nenhuma)",
                               resultado=str(resultado)[:3500])
    try:
        avaliacao = interpretar((chamar_modelo or chamar)(pedido_txt))
    except Exception as exc:  # model down, timeout: the round is logged without a grade
        avaliacao, motivo_erro = None, f"{type(exc).__name__}: {_curto(exc, 120)}"
    else:
        motivo_erro = "resposta do modelo ilegível"
    with _trava(uuid):
        if avaliacao is None:
            _anotar(uuid, {"tipo": "avaliacao", "nota": None, "linha": f"sem avaliação ({motivo_erro})"}, agora)
            return {"motivo": "sem_avaliacao", "avaliacao": None, "proposta": None}
        _anotar(uuid, {"tipo": "avaliacao", "nota": avaliacao["nota"], "linha": avaliacao["linha"],
                       **({"infra": True} if avaliacao["falha_infra"] else {}),
                       **({"melhoria": avaliacao["melhoria"]} if avaliacao["melhoria"] else {})}, agora)
        if avaliacao["falha_infra"]:
            return {"motivo": "infra", "avaliacao": avaliacao, "proposta": None}
        if not avaliacao["melhoria"]:
            return {"motivo": "avaliada", "avaliacao": avaliacao, "proposta": None}
        barrada = pode_propor(uuid, avaliacao["melhoria"], correcoes, agora)
        if barrada:
            return {"motivo": barrada, "avaliacao": avaliacao, "proposta": None}
        pid = secrets.token_hex(4)
        _anotar(uuid, {"tipo": "proposta", "id": pid, "nome": nome, "melhoria": avaliacao["melhoria"],
                       "linha": avaliacao["linha"], "nota": avaliacao["nota"]}, agora)
    try:
        falhou = (enviar or _enviar)(login, mensagem(nome, avaliacao["linha"], avaliacao["melhoria"]),
                                     botoes(login, uuid, pid))
    except Exception as exc:
        falhou = f"{type(exc).__name__}: {exc}"
    if falhou:
        with _trava(uuid):  # he never saw it: it does not hold the next proposal back
            _anotar(uuid, {"tipo": "envio_falhou", "id": pid, "erro": _curto(falhou, 160)}, time.time())
        return {"motivo": "envio_falhou", "avaliacao": avaliacao, "proposta": pid}
    return {"motivo": "proposta", "avaliacao": avaliacao, "proposta": pid}


def ler_botao(botao: str) -> tuple[str, str, str, str]:
    """(login, uuid, proposal id, acao) of a "rta:<login>:<uuid>.<id>:<acao>" button ('' parts when malformed)."""
    partes = (str(botao or "").split(":") + ["", "", "", ""])[:4]
    if partes[0] != PREFIXO or "." not in partes[2]:
        return "", "", "", ""
    uuid, pid = partes[2].rsplit(".", 1)
    return partes[1], uuid, pid, partes[3]


def responder(usuario: str, botao: str, R=None, agora: float | None = None) -> str:
    """His answer to a proposal. Aplicar → corrigir_agendada with his ok recorded; Não → refusal recorded.
    Returns the line that goes back to his phone."""
    login, uuid, pid, acao = ler_botao(botao)
    if not login or login != str(usuario or "").lower() or acao not in ("aplicar", "nao"):
        return "Não reconheci esse botão."
    agora = agora or time.time()
    with _trava(uuid):
        p = next((x for x in propostas(uuid) if x.get("id") == pid), None)
        if p is None:
            return "Não achei mais essa sugestão."
        if p["estado"] in ("aplicada", "recusada"):
            return f"Essa sugestão já foi respondida ({p['estado']})."
        nome = p.get("nome") or uuid
        if acao == "nao":
            _anotar(uuid, {"tipo": "resposta", "id": pid, "decisao": "recusada", "por": login}, agora)
            return f"❌ Ok, a rotina {nome} fica como está (e não proponho isso de novo)."
        R = R or _rotinas()
        r = R.corrigir_agendada(uuid, nome, p["melhoria"], por=f"{login}, aprovou a sugestão {pid}")
        if not r.get("ok") and r.get("motivo") != "repetida":
            return f"Não consegui aplicar ({r.get('motivo')}); a rotina ficou como estava."
        _anotar(uuid, {"tipo": "resposta", "id": pid, "decisao": "aplicada", "por": login, "ok_de": login,
                       "gravada": r.get("motivo")}, agora)
    return f"✅ Aplicado na rotina {nome}: vale a partir da próxima rodada."

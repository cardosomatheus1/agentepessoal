"""Talk to the host's ponte_whatsapp (infra/vm/ponte_whatsapp.py).

The bridge holds the Meta token and the phone numbers; here people are addressed only by
their login name, so the agent can reach no one but the registered users.
"""

import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

URL = "http://host.docker.internal:8789/enviar"
_abrir = urllib.request.urlopen  # the bridge call (tests replace it in their own copy)
PEDIDOS: dict[str, dict] = {}  # login -> code the agent asked for on WhatsApp (pedir_codigo)
CHAVE = Path("/a0/usr/whatsapp/.chave")
CAIXA_TESTES = Path("/a0/usr/testes/celular.jsonl")  # phone messages of "teste_*" logins (tests)
# Migração ao Hermes (23/10): no container do Hermes, até a virada, AGENTEPESSOAL_ENSAIO=1. Nada vai ao celular: o que
# iria fica numa caixa do próprio Hermes (fora de /a0/usr) e volta como "não enviado", sem fila de reenvio (SAIDA está
# em /a0/usr: o A0 mandaria depois) e sem marcar aviso (o A0 deixaria de mandar o dele achando que já foi).
ENSAIO = "AGENTEPESSOAL_ENSAIO"
CAIXA_ENSAIO = Path("/opt/data/agentepessoal/ensaio_celular.jsonl")
ERRO_ENSAIO = ("ensaio do Hermes: nada vai ao celular antes da virada (guardado para o operador conferir). Não tente de "
               "outro jeito; diga ao operador o que ia mandar.")


def em_ensaio() -> bool:
    return os.environ.get(ENSAIO) == "1"


def chave() -> str:
    try:
        return CHAVE.read_text().strip()
    except OSError:
        return ""


CAMPOS_BILHETE = ("usuario", "conversa", "gatilho", "botao", "texto", "audio", "anexos")  # same as the bridge's


def resumo_entrega(dados: dict) -> str:
    return hashlib.sha256(json.dumps({k: dados.get(k) for k in CAMPOS_BILHETE}, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()


def entrega_da_ponte(dados: dict) -> bool:
    """The delivery really came from the bridge: it carries a one-time ticket that only the bridge (on the host, outside
    this container) keeps, and the bridge spends it now. The agent can read the shared key, so without this it could
    fake a phone message or a button press — an "aprovar" for its own action (12/10 review). Test logins (teste_*)
    reach no one and own nothing, so their tools may still post without a ticket (one that comes is checked)."""
    if not dados.get("bilhete"):
        return str(dados.get("usuario") or "").startswith("teste_")
    req = urllib.request.Request(URL.rsplit("/", 1)[0] + "/conferir",
                                 data=json.dumps({"bilhete": dados["bilhete"], "resumo": resumo_entrega(dados)}).encode(),
                                 headers={"Content-Type": "application/json", "X-Chave": chave()})
    try:
        with _abrir(req, timeout=10) as r:
            return bool(json.loads(r.read() or b"{}").get("ok"))
    except Exception as exc:
        print(f"whatsapp: bridge ticket check failed: {exc}", flush=True)
        return False


# 12/10 review (§4.3, item 5): "starts with falha/erro/atenção/⚠️" made every routine hiccup urgent, ringing in his
# quiet hours. Urgent now = the routine says it needs him ("PRECISA DE VOCÊ", the convention of every routine prompt)
# or a real block only he can clear: login or code asked, captcha, account blocked/limited.
URGENTE = re.compile(r"^\W*(precisa de voc[eê]|🚨)", re.I)
BLOQUEIO = re.compile(r"(pediu|pede|precisa de|fazer|refazer|entrar com) (o |um |de novo o )?(login|c[oó]digo)|"
                      r"login (expirou|caiu)|sess[aã]o expirou|\b2fa\b|captcha|verifica[cç][aã]o em (duas|2) etapas|"
                      r"conta (foi )?(bloqueada|suspensa|restrita|limitada|desativada)", re.I)


URL_AGENTE = Path("/a0/usr/agente/url.txt")  # the app's public address, kept current by the VM's report_url.py
TELA = Path("/a0/usr/plugins/navegador_visual/helpers/tela.py")  # signed links to one chat's browser tab
PEDE_NAVEGADOR = re.compile(r"\b(navegador|browser)\b", re.I)
# a block only solved on the screen, even when the answer does not name the Navegador (15/10: "resolva a verificação
# do Cloudflare pelo botão Resolver aqui" never reached the phone)
SO_NA_TELA = re.compile(r"captcha|cloudflare|resolver aqui|verifica[cç][aã]o (de seguran[cç]a|humana)|n[aã]o sou um rob", re.I)
PEDE_ACAO = re.compile(r"captcha|desafio|login|logar|entrar|entre |resolv|conclu|confirm|c[oó]digo|verifica", re.I)


def _modulo_tela(caminho: Path = TELA):
    spec = importlib.util.spec_from_file_location("navegador_visual_tela_ponte", caminho)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pede_tela(texto: str) -> bool:
    """The answer asks the person to do something in the Navegador (captcha, login, code)."""
    texto = str(texto or "")
    return bool(PEDE_NAVEGADOR.search(texto) and PEDE_ACAO.search(texto) or SO_NA_TELA.search(texto))


def botao_do_navegador(texto: str, ctx_id: str, usuario: str, arquivo: Path | None = None, tela=None) -> dict | None:
    """A reply that asks the person to do something in the Navegador (captcha, login, code) gets a "🖥️ Resolver aqui"
    button that opens, inside Telegram, the live tab of this very chat (14/10, Matheus: "quero conseguir resolver
    pelo Telegram, sem nada extra"; before, the app's panel showed whichever chat was selected there)."""
    if not ctx_id or not usuario or not pede_tela(texto):
        return None
    try:
        base = (arquivo or URL_AGENTE).read_text(encoding="utf-8").strip()
        link = (tela or _modulo_tela()).link(base, ctx_id, usuario)
    except Exception:
        return None
    return {"titulo": "🖥️ Resolver aqui", "url": link} if link else None


def urgente(texto: str) -> bool:
    texto = str(texto or "")
    return bool(URGENTE.match(texto) or BLOQUEIO.search(texto[:600]))


def _corpo(usuario: str, texto: str, arquivo: str, legenda: str, botoes: list | None, tipo: str, rotina: str,
           app: dict | None) -> dict:
    corpo = {"usuario": usuario, "texto": formatar(texto) if texto else "", "arquivo": arquivo, "legenda": legenda,
             "botoes": botoes or [], "tipo": tipo or ("urgente" if botoes else "resposta"), "rotina": rotina}
    if app:
        corpo["app"] = app
    return corpo


def _postar(corpo: dict) -> tuple[str, bool]:
    """POST to the bridge's /enviar: ("", False) when sent, else (reason, uncertain). Uncertain = the bridge got the
    request, so part of it may have reached the phone (it answered 5xx, or the answer was lost); a request that never
    reached it (refused, no route: urllib wraps those in URLError while sending) is not."""
    req = urllib.request.Request(URL, data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json", "X-Chave": chave()})
    try:
        with _abrir(req, timeout=180) as r:
            r.read()
        return "", False
    except urllib.error.HTTPError as e:
        try:
            erro = json.loads(e.read()).get("erro") or str(e)
        except Exception:
            erro = str(e)
        return erro, e.code >= 500
    except urllib.error.URLError as e:
        return str(e), False
    except Exception as exc:  # timed out or cut while the bridge was sending
        return str(exc) or type(exc).__name__, True


def enviar(usuario: str, texto: str = "", arquivo: str = "", legenda: str = "", botoes: list | None = None,
           tipo: str = "", sempre: bool = False, rotina: str = "", app: dict | None = None,
           reenviar: bool = False) -> str:
    """'' when sent, else the reason it was not. botoes: up to 3 [{"id", "titulo"}] reply buttons.
    tipo: "resposta" (default: answer to the person), "urgente" (needs them now: goes even in quiet hours) or
    "progresso" (held during their quiet hours and delivered together afterwards).
    sempre: send even when identical to a recent notice (a new request that happens to read the same, e.g. a code).
    rotina: the scheduled task that wrote it (the bridge puts the night's held notices inside the morning summary).
    app: {"titulo", "url"}: a button that opens a page inside Telegram (WhatsApp gets the link in the text).
    reenviar: when it fails, keep it in SAIDA for the job loop to try again (see reenviar_pendentes)."""
    if not usuario:
        return "conversa sem dono"
    if usuario.startswith("teste_"):  # test logins: what would reach the phone is recorded, nothing is sent
        CAIXA_TESTES.parent.mkdir(parents=True, exist_ok=True)
        with CAIXA_TESTES.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"em": time.time(), "usuario": usuario, "texto": texto, "arquivo": arquivo,
                                "legenda": legenda, "botoes": botoes or [], "tipo": tipo, "rotina": rotina,
                                "app": app},
                               ensure_ascii=False) + "\n")
        return ""
    if em_ensaio():
        try:
            CAIXA_ENSAIO.parent.mkdir(parents=True, exist_ok=True)
            with CAIXA_ENSAIO.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"em": time.time(), "usuario": usuario, "texto": texto, "arquivo": arquivo,
                                    "legenda": legenda, "botoes": botoes or [], "tipo": tipo, "rotina": rotina},
                                   ensure_ascii=False) + "\n")
        except OSError:
            pass
        return ERRO_ENSAIO
    corpo = _corpo(usuario, texto, arquivo, legenda, botoes, tipo, rotina, app)
    marca = _chave_aviso(texto, arquivo, botoes)
    janela = REPETIDO_H.get(corpo["tipo"])
    if janela and texto and not sempre and _ja_avisado(usuario, marca, janela):
        _segurar(usuario, texto, corpo["tipo"], f"igual a um aviso das últimas {janela} h")
        return ""  # it reached the phone already: for the caller this one is delivered
    erro, incerto = _postar(corpo)
    if not erro:
        if corpo["tipo"] != "resposta" and texto:
            _lembrar_aviso(usuario, texto, marca)
        return ""
    if reenviar:
        guardar_saida({"usuario": usuario, "texto": texto, "arquivo": arquivo, "legenda": legenda, "botoes": botoes or [],
                       "tipo": tipo, "sempre": sempre, "rotina": rotina, "app": app}, erro, incerto)
    return erro


# 14/10 (Hermes gateway/delivery_ledger.py): an answer the bridge refused (502: Telegram or Meta down, flood control)
# only went to the log and was lost. Now it waits in SAIDA and the job loop (_58_reenviar_saida) tries again 30 s and
# then 2 min later: 3 tries in all, within 24 h. When the bridge had the request (5xx, answer lost) part of it may
# already be on the phone, so the new try says "(pode ser repetida)". A destination that cannot work (nobody
# registered, chat gone, bot blocked, file missing) is never retried. Given-up messages go to SAIDA_DESISTIDA.
SAIDA = Path("/a0/usr/whatsapp/saida_pendente.jsonl")
SAIDA_DESISTIDA = Path("/a0/usr/whatsapp/saida_desistida.jsonl")
REENVIO_APOS = (30, 120)  # wait before the 2nd and the 3rd try
REENVIO_MAX = 3           # tries in all, counting the first
REENVIO_VIDA = 24 * 3600
REENVIO_TRAVADO = 5 * 60  # a try marked as sending this long ago died with the process: it may have gone out
TALVEZ_REPETIDA = "(pode ser repetida) "
DEFINITIVO = re.compile(r"pessoa sem WhatsApp/Telegram|conversa sem dono|arquivo não encontrado|arquivo maior|"
                        r"chat not found|bot was blocked|user is deactivated|bot was kicked|PEER_ID_INVALID|"
                        r"\b1310(?:26|30)\b", re.I)  # Meta: 131026 undeliverable, 131030 number not allowed


def definitivo(erro: str) -> bool:
    return bool(DEFINITIVO.search(str(erro or "")))


@contextlib.contextmanager
def _trava_saida():
    """One writer at a time on SAIDA (the send hook adds while the job loop rewrites)."""
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SAIDA.with_name(SAIDA.name + ".trava"), "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _desistir(item: dict, motivo: str) -> None:
    print(f"whatsapp: gave up resending {item.get('id')} to {(item.get('args') or {}).get('usuario')}: {motivo}", flush=True)
    try:
        _gravar_jsonl(SAIDA_DESISTIDA, _ler_jsonl(SAIDA_DESISTIDA)[-199:] + [{**item, "desistiu_em": time.time(),
                                                                                 "motivo": motivo}])
    except OSError:
        pass


def guardar_saida(args: dict, erro: str, incerto: bool, agora: float | None = None) -> str:
    """Keep a message the bridge did not deliver for another try; returns its id ('' when not retried)."""
    agora = agora or time.time()
    if definitivo(erro) or str(args.get("usuario") or "").startswith("teste_") or not args.get("usuario"):
        print(f"whatsapp: not retrying to {args.get('usuario')!r}: {str(erro)[:200]}", flush=True)
        return ""
    item = {"id": uuid.uuid4().hex[:12], "criado": agora, "proxima": agora + REENVIO_APOS[0], "tentativas": 1,
            "incerto": bool(incerto), "erro": str(erro)[:300], "enviando": 0, "args": args}
    try:
        with _trava_saida():
            _gravar_jsonl(SAIDA, _ler_jsonl(SAIDA) + [item])
    except OSError as exc:
        print(f"whatsapp: message to {args.get('usuario')} not kept for a retry: {exc}", flush=True)
        return ""
    return item["id"]


def proxima_saida() -> float | None:
    """When the next waiting message is due (None: nothing waiting)."""
    vez = [float(i.get("proxima") or 0) for i in _ler_jsonl(SAIDA) if not i.get("enviando")]
    return min(vez) if vez else None


def reenviar_pendentes(agora: float | None = None) -> list[dict]:
    """Try again the waiting messages that are due: [{"id", "resultado": entregue|de_novo|desistiu, "erro"}]."""
    agora = agora or time.time()
    vez = []
    with _trava_saida():
        itens = _ler_jsonl(SAIDA)
        ficam = []
        for i in itens:
            if agora - float(i.get("criado") or 0) > REENVIO_VIDA:
                _desistir(i, "mais de 24 h")
                continue
            if i.get("enviando") and agora - float(i["enviando"]) > REENVIO_TRAVADO:
                i.update(enviando=0, incerto=True)  # the process died during that try: it may have gone out
            if not i.get("enviando") and float(i.get("proxima") or 0) <= agora:
                i["enviando"], i["tentativas"] = agora, int(i.get("tentativas") or 1) + 1
                vez.append(dict(i))
            ficam.append(i)
        if vez or len(ficam) != len(itens):
            _gravar_jsonl(SAIDA, ficam)
    if not vez:
        return []
    resultados = {}
    for i in vez:
        a = dict(i["args"])
        if i.get("incerto"):
            if a.get("texto"):
                a["texto"] = TALVEZ_REPETIDA + a["texto"]
            elif a.get("legenda"):
                a["legenda"] = TALVEZ_REPETIDA + a["legenda"]
        erro, incerto = _postar(_corpo(a["usuario"], a.get("texto") or "", a.get("arquivo") or "", a.get("legenda") or "",
                                       a.get("botoes"), a.get("tipo") or "", a.get("rotina") or "", a.get("app")))
        if not erro and (a.get("tipo") or "resposta") != "resposta" and a.get("texto"):
            _lembrar_aviso(a["usuario"], i["args"]["texto"], _chave_aviso(i["args"]["texto"], a.get("arquivo") or "",
                                                                          a.get("botoes")))
        resultados[i["id"]] = (erro, incerto)
    saida = []
    with _trava_saida():
        ficam = []
        for i in _ler_jsonl(SAIDA):
            if i.get("id") not in resultados:
                ficam.append(i)
                continue
            erro, incerto = resultados[i["id"]]
            if not erro:
                saida.append({"id": i["id"], "resultado": "entregue", "erro": ""})
                continue
            i.update(enviando=0, erro=str(erro)[:300], incerto=bool(i.get("incerto") or incerto))
            if definitivo(erro) or int(i["tentativas"]) >= REENVIO_MAX:
                _desistir(i, "destino inválido" if definitivo(erro) else f"{i['tentativas']} tentativas")
                saida.append({"id": i["id"], "resultado": "desistiu", "erro": erro})
                continue
            i["proxima"] = agora + REENVIO_APOS[min(int(i["tentativas"]) - 1, len(REENVIO_APOS) - 1)]
            saida.append({"id": i["id"], "resultado": "de_novo", "erro": erro})
            ficam.append(i)
        _gravar_jsonl(SAIDA, ficam)
    return saida


async def reenviar_depois(segundos: float) -> list[dict]:
    """Wait, then try the due messages (the job loop runs once a minute; a 30 s retry cannot wait for it)."""
    import asyncio

    await asyncio.sleep(max(0.0, segundos))
    return await asyncio.to_thread(reenviar_pendentes)


# 12/10 review §6 (requests in parallel): one progress message per person that the bridge edits in place (Telegram),
# instead of one "still working" per request every 4 minutes. ANDAMENTO keeps which people have one open (job-loop
# modules reload on every pass: the state lives in a file).
ANDAMENTO = Path("/a0/usr/whatsapp/andamento.json")  # {login: {"em": last update, "n": requests shown, "maximo": most}}


def andamento_aberto() -> dict:
    try:
        return json.loads(ANDAMENTO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar_andamento(dados: dict) -> None:
    ANDAMENTO.parent.mkdir(parents=True, exist_ok=True)
    tmp = ANDAMENTO.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados), encoding="utf-8")
    os.replace(tmp, ANDAMENTO)


def andamento(usuario: str, texto: str, fim: bool = False, n: int = 1) -> str:
    """Show `texto` as the person's single progress message (the bridge edits the open one); `fim` closes it. ''
    when done, else the reason it was not."""
    if not usuario:
        return "conversa sem dono"
    resposta = b""
    if usuario.startswith("teste_"):
        CAIXA_TESTES.parent.mkdir(parents=True, exist_ok=True)
        with CAIXA_TESTES.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"em": time.time(), "usuario": usuario, "texto": texto, "tipo": "andamento", "fim": fim},
                               ensure_ascii=False) + "\n")
        erro = ""
    else:
        req = urllib.request.Request(URL.rsplit("/", 1)[0] + "/andamento",
                                     data=json.dumps({"usuario": usuario, "texto": texto, "fim": fim}).encode(),
                                     headers={"Content-Type": "application/json", "X-Chave": chave()})
        try:
            with _abrir(req, timeout=60) as r:
                resposta = r.read()
            erro = ""
        except Exception as exc:
            erro = str(exc)[:200]
    if not erro:
        dados = andamento_aberto()
        if fim:
            dados.pop(usuario, None)
        else:
            antes = dados.get(usuario) or {}
            dados[usuario] = {"em": time.time(), "n": n, "maximo": max(n, int(antes.get("maximo") or 0))}
            try:  # the bridge edited it: Telegram (an edit does not buzz); WhatsApp can only send new ones
                como = json.loads(resposta or b"{}").get("como")
            except (ValueError, AttributeError):
                como = ""
            if como == "editada" or antes.get("canal") == "telegram":
                dados[usuario]["canal"] = "telegram"
        try:
            _guardar_andamento(dados)
        except OSError as exc:
            print(f"whatsapp: progress state not saved: {exc}", flush=True)
    return erro


def texto_andamento(pedidos: list, agora: float | None = None) -> str:
    """The progress message: `pedidos` = [{"pedido": what was asked, "desde": when, "fazendo": current step}]."""
    agora = agora or time.time()
    minutos = lambda p: max(1, round((agora - float(p.get("desde") or agora)) / 60))  # noqa: E731
    resumo = lambda t: (lambda x: x if len(x) <= 70 else x[:69].rsplit(" ", 1)[0] + "…")(" ".join(str(t or "").split()))  # noqa: E731
    if len(pedidos) == 1:
        p = pedidos[0]
        return (f"⏳ Trabalhando no seu pedido ({minutos(p)} min" + (f" · {p['fazendo']}" if p.get("fazendo") else "") +
                "). Te mando o resultado aqui; esta mensagem se atualiza sozinha (/parar cancela).")
    linhas = [f"⏳ Trabalhando em {len(pedidos)} pedidos (esta mensagem se atualiza sozinha; /parar cancela):"]
    for p in sorted(pedidos, key=lambda x: float(x.get("desde") or 0)):
        linhas.append(f"• «{resumo(p.get('pedido')) or 'pedido'}» — {minutos(p)} min" + (f" · {p['fazendo']}" if p.get("fazendo") else ""))
    return "\n".join(linhas)


ANDAMENTO_PRIMEIRO = 90       # a request answered faster than this gets no progress message at all
ANDAMENTO_ATUALIZA = 2 * 60   # then the message updates every 2 min (edits do not buzz) or when requests come/go


def proximos_andamentos(por_pessoa: dict, abertos: dict, agora: float, resumindo=()) -> list:
    """What the progress loop sends now: [(login, texto, fim, n)]. `por_pessoa`: {login: running requests}
    (see texto_andamento); `abertos`: andamento_aberto(); `resumindo`: people who already get the summaries in new
    messages (helpers/resumo_andamento.py). On WhatsApp every update is a new message (at most one per 4 min), so
    for them the summaries take its place; on Telegram it keeps updating in place, silently, between summaries."""
    saida = []
    for destino, pedidos in por_pessoa.items():
        reg = abertos.get(destino)
        if reg and destino in resumindo and reg.get("canal") != "telegram":
            continue
        if not reg and all(agora - float(x.get("desde") or agora) < ANDAMENTO_PRIMEIRO for x in pedidos):
            continue
        if reg and agora - float(reg.get("em") or 0) < ANDAMENTO_ATUALIZA and int(reg.get("n") or 0) == len(pedidos):
            continue
        saida.append((destino, texto_andamento(pedidos, agora), False, len(pedidos)))
    for destino, reg in abertos.items():
        if destino not in por_pessoa:  # everything answered: the message turns into "done"
            saida.append((destino, texto_andamento_fim(int(reg.get("maximo") or 1)), True, 0))
    return saida


def enviar_resumo(usuario: str, texto: str) -> str:
    """A progress summary in a NEW message (it notifies, unlike the edited progress message). Not "progresso": the
    plugin already held it in quiet hours and /foco (resumo_andamento.em_silencio) and the bridge would only queue it
    for later or count it in the daily ceiling of notices; a summary is worth nothing later. Not kept in AVISOS (the
    chat's context of notices) nor retried: the next summary replaces it."""
    if not usuario:
        return "conversa sem dono"
    if usuario.startswith("teste_"):
        return enviar(usuario, texto, tipo="andamento")
    return _postar(_corpo(usuario, texto, "", "", None, "andamento", "", None))[0]


def texto_andamento_fim(n: int) -> str:
    return ("✅ Terminei os " + str(n) + " pedidos" if n > 1 else "✅ Terminei") + " — as respostas estão aqui na conversa."


AVISOS = Path("/a0/usr/whatsapp/avisos")  # notices sent by rounds/tasks, one .jsonl per person (last 60)
# 12/10 review (first piece of the notices gate, §4.3): the same notice could reach the phone 3-4 times (duplicate
# rounds, a round re-reporting what it already reported). An identical notice (same text, file and buttons) inside
# the window is held, not sent, and logged in <login>.segurados.jsonl. Answers to the person are never held.
REPETIDO_H = {"urgente": 6, "progresso": 12}


def _chave_aviso(texto: str, arquivo: str = "", botoes: list | None = None) -> str:
    base = "|".join([re.sub(r"\s+", " ", (texto or "").strip().lower()), arquivo or "",
                     ",".join(str((b or {}).get("id", "")) for b in botoes or [])])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _ler_jsonl(arq: Path) -> list[dict]:
    try:
        linhas = arq.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    itens = []
    for linha in linhas:
        try:
            itens.append(json.loads(linha))
        except ValueError:
            continue
    return itens


def _gravar_jsonl(arq: Path, itens: list[dict]) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=arq.parent, prefix=f".{arq.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in itens))
        os.chmod(tmp, 0o644)
        os.replace(tmp, arq)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _ja_avisado(usuario: str, marca: str, horas: float) -> bool:
    limite = time.time() - horas * 3600
    return any(i.get("chave") == marca and i.get("em", 0) >= limite for i in _ler_jsonl(AVISOS / f"{usuario}.jsonl"))


def _lembrar_aviso(usuario: str, texto: str, marca: str = "") -> None:
    """Keep what a round sent to the phone: when he answers it in the phone chat, that chat knows what he means
    (and the same notice is not sent twice)."""
    try:
        arq = AVISOS / f"{usuario}.jsonl"
        itens = _ler_jsonl(arq)[-59:] + [{"em": time.time(), "texto": texto[:1500], "chave": marca}]
        _gravar_jsonl(arq, itens)
    except OSError:
        pass


def _segurar(usuario: str, texto: str, tipo: str, motivo: str) -> None:
    try:
        arq = AVISOS / f"{usuario}.segurados.jsonl"
        _gravar_jsonl(arq, _ler_jsonl(arq)[-199:] + [{"em": time.time(), "tipo": tipo, "motivo": motivo,
                                                       "texto": texto[:500]}])
    except OSError:
        pass


def avisos_recentes(usuario: str, horas: float = 24, maximo: int = 6) -> list[dict]:
    limite = time.time() - horas * 3600
    return [i for i in _ler_jsonl(AVISOS / f"{usuario}.jsonl") if i.get("em", 0) >= limite][-maximo:]


def formatar(texto: str) -> str:
    """Agent markdown -> WhatsApp formatting (*bold*, _italic_, ~strike~, ```mono```)."""
    t = texto.replace("\r\n", "\n")
    t = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", t, flags=re.M)          # headings
    t = re.sub(r"\*\*(.+?)\*\*", r"*\1*", t)                         # bold
    t = re.sub(r"(?<![\w*])__(.+?)__(?![\w*])", r"*\1*", t)
    t = re.sub(r"~~(.+?)~~", r"~\1~", t)
    t = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", r"\1", t)                 # images -> path
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", t)  # links
    t = re.sub(r"^\s*[-*]\s+", "• ", t, flags=re.M)                  # bullets
    linhas = []
    for linha in t.split("\n"):                                      # tables -> "a · b · c"
        if re.match(r"^\s*\|?\s*:?-{3,}", linha):
            continue
        if linha.strip().startswith("|") and linha.strip().endswith("|"):
            celulas = [c.strip() for c in linha.strip().strip("|").split("|")]
            linha = " · ".join(c for c in celulas if c)
        linhas.append(linha)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()


def dono(context) -> str:
    """Owner login of a chat, the same rule the per-user separation uses (login_usuarios)."""
    import sys

    sep = sys.modules.get("login_usuarios_separacao")
    try:
        if sep is not None:
            return sep.dono_contexto(context)
        return (context.get_data("dono") or "").lower()
    except Exception:
        return ""


TAREFAS = "/a0/usr/scheduler/tasks.json"
_tarefas = {"mtime": 0.0, "ids": {}}
SILENCIO = "SEM NOVIDADE"  # a scheduled round that answers starting with this is not sent to the phone


def tarefa(context) -> str:
    """Name of the scheduled task this chat runs, or "". The scheduler makes ordinary (USER) chats
    for its tasks, so the context type alone never said it; its task list does."""
    import json
    import os

    try:
        from agent import AgentContextType

        if context.type == AgentContextType.TASK:
            return context.name or "tarefa"
    except Exception:
        pass
    try:
        mtime = os.path.getmtime(TAREFAS)
        if mtime != _tarefas["mtime"]:
            with open(TAREFAS, encoding="utf-8") as f:
                lista = json.load(f).get("tasks", [])
            _tarefas["ids"] = {t.get("context_id") or t.get("uuid"): t.get("name") or "tarefa" for t in lista}
            _tarefas["mtime"] = mtime
    except Exception:
        return ""
    return _tarefas["ids"].get(context.id, "")


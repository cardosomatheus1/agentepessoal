"""The Gestor de conteúdo of @raiz.connect (03/11). Matheus: "To achando que ta faltando um agente gestor tbm, pra
tomar algumas decisões, entender o contexto, ver quando esse tipo de coisa n faz sentido, ser de fato uma
inteligência". His decisions that day: scope "Só o Instagram"; autonomy "Age e avisa".

It is the layer above the rules in conteudo.py: one model call (the especialistas role "gestor", Claude Opus 5.5)
sees the whole calendar (today, the next 7 days and the last 7), states, block reasons, the Crítico's verdicts, redo
attempts, the recent journal, the week proposed, Matheus's decisions and the current offer, and answers with actions
from a CLOSED vocabulary. Code, not the model, decides what is allowed:
- segurar / remarcar / cancelar / trocar / refazer only on items that have not gone out, through the helper's own
  functions (conteudo.segurar, remarcar, cancelar, trocar_datas and semana.refazer_item), AUTOR "gestor: <motivo>",
  every step in the journal;
- never publish, never liberar() a reproved item, never delete what went out, never two of a slot on one day, never
  touch publicando/publicada/incerta/falhou, never change a caption (that only happens through a redo the Crítico
  judges); pedir_ao_matheus is the only way to reach what is his;
- an action outside the vocabulary, or one that breaks a rule, is refused and journaled;
- one message per run, only when it did something or needs him; silence when all is well.
It runs at 08:30, 11:15 and 20:00 and on events (blocked, reproved, a redo that failed, a publish that failed or is
uncertain), from the content routine of the relógio (job_loop _46), never two at once (gestor.lock)."""

import copy
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import re
import time
from pathlib import Path

HORARIOS = ("08:30", "11:15", "20:00")  # before the 9h story, before the 11:45 post, and the evening review
JANELA_HORARIO_MIN = 60  # a fixed run still happens up to this long after its hour (the VM was busy or restarting)
INTERVALO_EVENTO_MIN = 15  # at most one run per this many minutes for events
MAX_POR_DIA = 10  # model calls a day (fixed + events)
TETO_USD = 0.30  # per run: the prompt is trimmed until the worst case (prompt + full answer) fits
TETO_DIA_USD = 2.00
MAX_SAIDA = 8000  # tokens of answer (thinking included)
MAX_ACOES = 6
REFAZ_EXTRA = 1  # redo attempts the Gestor may add on top of conteudo.REFAZER_MAX
FOLGA_REFAZER_MIN = 45  # a redo takes minutes (Designer + Crítico): not when the item goes out sooner than this
DIAS = 7
ACOES = {
    "segurar": {"item"},
    "remarcar": {"item", "data", "hora"},
    "cancelar": {"item"},
    "refazer": {"item", "instrucao"},
    "trocar": {"item_a", "item_b"},
    "pedir_ao_matheus": {"pergunta", "opcoes", "item"},
}
OPCIONAIS = {"pedir_ao_matheus": {"opcoes", "item"}}
NAO_TOCA = ("publicando", "publicada", "incerta", "falhou")
EVENTOS = ("bloqueada", "falhou", "incerta")
ROTINA = "🧭 Gestor de conteúdo"
DIAS_SEMANA = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")

_C: dict = {}


def _irmao(nome: str, chave: str):
    """conteudo.py / semana.py next to this file, re-read when they change (tests pin theirs in _C[chave])."""
    if chave in _C:
        return _C[chave]
    caminho = Path(__file__).resolve().parent / nome
    marca = caminho.stat().st_mtime_ns
    if _C.get(f"marca_{nome}") != marca:
        spec = importlib.util.spec_from_file_location(f"conteudo_gestor_{nome[:-3]}", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _C.update({f"marca_{nome}": marca, f"m_{nome}": m})
    return _C[f"m_{nome}"]


def c():
    return _irmao("conteudo.py", "fixo")


def semana():
    return _irmao("semana.py", "semana_fixa")


def _pasta() -> Path:
    return c().PASTA


def _momento(agora: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(agora, c()._tz())


def _ler_jsonl(arq: Path, ultimas: int = 400) -> list:
    if not arq.exists():
        return []
    saida = []
    for linha in arq.read_text(encoding="utf-8").splitlines()[-ultimas:]:
        try:
            saida.append(json.loads(linha))
        except ValueError:
            continue
    return saida


def _curto(v, n: int = 200) -> str:
    t = " ".join(str(v or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


# ------------------------------------------------------------------ what the Gestor sees

def _assunto(i: dict) -> str:
    return _curto((i.get("origem") or {}).get("titulo") or (i.get("ficha") or {}).get("titulo")
                  or (i.get("ficha") or {}).get("brief") or i.get("legenda"), 160)


def _item(i: dict, agora: float) -> dict:
    conf = i.get("conferido") or {}
    critica = i.get("critica") or {}
    linha = {"id": i["id"], "data": i["data"], "dia": DIAS_SEMANA[dt.date.fromisoformat(i["data"]).weekday()],
             "hora": i["hora"], "tipo": i["tipo"], "canal": c().canal(i), "estado": i["estado"], "assunto": _assunto(i),
             "minutos_ate_sair": int((c()._quando(i) - agora) // 60)}
    if c().canal(i) == "feed":
        linha["legenda"] = _curto(i.get("legenda"), 300)
    if c().chama_post(i):
        linha["anuncia_o_post_do_dia"] = True
    for k in ("bloqueio", "espera_post", "erro", "segurado_por"):
        if i.get(k):
            linha[k] = _curto(i[k], 300)
    if conf.get("veredito"):
        linha["critico_antecipado"] = {"veredito": conf["veredito"], "motivo": _curto(conf.get("motivo"), 400)}
    if critica.get("motivos"):
        linha["critico_na_hora"] = [_curto(m, 300) for m in critica["motivos"][:3]]
    if i.get("refeitas"):
        linha["refeitas"] = int(i["refeitas"])
    if i.get("liberado"):
        linha["liberado_pelo_matheus"] = True
    linha["pode_refazer"] = i["tipo"] != "REELS" and c().tem_ficha(i)
    return linha


def _buracos(itens: list, hoje: dt.date) -> list:
    """Days of the next DIAS with no story, and the plan's feed days (semana.PLANO_FEED) with no feed post."""
    vivos = [i for i in itens if i["estado"] not in ("cancelada", "falhou")]
    plano = {dia for _, dia in semana().PLANO_FEED}
    saida = []
    for k in range(DIAS + 1):
        dia = hoje + dt.timedelta(days=k)
        iso = dia.isoformat()
        if not any(i["data"] == iso and c().canal(i) == "story" for i in vivos):
            saida.append(f"{iso} ({DIAS_SEMANA[dia.weekday()]}): sem story")
        if dia.weekday() in plano and not any(i["data"] == iso and c().canal(i) == "feed" for i in vivos):
            saida.append(f"{iso} ({DIAS_SEMANA[dia.weekday()]}): dia de post no plano e sem post")
    return saida


def _alertas(itens: list, agora: float) -> list:
    """What code can see by itself; the model decides what to do about it."""
    hoje = _momento(agora).date().isoformat()
    saida = []
    for i in itens:
        if i["estado"] == "pendente" and c()._quando(i) < agora - 15 * 60:
            saida.append(f"{i['id']}: era para sair {i['data']} {i['hora']} e continua pendente (rotina parada ou "
                         f"travada?)" + (" e o dia já passou" if i["data"] < hoje else ""))
        if i["estado"] == "bloqueada" and i["data"] < hoje:
            saida.append(f"{i['id']}: bloqueado num dia que já passou ({i['data']})")
        if c().chama_post(i) and i["estado"] in ("pendente", "bloqueada", "publicada"):
            feed = [f for f in itens if f["data"] == i["data"] and c().canal(f) == "feed" and f["estado"] != "cancelada"]
            if not feed:
                saida.append(f"{i['id']}: story que anuncia um post, e {i['data']} não tem post")
            elif all(f["estado"] in ("bloqueada", "falhou") for f in feed):
                saida.append(f"{i['id']}: story que anuncia {feed[0]['id']}, que está {feed[0]['estado']}"
                             + (" (o story JÁ saiu)" if i["estado"] == "publicada" else ""))
    return saida


def _semana_resumo() -> dict | None:
    try:
        s = semana().ultima()
    except Exception as exc:
        return {"erro": f"{type(exc).__name__}: {exc}"[:200]}
    if not s:
        return None
    return {"id": s["id"], "estado": s["estado"], "propostas": [
        {"n": p.get("n"), "formato": p.get("formato_pedido"), "data": p.get("data"), "titulo": _curto(p.get("titulo"), 120),
         "critico": (p.get("critica") or {}).get("veredito"), "estado": p.get("estado"),
         **({"problema": _curto(p["problema"], 160)} if p.get("problema") else {})} for p in s.get("propostas") or []]}


def _diario_recente(agora: float, horas: int = 72, n: int = 60) -> list:
    saida = []
    for e in _ler_jsonl(_pasta() / "diario.jsonl", 600):
        if float(e.get("em") or 0) < agora - horas * 3600:
            continue
        e = {k: (_curto(v, 220) if isinstance(v, str) else v) for k, v in e.items()
             if k not in ("legenda", "critica", "permalink", "media_id")}
        e["em"] = _momento(float(e["em"])).strftime("%d/%m %H:%M")
        saida.append(e)
    return saida[-n:]


def _contexto() -> dict:
    """Matheus's decisions and the Raiz (offer, client, brand) from the especialistas plugin, when installed."""
    esp = c().especialistas()
    if esp is None:
        return {"raiz": "", "decisoes": "", "aviso": "plugin especialistas não instalado"}
    try:
        raiz, nota = esp.contexto_raiz(14000)
    except Exception as exc:
        raiz, nota = "", f"{type(exc).__name__}"
    try:
        dec = esp.decisoes_raiz(7000)
    except Exception:
        dec = ""
    return {"raiz": raiz, "decisoes": dec, **({"aviso": nota} if nota else {})}


def estado(agora: float | None = None, contexto: dict | None = None) -> dict:
    agora = time.time() if agora is None else agora
    momento = _momento(agora)
    hoje = momento.date()
    de, ate = (hoje - dt.timedelta(days=DIAS)).isoformat(), (hoje + dt.timedelta(days=DIAS)).isoformat()
    todos = c().carregar()["itens"]
    itens = [i for i in todos if de <= i["data"] <= ate or (i["estado"] in ("pendente", "bloqueada") and i["data"] < de)]
    itens.sort(key=lambda i: (i["data"], i["hora"]))
    return {
        "agora": momento.strftime("%Y-%m-%d %H:%M") + f" ({DIAS_SEMANA[momento.weekday()]})",
        "plano": "carrossel ter e sex, Reel qua e dom, às 11:45; 1 story por dia às 9h (seg dica; ter/sex chama o "
                 "carrossel; qua/dom chama o Reel; qui bastidor; sáb oferta). Um post e um story por dia, no máximo.",
        "itens": [_item(i, agora) for i in itens],
        "alertas": _alertas(itens, agora),
        "buracos": _buracos(itens, hoje),
        "semana_proposta": _semana_resumo(),
        "diario_recente": _diario_recente(agora),
        "perguntas_abertas": [{k: p[k] for k in ("pergunta", "opcoes", "item") if k in p}
                              for p in _perguntas() if p.get("em", 0) > agora - 48 * 3600],
        "gestor_recente": [{"em": _momento(r["em"]).strftime("%d/%m %H:%M"), "fez": r.get("feitas", [])}
                           for r in _ler_jsonl(_pasta() / "gestor.jsonl", 40) if r.get("feitas") and not r.get("seco")][-8:],
        "contexto": contexto if contexto is not None else _contexto(),
    }


def tarefa(st: dict, motivo: str) -> str:
    ctx = st.get("contexto") or {}
    corpo = {k: v for k, v in st.items() if k != "contexto"}
    return (f"Execução: {motivo}. Agora: {st['agora']} (horário de Brasília).\n\n"
            f"## Agenda e estado (JSON)\n{json.dumps(corpo, ensure_ascii=False, indent=0)}\n\n"
            f"## Decisões do Matheus\n{ctx.get('decisoes') or '(indisponível)'}\n\n"
            f"## Cérebro da Raiz (oferta atual, cliente, marca)\n{ctx.get('raiz') or '(indisponível)'}\n\n"
            "Decida. Responda só o JSON {\"visto\": ..., \"acoes\": [...]}.")


def _custo_max(texto: str) -> float:
    esp = c().especialistas()
    preco = getattr(esp, "PRECO_CLAUDE", {"entrada": 4.0 / 1e6, "saida": 20.0 / 1e6})
    entrada = (len(texto) + 6000) / 3.0  # ~3 letters per token in Portuguese JSON, plus the role text
    return entrada * preco["entrada"] + MAX_SAIDA * preco["saida"]


def tarefa_no_teto(st: dict, motivo: str) -> str:
    """The prompt, trimmed (journal, then Raiz, then decisions) until its worst case fits TETO_USD."""
    st = copy.deepcopy(st)
    texto = tarefa(st, motivo)
    for corte in ("diario_recente", "raiz", "decisoes", "diario_recente"):
        if _custo_max(texto) <= TETO_USD:
            break
        if corte == "diario_recente":
            st["diario_recente"] = st["diario_recente"][-max(5, len(st["diario_recente"]) // 3):]
        else:
            st["contexto"][corte] = str(st["contexto"].get(corte) or "")[:3000]
        texto = tarefa(st, motivo)
    return texto


# ------------------------------------------------------------------ closed vocabulary

def _ids(acao: dict) -> list:
    return [acao[k] for k in ("item", "item_a", "item_b") if acao.get(k)]


def _perguntas() -> list:
    arq = _pasta() / "gestor_perguntas.json"
    try:
        return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else []
    except ValueError:
        return []


def _mesma(a: str, b: str) -> bool:
    norm = lambda t: re.sub(r"\W+", " ", str(t).lower()).strip()  # noqa: E731
    return norm(a) == norm(b)


def validar(acoes, itens: list, agora: float) -> tuple[list, list]:
    """(accepted, refused) from the model's list. Each is checked against a copy of the calendar with the accepted
    ones before it applied, so two actions can never put two items on one day. Refused: {"acao", "erro"}."""
    if not isinstance(acoes, list):
        return [], [{"acao": acoes, "erro": "acoes não é uma lista"}]
    sim = {i["id"]: dict(i) for i in copy.deepcopy(itens)}
    tocados, aceitas, recusadas = set(), [], []
    abertas = [p for p in _perguntas() if p.get("em", 0) > agora - 24 * 3600]

    def ocupado(data, canal_, exceto):
        return next((i for i in sim.values() if i["id"] not in exceto and i["data"] == data and c().canal(i) == canal_
                     and i["estado"] not in ("cancelada", "falhou")), None)

    for a in acoes:
        erro = _erro(a, sim, tocados, abertas, ocupado, agora, len(aceitas))
        if erro:
            recusadas.append({"acao": a, "erro": erro})
            continue
        nome = a["acao"]
        if nome == "segurar":
            sim[a["item"]]["estado"] = "bloqueada"
        elif nome == "cancelar":
            sim[a["item"]]["estado"] = "cancelada"
        elif nome == "remarcar":
            sim[a["item"]].update(data=a["data"], hora=a["hora"])
        elif nome == "trocar":
            x, y = sim[a["item_a"]], sim[a["item_b"]]
            (x["data"], x["hora"]), (y["data"], y["hora"]) = (y["data"], y["hora"]), (x["data"], x["hora"])
        tocados.update(_ids(a) + (["pergunta"] if nome == "pedir_ao_matheus" else []))
        aceitas.append({k: (v.strip() if isinstance(v, str) else v) for k, v in a.items()})
    return aceitas, recusadas


def _erro(a, sim: dict, tocados: set, abertas: list, ocupado, agora: float, ja: int) -> str:
    if not isinstance(a, dict):
        return "ação não é um objeto"
    nome = a.get("acao")
    if nome not in ACOES:
        return f"ação fora do vocabulário: {str(nome)[:40]!r} (só {', '.join(sorted(ACOES))})"
    sobra = set(a) - ACOES[nome] - {"acao", "motivo"}
    if sobra:
        return f"{nome}: campos que não existem: {', '.join(sorted(map(str, sobra)))}"
    falta = ACOES[nome] - OPCIONAIS.get(nome, set()) - set(a)
    if falta:
        return f"{nome}: falta {', '.join(sorted(falta))}"
    if not isinstance(a.get("motivo"), str) or not a["motivo"].strip():
        return f"{nome}: sem motivo"
    if ja >= MAX_ACOES:
        return f"mais de {MAX_ACOES} ações numa execução"
    for k in ("item", "item_a", "item_b"):
        if k in a and a[k] is not None and (not isinstance(a[k], str) or a[k] not in sim):
            return f"{nome}: o item {str(a[k])[:60]!r} não existe na agenda"
    if any(i in tocados for i in _ids(a)):
        return f"{nome}: o mesmo item já tem outra ação nesta execução"
    if nome == "pedir_ao_matheus":
        if not isinstance(a.get("pergunta"), str) or not a["pergunta"].strip():
            return "pedir_ao_matheus: sem pergunta"
        opcoes = a.get("opcoes", [])
        if not isinstance(opcoes, list) or len(opcoes) > 3 or not all(isinstance(o, str) and o.strip() for o in opcoes):
            return "pedir_ao_matheus: opcoes é uma lista de até 3 textos"
        if any(_mesma(p.get("pergunta"), a["pergunta"]) for p in abertas):
            return "pedir_ao_matheus: a mesma pergunta já foi feita nas últimas 24 h"
        if "pergunta" in tocados:
            return "pedir_ao_matheus: uma pergunta por execução (a mensagem fica curta e os botões claros)"
        return ""
    for i in _ids(a):
        if sim[i]["estado"] in NAO_TOCA:
            return f"{nome}: {i} está {sim[i]['estado']} (o gestor não mexe no que saiu ou está saindo)"
    it = sim.get(a.get("item") or a.get("item_a"))
    if nome == "cancelar":
        return "" if it["estado"] in ("pendente", "bloqueada") else f"cancelar: {it['id']} está {it['estado']}"
    if it["estado"] != "pendente":
        return f"{nome}: {it['id']} está {it['estado']} (só pendente)"
    if nome == "segurar":
        return ""
    if nome == "remarcar":
        try:
            dt.date.fromisoformat(str(a["data"]))
        except ValueError:
            return "remarcar: data (AAAA-MM-DD) inválida"
        if not c()._hora_valida(a["hora"]):
            return "remarcar: hora (HH:MM) inválida"
        if c()._quando({"data": a["data"], "hora": a["hora"]}) < agora + c().MARGEM_MIN * 60:
            return f"remarcar: {a['data']} {a['hora']} já passou ou está perto demais"
        outro = ocupado(a["data"], c().canal(it), {it["id"]})
        return f"remarcar: {a['data']} já tem {c().canal(it)} ({outro['id']}): um por dia" if outro else ""
    if nome == "refazer":
        if not isinstance(a.get("instrucao"), str) or len(a["instrucao"].strip()) < 10:
            return "refazer: sem instrução clara do que mudar"
        if it["tipo"] == "REELS":
            return "refazer: Reel muda a narração, que precisa do ok do Matheus (decisão #39); use pedir_ao_matheus"
        if not c().tem_ficha(it):
            return f"refazer: {it['id']} não tem ficha para ser refeito"
        if int(it.get("refeitas") or 0) >= c().REFAZER_MAX + REFAZ_EXTRA:
            return f"refazer: {it['id']} já foi refeito {it.get('refeitas')} vezes"
        if c()._quando(it) < agora + FOLGA_REFAZER_MIN * 60:
            return f"refazer: {it['id']} sai em menos de {FOLGA_REFAZER_MIN} min, não dá tempo"
        return ""
    if nome == "trocar":
        b = sim[a["item_b"]]
        if b["estado"] != "pendente":
            return f"trocar: {b['id']} está {b['estado']} (só pendente)"
        if c().canal(it) != c().canal(b):
            return "trocar: um é story e o outro é post: só no mesmo canal"
        if min(c()._quando(it), c()._quando(b)) < agora + c().MARGEM_MIN * 60:
            return "trocar: um dos dois sai em minutos"
        return ""
    return "ação sem regra"


# ------------------------------------------------------------------ doing it

def _descrever(a: dict, itens: dict) -> str:
    nome = a["acao"]
    rotulo = lambda i: f"{i} ({itens[i]['tipo'].lower()}, {itens[i]['data'][8:]}/{itens[i]['data'][5:7]} {itens[i]['hora']})"  # noqa: E731
    if nome == "segurar":
        return f"Segurei {rotulo(a['item'])}"
    if nome == "cancelar":
        return f"Cancelei {rotulo(a['item'])}"
    if nome == "remarcar":
        return f"Remarquei {rotulo(a['item'])} para {a['data'][8:]}/{a['data'][5:7]} às {a['hora']}"
    if nome == "trocar":
        return f"Troquei as datas de {rotulo(a['item_a'])} e {rotulo(a['item_b'])}"
    if nome == "refazer":
        return f"Mandei refazer {rotulo(a['item'])}"
    return nome


def _critica_com_instrucao(item: dict, instrucao: str) -> dict:
    motivos = list((item.get("critica") or {}).get("motivos") or [])
    conf = (item.get("conferido") or {}).get("motivo")
    if conf and conf not in motivos:
        motivos.append(conf)
    return {"veredito": "reprova", "motivos": motivos + [f"Instrução do gestor: {instrucao}"], "sugestoes": []}


def executar(a: dict, refazer=None, agora: float | None = None) -> dict:
    """One accepted action through the helper's own functions, as "gestor: <motivo>"."""
    conteudo = c()
    antes = conteudo.AUTOR["quem"]
    conteudo.AUTOR["quem"] = f"gestor: {_curto(a['motivo'], 150)}"
    try:
        nome = a["acao"]
        if nome == "segurar":
            return conteudo.segurar(a["item"], a["motivo"])
        if nome == "cancelar":
            return conteudo.cancelar(a["item"], "gestor: " + a["motivo"])
        if nome == "remarcar":
            return conteudo.remarcar(a["item"], a["data"], a["hora"], a["motivo"], agora)
        if nome == "trocar":
            return conteudo.trocar_datas(a["item_a"], a["item_b"], a["motivo"], agora)
        if nome == "refazer":
            item = next((i for i in conteudo.carregar()["itens"] if i["id"] == a["item"]), None)
            if not item or item["estado"] != "pendente":
                return {"ok": False, "erro": f"{a['item']}: não está mais pendente"}
            feitas = int(item.get("refeitas") or 0)
            try:
                r = (refazer or semana().refazer_item)(item, _critica_com_instrucao(item, a["instrucao"]))
            except Exception as exc:
                r = {"ok": False, "erro": f"{type(exc).__name__}: {str(exc)[:160]}"}
            conteudo._anotar(a["item"], {"refazer": bool(r.get("ok")), "tentativa": feitas + 1, "pelo_gestor": True,
                                         **({} if r.get("ok") else {"erro": _curto(r.get("erro"), 200)})},
                             refeitas=feitas + 1)
            return r
        return {"ok": False, "erro": "ação sem execução"}
    finally:
        conteudo.AUTOR["quem"] = antes


def _pergunta(a: dict, agora: float, itens: dict) -> tuple[str, list]:
    """The question text and its buttons: "Publicar mesmo assim" for a reproved/blocked item (the existing button),
    and one button per option that hands his choice to the agent in his chat (semana.botao, acao g<k>)."""
    gid = "g" + hashlib.sha256(f"{a['pergunta']}{agora}".encode()).hexdigest()[:8]
    registro = {"id": gid, "em": agora, "pergunta": a["pergunta"], "opcoes": a.get("opcoes") or [],
                **({"item": a["item"]} if a.get("item") else {})}
    lista = [p for p in _perguntas() if p.get("em", 0) > agora - 7 * 86400] + [registro]
    arq = _pasta() / "gestor_perguntas.json"
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)
    login = c().LOGIN
    botoes = []
    it = itens.get(a.get("item") or "")
    hoje = _momento(agora).date().isoformat()  # liberar a past day's item would publish nothing
    if it and it["data"] >= hoje and (it["estado"] == "bloqueada" or (it.get("conferido") or {}).get("veredito") == "reprova"):
        botoes.append({"id": f"cs:{login}:{it['id']}:liberar", "titulo": "🔓 Publicar mesmo assim"})
    for k, o in enumerate(registro["opcoes"], 1):
        if len(botoes) < 3:
            botoes.append({"id": f"cs:{login}:{gid}:o{k}", "titulo": _curto(o, 30)})
    botoes = [b for b in botoes if len(b["id"].encode()) <= 64]
    texto = a["pergunta"].strip() + ("\n" + "\n".join(f"{k}) {o}" for k, o in enumerate(registro["opcoes"], 1))
                                     if registro["opcoes"] else "")
    return texto, botoes


def resposta(gid: str, k: int) -> dict:
    """His button on a Gestor question: the question and the option, for the agent to act on in his chat."""
    p = next((x for x in _perguntas() if x.get("id") == gid), None)
    if not p or not 1 <= k <= len(p.get("opcoes") or []):
        return {}
    c()._diario({"gestor": "resposta", "pergunta": _curto(p["pergunta"], 200), "escolha": p["opcoes"][k - 1]})
    return {"conversa": (f"🧭 Sobre a pergunta do gestor de conteúdo: \"{p['pergunta']}\"\nEu escolho: {p['opcoes'][k - 1]}"
                         + (f" (item {p['item']})" if p.get("item") else "")
                         + "\n\nFaça isso com a ferramenta `conteudo` (agenda, semana, liberar) e me diga em uma linha o "
                           "que ficou.")}


def _mensagem(visto: str, feitos: list, falhas: list, perguntas: list) -> tuple[str, list]:
    if not feitos and not perguntas:
        return "", []
    linhas = [f"🧭 Gestor de conteúdo: {visto.strip()}" if visto.strip() else "🧭 Gestor de conteúdo"]
    for desc, motivo in feitos:
        linhas.append(f"- {desc}. Por quê: {motivo}")
    for desc, erro in falhas:
        linhas.append(f"- Tentei: {desc.lower()}, não deu ({_curto(erro, 120)}).")
    botoes = []
    for texto, b in perguntas:
        linhas.append(f"Preciso de você: {texto}")
        botoes += b
    return "\n".join(linhas), botoes[:3]


# ------------------------------------------------------------------ when and the whole run

def _estado_arq() -> Path:
    return _pasta() / "gestor_estado.json"


def _ler_estado() -> dict:
    try:
        return json.loads(_estado_arq().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_estado(e: dict) -> None:
    tmp = _estado_arq().with_suffix(".tmp")
    tmp.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_estado_arq())


def _eventos_novos(desde: float) -> list:
    """Journal events that call for a look (not the Gestor's own): blocked, failed, uncertain, reproved, redo failed."""
    saida = []
    for e in _ler_jsonl(_pasta() / "diario.jsonl", 300):
        if float(e.get("em") or 0) <= desde or str(e.get("quem", "")).startswith("gestor:"):
            continue
        if e.get("para") in EVENTOS or e.get("conferido") == "reprova" or e.get("refazer") is False:
            tipo = e.get("para") or ("reprovado" if e.get("conferido") else "refazer falhou")
            saida.append({"em": float(e["em"]), "texto": f"{e.get('item')} {tipo}"})
    return saida


def quando_rodar(agora: float | None = None) -> str:
    """Why to run now ("" = not now): a fixed hour not yet run today, or new events (spaced INTERVALO_EVENTO_MIN).
    Cheap: no model, no network."""
    agora = time.time() if agora is None else agora
    if not (_pasta() / "agenda.json").exists():
        return ""
    e = _ler_estado()
    if "evento_em" not in e:  # first time: old history is not news
        _gravar_estado({"evento_em": agora, "feitos": []})
        e = _ler_estado()
    momento = _momento(agora)
    hoje, hora = momento.date().isoformat(), momento.strftime("%H:%M")
    for h in HORARIOS:
        fim = (dt.datetime.strptime(h, "%H:%M") + dt.timedelta(minutes=JANELA_HORARIO_MIN)).strftime("%H:%M")
        if h <= hora < fim and f"{hoje} {h}" not in e.get("feitos", []):
            return f"horário {h}"
    novos = _eventos_novos(float(e.get("evento_em") or 0))
    if novos and agora - float(e.get("ultimo_evento_run") or 0) >= INTERVALO_EVENTO_MIN * 60:
        return "evento: " + "; ".join(n["texto"] for n in novos[:4])
    return ""


def _marcar(motivo: str, agora: float) -> None:
    e = _ler_estado()
    momento = _momento(agora)
    if motivo.startswith("horário "):
        e["feitos"] = [f for f in e.get("feitos", []) if f >= (momento.date() - dt.timedelta(days=2)).isoformat()] + [
            f"{momento.date().isoformat()} {motivo.split()[1]}"]
    novos = _eventos_novos(float(e.get("evento_em") or 0))
    if novos:
        e["evento_em"] = max(n["em"] for n in novos)
    if motivo.startswith("evento"):
        e["ultimo_evento_run"] = agora
    _gravar_estado(e)


def _do_dia(agora: float) -> tuple[int, float]:
    hoje = _momento(agora).date().isoformat()
    runs = [r for r in _ler_jsonl(_pasta() / "gestor.jsonl", 200)
            if not r.get("seco") and r.get("uso") and _momento(float(r["em"])).date().isoformat() == hoje]
    return len(runs), sum(float((r.get("uso") or {}).get("usd") or 0) for r in runs)


def rodar(motivo: str = "manual", agora: float | None = None, seco: bool = False, modelo=None, avisar=None,
          refazer=None, contexto: dict | None = None) -> dict:
    """One run. seco=True decides and shows, executing and sending nothing. modelo(tarefa) -> {"texto","erro","uso"}
    (default: the especialistas role "gestor"); avisar(texto, botoes); refazer(item, critica) as semana.refazer_item."""
    agora = time.time() if agora is None else agora
    _pasta().mkdir(parents=True, exist_ok=True)
    trava = open(_pasta() / "gestor.lock", "a")
    try:
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        trava.close()
        return {"pulou": "outro gestor está rodando"}
    try:
        if not seco:
            _marcar(motivo, agora)
            n, gasto = _do_dia(agora)
            if n >= MAX_POR_DIA or gasto >= TETO_DIA_USD:
                r = {"pulou": f"teto do dia ({n} execuções, US$ {gasto:.2f})"}
                _registrar(agora, motivo, seco, r)
                return r
        st = estado(agora, contexto)
        texto = tarefa_no_teto(st, motivo)
        if modelo is None:
            esp = c().especialistas()
            if esp is None or not hasattr(esp, "chamar_claude"):
                r = {"erro": "o plugin especialistas (papel gestor) não está instalado"}
                _registrar(agora, motivo, seco, r)
                return r
            modelo = lambda t: esp.chamar_claude("gestor", t, max_saida=MAX_SAIDA)  # noqa: E731
        resp = modelo(texto) or {}
        uso = resp.get("uso") or {}
        dados = None
        if not resp.get("erro"):
            achado = re.search(r"\{.*\}", resp.get("texto") or "", re.S)
            try:
                dados = json.loads(achado.group(0)) if achado else None
            except ValueError:
                dados = None
        if not isinstance(dados, dict) or not isinstance(dados.get("acoes"), list):
            r = {"erro": resp.get("erro") or "resposta ilegível do modelo (nada foi feito)", "uso": uso,
                 "texto": _curto(resp.get("texto"), 300)}
            _registrar(agora, motivo, seco, r)
            return r
        itens = {i["id"]: i for i in c().carregar()["itens"]}
        aceitas, recusadas = validar(dados["acoes"], list(itens.values()), agora)
        visto = _curto(dados.get("visto"), 400) if isinstance(dados.get("visto"), str) else ""
        for x in recusadas:
            c()._diario({"gestor": "recusada", "acao": _curto(json.dumps(x["acao"], ensure_ascii=False), 300),
                         "erro": x["erro"]})
        feitos, falhas, perguntas, resultados = [], [], [], []
        for a in aceitas:
            if a["acao"] == "pedir_ao_matheus":
                if seco:
                    perguntas.append((a["pergunta"] + (" | " + " / ".join(a.get("opcoes") or []) if a.get("opcoes") else ""), []))
                else:
                    perguntas.append(_pergunta(a, agora, itens))
                    c()._diario({"gestor": "perguntou", "pergunta": _curto(a["pergunta"], 300), "motivo": _curto(a["motivo"], 200)})
                resultados.append({"acao": a, "ok": True})
                continue
            desc = _descrever(a, itens)
            if seco:
                feitos.append((desc, a["motivo"]))
                resultados.append({"acao": a, "ok": None})
                continue
            r = executar(a, refazer, agora)
            resultados.append({"acao": a, "ok": bool(r.get("ok")), **({} if r.get("ok") else {"erro": r.get("erro")})})
            (feitos.append((desc, a["motivo"])) if r.get("ok") else falhas.append((desc, str(r.get("erro")))))
        mensagem, botoes = _mensagem(visto, feitos, falhas, perguntas)
        avisou = ""
        if mensagem and not seco and avisar is not None:
            c()._chamar_aviso(avisar, mensagem, botoes)
            avisou = "sim"
        r = {"visto": visto, "aceitas": aceitas, "recusadas": recusadas, "resultados": resultados, "uso": uso,
             "mensagem": mensagem, "botoes": botoes, "avisou": avisou}
        _registrar(agora, motivo, seco, r)
        return r
    finally:
        fcntl.flock(trava, fcntl.LOCK_UN)
        trava.close()


def _registrar(agora: float, motivo: str, seco: bool, r: dict) -> None:
    linha = {"em": agora, "motivo": motivo, "seco": seco, **{k: r[k] for k in ("pulou", "erro", "visto", "uso", "avisou")
                                                            if r.get(k)}}
    if r.get("resultados") is not None:
        linha["feitas"] = [{"acao": x["acao"]["acao"], "itens": _ids(x["acao"]), "ok": x["ok"],
                            "motivo": _curto(x["acao"].get("motivo"), 160)} for x in r["resultados"]]
        linha["recusadas"] = [_curto(x["erro"], 160) for x in r.get("recusadas") or []]
    with open(_pasta() / "gestor.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    if not seco:
        c()._diario({"gestor": "rodou", "motivo": _curto(motivo, 160), "acoes": len(linha.get("feitas") or []),
                     "recusadas": len(linha.get("recusadas") or []),
                     "usd": (r.get("uso") or {}).get("usd"), **({"erro": _curto(r["erro"], 200)} if r.get("erro") else {})})

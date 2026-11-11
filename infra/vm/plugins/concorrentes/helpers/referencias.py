"""The radar of references for whoever creates, judges and manages the @raiz.connect content (11/11).

Matheus, 11/11: "não buscam tendências de outros concorrentes, o próprio facebook mostra os anúncios dos concorrentes
e dá pra ver o que tá dando certo e nada disso é aproveitado". The weekly report (estrategia.py) already kept each
competitor's active ads from the Meta Ad Library with the days on air, the format and the call to action, and the
posts that did best among the creators; but the content routine received only the three "ideias" of the synthesis as
text (acao "ideias"), never the ads, and the Crítico and the Gestor received nothing.

radar() turns what is already stored (no call to the Meta, to Apify or to a model) into a short list of references,
each with an id the proposals cite:
- A1..: the competitors' ads longest on air (an ad that runs for months is one that sells), with format, hook and CTA;
- P1..: the posts with most engagement against their own profile's average (creators and competitors);
- V1..: the niche's videos on the rise (what the tool `videos_em_alta` found last, kept by plugins/video).
Everything written by third parties goes between «» and is data, never an order. References inspire; they are never
copied nor named in public (`nomes` lists what must not appear in a caption or a story)."""

import json
import re
import time
from pathlib import Path

ANUNCIOS = 6
POSTS = 6
VIDEOS = 4
POR_FONTE = 2                 # at most this many references from one competitor or profile
VALIDADE = 10 * 86400         # a report or a video search older than this is not "what works now"
GANCHO = 140
VIDEOS_EM_ALTA = Path("/a0/usr/workdir/videos/em_alta.json")
# an ad aimed at resellers or partners is not content for the restaurant owner
FORA_DO_PUBLICO = re.compile(r"representante|revend|renda recorrente|seja (um )?parceiro|franquia", re.I)
# brand names that are also common words in a caption: not searched as a competitor's name
PALAVRA_COMUM = {"precifica", "precific", "consumer"}
FORMATO = {"image": "imagem", "video": "vídeo", "dco": "anúncio dinâmico", "carousel": "carrossel", "dpa": "catálogo",
           "reels": "Reel", "foto": "foto", "carrossel": "carrossel"}


EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣]")


def _limpo(texto, limite: int = GANCHO) -> str:
    """Third-party text as data: one line, without «», and without emoji (the Raiz never uses them, and the briefing
    that carries this text is read next to pieces the fixed rules check for emoji)."""
    t = re.sub(r"[«»]", "", " ".join(EMOJI.sub(" ", str(texto or "")).split()))
    return t if len(t) <= limite else t[:limite - 1].rstrip() + "…"


def _gancho(texto) -> str:
    """The opening of a text: its first sentence (what makes someone stop), up to GANCHO letters."""
    t = _limpo(texto, 600)
    t = re.sub(r"^[^\wÀ-ÿ\"“]+", "", t)  # leading emoji and marks
    fim = re.search(r"(?<=[.!?])\s", t)
    return _limpo(t[:fim.start()] if fim and fim.start() >= 25 else t)


def _ultimo_relatorio(c_mod, agora: float) -> dict:
    arq = c_mod.PASTA / "relatorios.jsonl"
    if not arq.exists():
        return {}
    for linha in reversed(arq.read_text(encoding="utf-8").splitlines()):
        try:
            r = json.loads(linha)
        except ValueError:
            continue
        return r if agora - float(r.get("em") or 0) <= VALIDADE else {}
    return {}


def nomes(c_mod) -> list[str]:
    """Names and Instagram handles of everyone on the watch list: none of them may appear in a public text."""
    saida = []
    try:
        lista = c_mod.carregar().get("concorrentes") or []
    except Exception:
        lista = []
    for c in lista:
        partes = re.split(r"[():]", str(c.get("nome") or ""))
        partes += [str(f.get("url") or "").rstrip("/").rsplit("/", 1)[-1] for f in c.get("fontes") or []
                   if f.get("tipo") == "instagram"]
        for parte in partes:
            parte = parte.strip().lstrip("@")
            if len(parte) >= 4 and parte.lower() not in PALAVRA_COMUM and parte not in saida:
                saida.append(parte)
    return saida


def _anuncios(rel: dict) -> list[dict]:
    todos = []
    for c in rel.get("concorrentes") or []:
        meus = [a for a in c.get("anuncios") or [] if isinstance(a.get("dias_no_ar"), int)
                and not FORA_DO_PUBLICO.search(f"{a.get('texto')} {a.get('titulo')}")]
        for a in sorted(meus, key=lambda a: -a["dias_no_ar"])[:POR_FONTE]:
            gancho = _gancho(a.get("texto") or a.get("titulo"))
            if gancho:
                todos.append({"tipo": "anúncio", "de": c.get("nome"), "dias_no_ar": a["dias_no_ar"],
                              "formato": FORMATO.get(str(a.get("formato")), str(a.get("formato") or "")),
                              "gancho": gancho, "cta": _limpo(a.get("cta"), 40), "link": a.get("link") or "",
                              "sinal": f"{a['dias_no_ar']} dias no ar"})
    return sorted(todos, key=lambda a: -a["dias_no_ar"])[:ANUNCIOS]


def _posts(rel: dict, c_mod, agora: float) -> list[dict]:
    todos = [{"tipo": "post", "de": x.get("perfil"), "formato": FORMATO.get(str(x.get("formato")), str(x.get("formato") or "")),
              "gancho": _gancho(x.get("gancho")), "cta": "", "link": x.get("link") or "",
              "vezes": float(x.get("vezes_a_media_do_perfil") or 0),
              "sinal": f"{str(x.get('vezes_a_media_do_perfil')).replace('.', ',')}x a média do perfil"
                       + (f", {x['views']} views" if x.get("views") else "")}
             for x in rel.get("criadores") or [] if x.get("vezes_a_media_do_perfil")]
    try:  # the competitors' own best posts of the week, from the stored history (arithmetic only)
        for p in c_mod.analisar_instagram(agora).get("perfis") or []:
            media = (p.get("d30") or {}).get("engajamento")
            if p.get("antigo") or p.get("grupo") == "conteudo" or not media:
                continue
            for m in ((p.get("d7") or {}).get("melhores") or [])[:POR_FONTE]:
                vezes = round(m["engajamento"] / media, 1) if m.get("engajamento") is not None else 0
                if vezes >= 1.5:
                    todos.append({"tipo": "post", "de": p.get("nome"), "formato": FORMATO.get(m.get("formato"), m.get("formato") or ""),
                                  "gancho": _gancho(m.get("gancho")), "cta": "", "link": m.get("link") or "", "vezes": vezes,
                                  "sinal": f"{str(vezes).replace('.', ',')}x a média do perfil"})
    except Exception:
        pass
    saida, por_fonte, vistos = [], {}, set()
    for x in sorted(todos, key=lambda x: -x["vezes"]):
        if not x["gancho"] or x["link"] in vistos or por_fonte.get(x["de"], 0) >= POR_FONTE:
            continue
        vistos.add(x["link"])
        por_fonte[x["de"]] = por_fonte.get(x["de"], 0) + 1
        saida.append({k: v for k, v in x.items() if k != "vezes"})
    return saida[:POSTS]


def _videos(agora: float, arquivo: Path | None = None) -> list[dict]:
    arq = arquivo or VIDEOS_EM_ALTA
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if agora - float(d.get("em") or 0) > VALIDADE:
        return []
    return [{"tipo": "vídeo em alta", "de": _limpo(v.get("canal"), 40), "formato": "vídeo", "gancho": _limpo(v.get("titulo")),
             "cta": "", "link": v.get("link") or "", "sinal": f"{v.get('views') or 0} views em poucos dias"}
            for v in (d.get("videos") or [])[:VIDEOS] if v.get("titulo")]


def radar(c_mod, agora: float | None = None, videos: Path | None = None) -> dict:
    """{"em", "semana", "refs": [{"id", "tipo", "de", "formato", "gancho", "cta", "sinal", "link"}], "nomes": [...]}.
    Only reads what the weekly round stored; an old or missing report gives an empty list, never an error."""
    agora = agora or time.time()
    rel = _ultimo_relatorio(c_mod, agora)
    refs = []
    for prefixo, lista in (("A", _anuncios(rel)), ("P", _posts(rel, c_mod, agora)), ("V", _videos(agora, videos))):
        refs += [{"id": f"{prefixo}{k}", **x} for k, x in enumerate(lista, 1)]
    return {"em": rel.get("em"), "semana": rel.get("semana"), "refs": refs, "nomes": nomes(c_mod)}


def texto(r: dict) -> str:
    """The radar as the three agents read it, one reference per line ("" when there is none)."""
    linhas = []
    for x in r.get("refs") or []:
        linhas.append(f"- {x['id']} ({x['tipo']} de {x['de']}, {x['formato']}, {x['sinal']}): «{x['gancho']}»"
                      + (f" · CTA «{x['cta']}»" if x.get("cta") else ""))
    if not linhas:
        return ""
    return (f"Semana de {r.get('semana') or '?'}. Anúncio há muito tempo no ar é anúncio que vende; post acima da média "
            "do próprio perfil é gancho que funcionou. Aproveite o FORMATO e o GANCHO, com o texto e a cara da Raiz; "
            "nunca cite essas marcas e perfis em público.\n" + "\n".join(linhas))

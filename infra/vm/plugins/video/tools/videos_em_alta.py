"""The most-watched YouTube videos of the last hours (default 48: today and yesterday) on a topic, each watched whole by Gemini from its link (nothing downloaded).

A daily "10 top AI videos of the last 24 h" bulletin found one candidate: web search cannot filter
by upload date. YouTube's own search can ("today", sorted by views); this tool runs it for several
queries, keeps the videos that are really about the topic (the model filters the noise), confirms
each upload time, and has Gemini watch the chosen ones in parallel.
"""

import asyncio
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from helpers.tool import Response, Tool

# YouTube search filters, sorted by views, type video: upload date today / this week (the window is then cut by
# the real upload time, so "today + yesterday" is not limited to the calendar day YouTube calls today)
FILTROS = {"hoje": "CAMSBAgCEAE%3D",           # today, by views
           "semana": "CAMSBAgDEAE%3D",         # this week, by views (older videos dominate)
           "recentes": "CAISBAgDEAE%3D"}       # this week, newest first: fills today and yesterday
PARALELO = 10  # Gemini calls only: nothing runs on the VM


def _video():
    nome = "video_assistir_video"
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, Path(__file__).with_name("assistir_video.py"))
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _ytdlp(*args: str, timeout: int = 120) -> str:
    v = _video()
    r = subprocess.run([*v.YTDLP, "--cookies-from-browser", f"chromium:{v.PERFIL}", *args],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout


def buscar(consulta: str, filtro: str, limite: int = 30) -> list[dict]:
    url = (f"https://www.youtube.com/results?search_query={urllib.parse.quote(consulta)}"
           f"&sp={FILTROS[filtro]}")
    try:
        dados = json.loads(_ytdlp("--flat-playlist", "--playlist-end", str(limite), "-J", url) or "{}")
    except (ValueError, subprocess.TimeoutExpired):
        return []
    return [{"id": e["id"], "titulo": e.get("title") or "", "canal": e.get("channel") or "",
             "views": e.get("view_count") or 0, "duracao": e.get("duration") or 0}
            for e in dados.get("entries") or [] if e.get("id")]


def detalhes(vid: str) -> dict:
    try:
        d = json.loads(_ytdlp("--skip-download", "-j", "--no-warnings", f"https://www.youtube.com/watch?v={vid}", timeout=90) or "{}")
    except (ValueError, subprocess.TimeoutExpired):
        return {}
    ts = d.get("timestamp") or d.get("release_timestamp")
    return {"publicado": ts, "views": d.get("view_count"), "curtidas": d.get("like_count"), "duracao": d.get("duration"),
            "descricao": (d.get("description") or "")[:600]}


def escolher(tema: str, candidatos: list[dict], quantidade: int) -> list[str]:
    v = _video()
    lista = "\n".join(f"{c['id']} | {c['views']} views | {int(c['duracao'] // 60)} min | {c['canal']} | {c['titulo']}"
                      for c in candidatos)
    texto = (f"Tema: {tema}\n\nVídeos recentes do YouTube (id | visualizações | duração | canal | título). Marque TODOS "
             "os que são DE FATO sobre o tema (novidades, lançamentos, notícias, análises) — descarte política, "
             "entretenimento, vídeos fora do tema, Shorts de menos de 2 min e vídeos que não sejam em português ou inglês "
             "(pelo título/canal). Responda só com os ids, um por linha, "
             "na ordem da lista.\n\n" + lista)
    corpo = {"model": v.MODELO, "reasoning": {"effort": "low"},
             "input": [{"role": "user", "content": [{"type": "input_text", "text": texto}]}]}
    import urllib.request

    req = urllib.request.Request(v.URL, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        dados = json.loads(r.read())
    saida = "".join(c.get("text", "") for item in dados.get("output", []) if item.get("type") == "message"
                    for c in item.get("content", []) if c.get("type") == "output_text")
    validos = {c["id"] for c in candidatos}
    return [l.strip() for l in saida.split() if l.strip() in validos]


def assistir(vid: str, tema: str, duracao_lista: float) -> tuple[str, str]:
    """(summary, how): Gemini watches the whole video from its link; if it fails, the captions. Nothing is downloaded."""
    v = _video()
    url = f"https://www.youtube.com/watch?v={vid}"
    pergunta = (f"Quais novidades sobre {tema} este vídeo traz? Liste cada notícia/lançamento com os detalhes concretos "
                "(empresa, produto, números, datas), o que é mostrado na tela e a opinião/conclusão do apresentador. "
                "Responda em português.")
    try:
        return v.gemini().assistir(url, pergunta), "assistido inteiro (Gemini)"
    except Exception as exc:
        print(f"video: Gemini failed for {vid}, using captions: {exc}", flush=True)
    destino = v.PASTA / ("a" + hashlib.sha1(url.encode()).hexdigest()[:10])
    destino.mkdir(parents=True, exist_ok=True)
    falas = v._legendas(url, destino)
    if not falas:
        raise RuntimeError("o Gemini não assistiu e o vídeo não tem legendas")
    return v._pelas_legendas(falas, pergunta, ""), "lido pelas legendas"


async def em_alta(tema: str, consultas: list[str], quantidade: int, horas: int, assistir_videos: bool) -> str:
    inicio = time.time()
    listas = await asyncio.gather(*[asyncio.to_thread(buscar, c, f) for c in consultas for f in FILTROS])
    vistos, candidatos = set(), []
    for lista in listas:
        for c in lista:
            if c["id"] not in vistos:
                vistos.add(c["id"])
                candidatos.append(c)
    if not candidatos:
        return "A busca do YouTube não devolveu vídeos de hoje para essas consultas."
    candidatos.sort(key=lambda c: c["views"], reverse=True)
    relevantes = await asyncio.to_thread(escolher, tema, candidatos[:220], quantidade)
    relevantes = relevantes[:quantidade * 7]  # most viewed first; upload time confirmed for these
    sem_det = asyncio.Semaphore(6)  # yt-dlp metadata runs node for YouTube's challenge: 12 at once overloaded the VM

    async def det(i):
        async with sem_det:
            return await asyncio.to_thread(detalhes, i)
    info = dict(zip(relevantes, await asyncio.gather(*[det(i) for i in relevantes])))
    escolhidos = relevantes
    agora = datetime.now(timezone.utc).timestamp()
    por_id = {c["id"]: c for c in candidatos}
    finais = []
    for vid in escolhidos:  # keep only what was really published inside the window
        d = info.get(vid) or {}
        if not d.get("publicado") or agora - d["publicado"] > horas * 3600:
            continue
        finais.append({**por_id[vid], **{k: x for k, x in d.items() if x}})
    # most watched and best received first: views, then likes
    finais.sort(key=lambda f: (f.get("views") or 0) + 20 * (f.get("curtidas") or 0), reverse=True)
    finais = finais[:quantidade]
    resumos, como = [""] * len(finais), [""] * len(finais)
    if assistir_videos and finais:
        sem = asyncio.Semaphore(PARALELO)

        async def um(i, f):
            async with sem:
                try:
                    resumos[i], como[i] = await asyncio.to_thread(assistir, f["id"], tema, f.get("duracao") or 0)
                except Exception as exc:
                    resumos[i] = f"(não consegui assistir: {str(exc)[:200]})"
        await asyncio.gather(*[um(i, f) for i, f in enumerate(finais)])
    partes = []
    for i, (f, r) in enumerate(zip(finais, resumos), 1):
        quando = (datetime.fromtimestamp(f["publicado"], timezone.utc).strftime("%d/%m %H:%M UTC")
                  if f.get("publicado") else "hoje (hora não confirmada)")
        partes.append(f"## {i}. {f['titulo']}\nCanal: {f['canal']} · {f['views']:,} visualizações · "
                      f"{(f.get('curtidas') or 0):,} curtidas · "
                      f"{int((f.get('duracao') or 0) // 60)} min · publicado {quando}" + (f" · {como[i - 1]}" if como[i - 1] else "") + "\n"
                      f"https://www.youtube.com/watch?v={f['id']}\n\n{r or f.get('descricao', '')}")
    assistidos = sum(1 for c in como if c.startswith("assistido"))
    legendas = sum(1 for c in como if c.startswith("lido"))
    return (f"{len(finais)} vídeos das últimas {horas} h sobre {tema} (de {len(candidatos)} encontrados em "
            f"{len(consultas)} buscas, {len(relevantes)} sobre o tema), {assistidos} assistidos inteiros pelo Gemini e "
            f"{legendas} lidos pelas legendas, em {int(time.time() - inicio)} s.\n\n"
            + "\n\n".join(partes))


class VideosEmAlta(Tool):
    async def execute(self, tema: str = "", consultas=None, quantidade=10, horas=48, assistir=True, **kwargs) -> Response:
        tema = str(tema or "").strip()
        if not tema:
            return Response(message="Informe `tema` (ex.: novidades de inteligência artificial).", break_loop=False)
        if isinstance(consultas, str):
            consultas = [c.strip() for c in consultas.replace(";", "\n").splitlines() if c.strip()]
        consultas = [str(c) for c in (consultas or [])][:10] or [tema]
        try:
            quantidade = max(1, min(15, int(quantidade or 10)))
            horas = max(1, min(168, int(horas or 48)))
        except (TypeError, ValueError):
            quantidade, horas = 10, 48
        assistir = str(assistir).lower() not in ("false", "0", "nao", "não", "no")
        try:
            texto = await em_alta(tema, consultas, quantidade, horas, assistir)
        except Exception as exc:
            texto = f"Falhou: {str(exc)[:400]}"
        return Response(message=texto, break_loop=False)

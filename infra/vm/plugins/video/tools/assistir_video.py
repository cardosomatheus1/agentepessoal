"""Watch a video: download it and have a video model watch all of it (picture and sound).

The agent's Playwright Chromium has no H.264/AAC, so Instagram (and many sites) fail to play in the
browser, and screenshots of a player were never "watching" anyway. TwelveLabs Pegasus 1.5
(Bedrock, AWS Marketplace) watches the whole video, picture and sound. If it fails, Amazon Nova 2
Lite watches it with the faster-whisper transcript alongside (Nova does not hear audio); if that
fails too, frames + a vision model. The exact transcript always goes back for quotes.
"""

import asyncio
import base64
import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path

from helpers.tool import Response, Tool


def gemini():
    """plugins/video/helpers/gemini.py (YouTube watched from its link, no download)."""
    import importlib.util
    import sys

    nome = "video_gemini"
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, Path(__file__).resolve().parents[1] / "helpers" / "gemini.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        sys.modules[nome] = modulo
    return sys.modules[nome]

URL = "http://host.docker.internal:8787/openai/v1/responses"
MODELO = "openai.gpt-6-luna"
PASTA = Path("/a0/usr/workdir/videos")
PERFIL = "/a0/tmp/browser/sessions/shared/Default"  # the agent's own browser, already logged in
MAX_SEGUNDOS = 60 * 60  # Pegasus watches up to an hour
MAX_QUADROS = 16
PEGASUS = "http://host.docker.internal:8787/bedrock/model/us.twelvelabs.pegasus-1-5-v1:0/invoke"
PEGASUS_S3 = "http://host.docker.internal:8787/arquivos/pegasus"
NOVA = "http://host.docker.internal:8787/bedrock/model/us.amazon.nova-2-lite-v1:0/converse"
MAX_BASE64 = 20 * 1024 * 1024  # bigger videos are re-encoded smaller before sending
YTDLP = ["/opt/venv-a0/bin/python", "-m", "yt_dlp", "--js-runtimes", "node", "--remote-components", "ejs:github"]
# YouTube needs a JS runtime for its challenges (node is in the image; deno has no ARM build here)
_WHISPER = None


def _baixar(url: str, destino: Path) -> Path:
    base = [*YTDLP, "--no-playlist", "--max-filesize", "300M", "-f", "b[height<=480][ext=mp4]/bv*[height<=480]+ba/b[height<=480]/b", "--merge-output-format", "mp4",
            "-o", str(destino / "video.%(ext)s"), "--quiet", "--no-warnings", url]
    erro = ""
    com_cookies = ["--cookies-from-browser", f"chromium:{PERFIL}"]
    tentativas = [com_cookies, []] if re.search(r"youtu\.?be", url) else [[], com_cookies]  # YouTube: AWS needs sign-in
    for extra in tentativas:
        r = subprocess.run([*base[:-1], *extra, base[-1]], capture_output=True, text=True, timeout=300)
        achados = sorted(destino.glob("video.*"))
        if r.returncode == 0 and achados:
            return achados[0]
        erro = (r.stderr or r.stdout).strip()[-400:]
    raise RuntimeError(f"não consegui baixar o vídeo: {erro or 'sem detalhes'}")


def _duracao(video: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
                       capture_output=True, text=True, timeout=60)
    return float(json.loads(r.stdout or "{}").get("format", {}).get("duration") or 0)


def _quadros(video: Path, destino: Path, duracao: float) -> list[tuple[float, Path]]:
    n = max(4, min(MAX_QUADROS, int(duracao // 3) or 4))
    saida = []
    for i in range(n):
        t = duracao * (i + 0.5) / n
        arq = destino / f"quadro_{i + 1:02d}_{int(t)}s.jpg"
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale='min(768,iw)':-2", "-q:v", "4", str(arq)], timeout=60)
        if arq.exists():
            saida.append((t, arq))
    return saida


def _transcrever(video: Path) -> str:
    global _WHISPER
    import numpy as np
    from faster_whisper import WhisperModel

    bruto = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(video), "-vn", "-f", "s16le", "-ac", "1",
                            "-ar", "16000", "-"], capture_output=True, timeout=300).stdout
    if not bruto:
        return ""
    if _WHISPER is None:
        _WHISPER = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
    audio = np.frombuffer(bruto, np.int16).astype(np.float32) / 32768.0
    segmentos, _ = _WHISPER.transcribe(audio, beam_size=1, vad_filter=True)
    return "\n".join(f"[{int(s.start // 60)}:{int(s.start % 60):02d}] {s.text.strip()}" for s in segmentos)


def _descrever(quadros: list[tuple[float, Path]], transcricao: str, pergunta: str, legenda: str) -> str:
    conteudo = [{"type": "input_text", "text": (
        "Estes são quadros de um vídeo, em ordem, com o tempo de cada um, e a transcrição do áudio. Descreva em "
        "português o que acontece no vídeo, em ordem (o que aparece na tela, textos legíveis, telas de programas, "
        "o que a pessoa fala e mostra) e depois responda à pergunta do usuário, se houver. Não invente o que não "
        "aparece nos quadros nem na transcrição; diga quando algo não dá para ver.\n\n"
        f"Pergunta do usuário: {pergunta or '(nenhuma: resuma o vídeo)'}\n\n"
        + (f"Legenda/descrição do post: {legenda[:1500]}\n\n" if legenda else "")
        + f"Transcrição do áudio:\n{transcricao[:12000] or '(sem fala)'}")}]
    for t, arq in quadros:
        conteudo.append({"type": "input_text", "text": f"Quadro em {int(t // 60)}:{int(t % 60):02d}"})
        conteudo.append({"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(arq.read_bytes()).decode()})
    corpo = {"model": MODELO, "reasoning": {"effort": "low"}, "input": [{"role": "user", "content": conteudo}]}
    req = urllib.request.Request(URL, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        dados = json.loads(r.read())
    return "".join(c.get("text", "") for item in dados.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []) if c.get("type") == "output_text").strip()


def _caber(video: Path, duracao: float) -> Path:
    """Re-encode (480p, bitrate for ~18 MB) when the video is too big to send inline."""
    if video.stat().st_size <= MAX_BASE64:
        return video
    menor = video.with_name("video_menor.mp4")
    if not menor.exists():
        kbps = max(150, int(18 * 8 * 1024 / max(duracao, 1)) - 64)
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(video), "-vf", "scale=-2:'min(480,ih)'",
                        "-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{kbps}k", "-c:a", "aac", "-b:a", "64k",
                        str(menor)], timeout=900, check=True)
    return menor


def _assistir_pegasus(video: Path, duracao: float, pergunta: str, legenda: str) -> str:
    prompt = ("Assista o vídeo inteiro (imagem e áudio) e responda em português. Primeiro descreva em ordem, com os "
              "tempos (mm:ss), o que acontece: o que aparece na tela, textos legíveis, telas de programas, o que a pessoa "
              "fala e mostra. Depois responda à pergunta do usuário, se houver. Não invente o que não está no vídeo.\n\n"
              f"Pergunta do usuário: {pergunta[:500] or '(nenhuma: resuma o vídeo)'}"
              + (f"\n\nLegenda do post (contexto): {legenda[:600]}" if legenda else ""))
    try:  # through S3 (the proxy has the AWS credentials): whole video, no re-encoding, ~10-40 s
        req = urllib.request.Request(PEGASUS_S3, data=json.dumps({"arquivo": str(video), "prompt": prompt}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            texto = str(json.loads(r.read()).get("message") or "").strip()
    except Exception as exc:
        print(f"video: Pegasus via S3 failed, sending inline: {exc}", flush=True)
        dados = base64.b64encode(_caber(video, duracao).read_bytes()).decode()
        corpo = {"inputPrompt": prompt, "mediaSource": {"base64String": dados}, "temperature": 0}
        req = urllib.request.Request(PEGASUS, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            texto = str(json.loads(r.read()).get("message") or "").strip()
    if not texto:
        raise RuntimeError("Pegasus sem resposta")
    return texto


def _assistir_nova(video: Path, duracao: float, transcricao: str, pergunta: str, legenda: str) -> str:
    prompt = ("Assista o vídeo inteiro e responda em português. Você não ouve o áudio: a transcrição da fala, com os "
              "tempos, está abaixo; junte o que aparece na tela com o que é falado em cada momento. Primeiro descreva em "
              "ordem, com os tempos (mm:ss), o que acontece: o que aparece, textos legíveis, telas de programas, o que a "
              "pessoa fala e mostra. Depois responda à pergunta do usuário, se houver. Não invente o que não está no "
              "vídeo nem na transcrição; diga quando algo não dá para ler.\n\n"
              f"Pergunta do usuário: {pergunta or '(nenhuma: resuma o vídeo)'}\n\n"
              + (f"Legenda do post (contexto): {legenda[:1000]}\n\n" if legenda else "")
              + f"Transcrição da fala:\n{transcricao[:15000] or '(sem fala)'}")
    dados = base64.b64encode(_caber(video, duracao).read_bytes()).decode()
    corpo = {"messages": [{"role": "user", "content": [{"video": {"format": "mp4", "source": {"bytes": dados}}},
                                                       {"text": prompt}]}],
             "inferenceConfig": {"maxTokens": 4000, "temperature": 0}}
    req = urllib.request.Request(NOVA, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        saida = json.loads(r.read())
    return "".join(c.get("text", "") for c in saida["output"]["message"]["content"]).strip()


def _legenda(url: str) -> str:
    try:
        r = subprocess.run([*YTDLP, "--skip-download", "--print", "%(description)s", "--quiet", "--no-warnings", url],
                           capture_output=True, text=True, timeout=60)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _legendas(url: str, destino: Path) -> str:
    """The video's own or automatic captions, without downloading it (seconds instead of minutes)."""
    try:
        for f in destino.glob("leg*"):
            f.unlink()
        subprocess.run([*YTDLP, "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "pt-orig,pt,pt-BR,en-orig,en",
                        "--cookies-from-browser", f"chromium:{PERFIL}",  # YouTube asks AWS addresses to sign in
                        "--sub-format", "vtt", "-o", str(destino / "leg.%(ext)s"), "--quiet", "--no-warnings", url],
                       capture_output=True, text=True, timeout=90)
        arquivos = sorted(destino.glob("leg*.vtt"), key=lambda p: (".pt" not in p.name, "-orig" not in p.name, p.name))
        if not arquivos:
            return ""
        vistos, saida = set(), []
        for linha in arquivos[0].read_text(errors="ignore").splitlines():
            linha = re.sub(r"<[^>]+>", "", linha).strip()
            if linha and "-->" not in linha and not linha.startswith(("WEBVTT", "Kind:", "Language:")) and linha not in vistos:
                vistos.add(linha)
                saida.append(linha)
        return " ".join(saida)
    except Exception:
        return ""


def _pelas_legendas(legendas: str, pergunta: str, legenda: str) -> str:
    texto = ("Esta é a transcrição (legendas) de um vídeo. Responda em português à pergunta do usuário com base nela: "
             "o que a pessoa diz, mostra e conclui, com detalhes concretos (números, prós e contras, defeitos citados). "
             "Não invente o que não está na transcrição.\n\n"
             f"Pergunta do usuário: {pergunta or '(nenhuma: resuma o vídeo)'}\n\n"
             + (f"Descrição do vídeo: {legenda[:1500]}\n\n" if legenda else "") + f"Transcrição:\n{legendas[:60000]}")
    corpo = {"model": MODELO, "reasoning": {"effort": "low"}, "input": [{"role": "user", "content": [{"type": "input_text", "text": texto}]}]}
    req = urllib.request.Request(URL, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        dados = json.loads(r.read())
    return "".join(c.get("text", "") for item in dados.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []) if c.get("type") == "output_text").strip()


_PROMPT_VER = ("Assista o vídeo inteiro (imagem e áudio) e responda em português. Primeiro descreva em ordem, com os "
               "tempos (mm:ss), o que acontece: o que aparece na tela, textos legíveis, o que a pessoa fala e mostra. "
               "Depois responda à pergunta do usuário. Não invente o que não está no vídeo.\n\nPergunta do usuário: {pergunta}")


def assistir(url: str, caminho: str, pergunta: str, modo: str = "") -> str:
    chave = hashlib.sha1((url or caminho).encode()).hexdigest()[:10]
    destino = PASTA / chave
    destino.mkdir(parents=True, exist_ok=True)
    youtube = gemini().e_youtube(url)
    if youtube and modo != "rapido":  # YouTube: Gemini watches it from the link; nothing is downloaded
        try:
            descricao = gemini().assistir(url, _PROMPT_VER.format(pergunta=pergunta[:800] or "(nenhuma: resuma o vídeo)"))
            (destino / "descricao.md").write_text(descricao, encoding="utf-8")
            return f"Vídeo assistido inteiro pelo Gemini, imagem e áudio (direto do link, sem baixar).\n\n{descricao}"
        except Exception as exc:
            print(f"video: Gemini failed, using captions: {exc}", flush=True)
    falas = _legendas(url, destino) if url else ""
    if youtube and not falas:
        return "Não consegui assistir esse vídeo do YouTube (o Gemini falhou e ele não tem legendas)."
    if falas and (modo == "rapido" or youtube):  # captions, no download (YouTube is never downloaded)
        legenda = _legenda(url)
        (destino / "transcricao.txt").write_text(falas, encoding="utf-8")
        descricao = _pelas_legendas(falas, pergunta, legenda)
        (destino / "descricao.md").write_text(descricao, encoding="utf-8")
        return (f"Vídeo lido pelas legendas (modo rápido, sem baixar).\n\n{descricao}\n\n"
                f"--- Transcrição (início) ---\n{falas[:3000]}\n\nArquivos: {destino}")
    if url:
        video = next(iter(sorted(destino.glob("video.*"))), None) or _baixar(url, destino)
    else:
        video = Path(caminho)
        if not video.is_file():
            return f"Arquivo não encontrado: {caminho}"
    duracao = _duracao(video)
    if duracao <= 0:
        return "Não consegui ler esse vídeo (formato ou arquivo inválido)."
    if duracao > MAX_SEGUNDOS:
        return f"O vídeo tem {int(duracao // 60)} min; o limite é {MAX_SEGUNDOS // 60} min. Peça um trecho ou um vídeo menor."
    legenda = _legenda(url) if url else ""
    try:
        transcricao = falas or _transcrever(video)  # captions when there are any: Whisper on CPU is slow
    except Exception as exc:
        transcricao = f"(não consegui transcrever: {str(exc)[:200]})"
    (destino / "transcricao.txt").write_text(transcricao, encoding="utf-8")
    try:
        descricao, como = _assistir_pegasus(video, duracao, pergunta, legenda), "assistido inteiro, imagem e áudio (Pegasus)"
    except Exception as exc:
        print(f"video: Pegasus failed, trying Nova: {exc}", flush=True)
        try:
            descricao, como = _assistir_nova(video, duracao, transcricao, pergunta, legenda), "assistido inteiro + fala transcrita (Nova)"
        except Exception as exc2:  # last resort: frames + vision model
            print(f"video: Nova failed, using frames: {exc2}", flush=True)
            quadros = _quadros(video, destino, duracao)
            descricao = _descrever(quadros, transcricao, pergunta, legenda)
            como = f"{len(quadros)} quadros analisados (os modelos de vídeo falharam)"
    (destino / "descricao.md").write_text(descricao, encoding="utf-8")
    return (f"Vídeo {int(duracao // 60)}:{int(duracao % 60):02d} — {como}.\n\n"
            f"{descricao}\n\n--- Transcrição exata do áudio ---\n{transcricao[:4000] or '(sem fala)'}\n\n"
            f"Arquivos: {destino} (vídeo, transcricao.txt, descricao.md)")


class AssistirVideo(Tool):
    async def execute(self, url: str = "", caminho: str = "", pergunta: str = "", modo: str = "", **kwargs) -> Response:
        url, caminho = str(url or "").strip(), str(caminho or "").strip()
        if not (url or caminho):
            return Response(message="Informe `url` (link do vídeo) ou `caminho` (arquivo).", break_loop=False)
        if url and not re.match(r"https?://", url):
            return Response(message="`url` precisa começar com http:// ou https://", break_loop=False)
        try:
            texto = await asyncio.to_thread(assistir, url, caminho, str(pergunta or ""), str(modo or "").strip().lower())
        except Exception as exc:
            texto = f"Não consegui assistir: {str(exc)[:500]}"
        return Response(message=texto, break_loop=False)

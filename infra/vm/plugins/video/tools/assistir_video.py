"""Watch a video: download it, take frames across it, transcribe the audio, describe it in one model call.

The agent's Playwright Chromium has no H.264/AAC, so Instagram (and many sites) fail to play in the
browser, and screenshots of a player were never "watching" anyway.
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

URL = "http://host.docker.internal:8787/openai/v1/responses"
MODELO = "openai.gpt-6-luna"
PASTA = Path("/a0/usr/workdir/videos")
PERFIL = "/a0/tmp/browser/sessions/shared/Default"  # the agent's own browser, already logged in
MAX_SEGUNDOS = 20 * 60
MAX_QUADROS = 16
YTDLP = ["/opt/venv-a0/bin/python", "-m", "yt_dlp"]
_WHISPER = None


def _baixar(url: str, destino: Path) -> Path:
    base = [*YTDLP, "--no-playlist", "--max-filesize", "300M", "-f", "b[ext=mp4]/bv*+ba/b", "--merge-output-format", "mp4",
            "-o", str(destino / "video.%(ext)s"), "--quiet", "--no-warnings", url]
    erro = ""
    for extra in ([], ["--cookies-from-browser", f"chromium:{PERFIL}"]):  # logged-in only when the site requires it
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


def _legenda(url: str) -> str:
    try:
        r = subprocess.run([*YTDLP, "--skip-download", "--print", "%(description)s", "--quiet", "--no-warnings", url],
                           capture_output=True, text=True, timeout=60)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def assistir(url: str, caminho: str, pergunta: str) -> str:
    chave = hashlib.sha1((url or caminho).encode()).hexdigest()[:10]
    destino = PASTA / chave
    destino.mkdir(parents=True, exist_ok=True)
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
    quadros = _quadros(video, destino, duracao)
    try:
        transcricao = _transcrever(video)
    except Exception as exc:
        transcricao = f"(não consegui transcrever: {str(exc)[:200]})"
    (destino / "transcricao.txt").write_text(transcricao, encoding="utf-8")
    descricao = _descrever(quadros, transcricao, pergunta, _legenda(url) if url else "")
    (destino / "descricao.md").write_text(descricao, encoding="utf-8")
    return (f"Vídeo assistido ({int(duracao // 60)}:{int(duracao % 60):02d}, {len(quadros)} quadros analisados).\n\n"
            f"{descricao}\n\n--- Transcrição do áudio ---\n{transcricao[:4000] or '(sem fala)'}\n\n"
            f"Arquivos: {destino} (vídeo, quadro_*.jpg, transcricao.txt, descricao.md)")


class AssistirVideo(Tool):
    async def execute(self, url: str = "", caminho: str = "", pergunta: str = "", **kwargs) -> Response:
        url, caminho = str(url or "").strip(), str(caminho or "").strip()
        if not (url or caminho):
            return Response(message="Informe `url` (link do vídeo) ou `caminho` (arquivo).", break_loop=False)
        if url and not re.match(r"https?://", url):
            return Response(message="`url` precisa começar com http:// ou https://", break_loop=False)
        try:
            texto = await asyncio.to_thread(assistir, url, caminho, str(pergunta or ""))
        except Exception as exc:
            texto = f"Não consegui assistir: {str(exc)[:500]}"
        return Response(message=texto, break_loop=False)

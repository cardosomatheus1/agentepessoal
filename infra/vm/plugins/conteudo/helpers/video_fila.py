"""Renders one approved Reel of a week in the background and hands it to semana.concluir_video (22/10).

    python video_fila.py <semana> <n>

Started by semana.iniciar_video right after Matheus approves (decision #39: the video only after the narration is
approved). One render at a time (video.lock): the VM has 4 cores and the agent keeps working meanwhile, so the motor
runs with 2 processes. The ficha, molde and format are the ones the Crítico judged in the preview; nothing is
re-decided here."""

import fcntl
import importlib.util
import sys
from pathlib import Path

PROCESSOS = 2
TEMPO = 3 * 3600  # a 60 s Reel takes about an hour with 2 processes; three is the ceiling before giving up


def _semana():
    spec = importlib.util.spec_from_file_location("conteudo_semana_video", Path(__file__).resolve().parent / "semana.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def gerar(sid: str, n: int, semana=None, esp=None) -> dict:
    s = semana or _semana()
    with open(s._pasta() / "video.lock", "a") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX)  # the next video waits here for the one before
        dados = s.carregar(sid) or {}
        p = next((x for x in dados.get("propostas", []) if x["n"] == n), None)
        if not p or p.get("estado") != "gerando_video":
            return {"ok": False, "erro": f"a {n} da semana {sid} não está esperando vídeo"}
        v = p["video"]
        try:
            esp = esp or s.c().especialistas()
            if esp is None:
                raise RuntimeError("o plugin de especialistas não está instalado")
            arquivos, problema = esp.renderizar_molde(str(v["molde"]), v["formato"], v["ficha"], previa=False,
                                                      saida=s._pasta() / sid / f"video-{n}", timeout=TEMPO,
                                                      processos=PROCESSOS)
        except Exception as exc:
            arquivos, problema = [], f"o render não rodou ({type(exc).__name__}: {str(exc)[:120]})"
        video = next((a for a in arquivos if a.endswith(".mp4")), "")
        return s.concluir_video(sid, n, video=video if not problema else "", erro=problema)


if __name__ == "__main__":
    print(gerar(sys.argv[1], int(sys.argv[2])), flush=True)

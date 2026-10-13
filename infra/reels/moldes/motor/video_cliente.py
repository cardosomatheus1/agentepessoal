#!/usr/bin/env python3
"""The client's own video as background footage: turns an mp4/mov into the frame folder the templates read
(midia/filmagem/<nome>/q0001.jpg…, 30 fps, up to 12 s, slowed 2x when shorter than 6 s). In the ficha the field
of type "filmagem" then takes <nome>, just like a clip of the bank; a photo path (fotos/x.jpg) also works there.

    video_cliente.py <video> <nome>
"""
import re, subprocess, sys
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "midia" / "filmagem"


def converter(video, nome):
    if not re.fullmatch(r"[a-z0-9_-]{2,40}", nome):
        raise SystemExit("nome: letras minúsculas, números, - e _")
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)]))
    pasta = DESTINO / nome
    pasta.mkdir(parents=True, exist_ok=True)
    for f in pasta.glob("q*.jpg"): f.unlink()
    lento = "setpts=2*PTS," if dur < 6 else ""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-t", "12", "-vf", f"{lento}fps=30,scale=1280:-2", "-frames:v", "360", "-q:v", "4", str(pasta / "q%04d.jpg")], check=True)
    n = len(list(pasta.glob("q*.jpg")))
    if n < 30: raise SystemExit(f"vídeo curto demais ({n} quadros)")
    return n


if __name__ == "__main__":
    if len(sys.argv) != 3: print(__doc__); sys.exit(1)
    print(sys.argv[2], converter(sys.argv[1], sys.argv[2]))

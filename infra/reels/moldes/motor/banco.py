#!/usr/bin/env python3
"""Footage bank: clips live in S3 (conteudo/banco_filmagem/<nome>.mp4, generated once with Wan 2.2 or Nova Reel)
and become frame folders the templates read (midia/filmagem/<nome>/q0001.jpg…, slowed 2x, 30 fps, 360 frames).

    banco.py baixar [nome ...]     # all clips when no name is given
    banco.py lista
"""
import subprocess, sys
from pathlib import Path
import boto3

BUCKET, PREFIXO = "agentepessoal-backup-964862484412", "conteudo/banco_filmagem/"
DESTINO = Path(__file__).resolve().parent.parent / "midia" / "filmagem"


def lista():
    s3 = boto3.client("s3", region_name="us-east-1")
    return sorted(o["Key"][len(PREFIXO):-4] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIXO).get("Contents", []) if o["Key"].endswith(".mp4"))


def baixar(nomes):
    s3 = boto3.client("s3", region_name="us-east-1")
    for n in nomes or lista():
        pasta = DESTINO / n
        if pasta.exists() and len(list(pasta.glob("q*.jpg"))) >= 300:
            continue
        pasta.mkdir(parents=True, exist_ok=True)
        mp4 = pasta / "_fonte.mp4"
        s3.download_file(BUCKET, f"{PREFIXO}{n}.mp4", str(mp4))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vf", "setpts=2*PTS,fps=30,scale=1280:-2", "-frames:v", "360", "-q:v", "4", str(pasta / "q%04d.jpg")], check=True)
        mp4.unlink()
        print(n, len(list(pasta.glob("q*.jpg"))))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "lista": print("\n".join(lista()))
    elif len(sys.argv) > 1 and sys.argv[1] == "baixar": baixar(sys.argv[2:])
    else: print(__doc__)

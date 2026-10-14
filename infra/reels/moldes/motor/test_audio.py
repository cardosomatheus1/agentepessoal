"""Music under the narration (misturar_musica): runs the real ffmpeg on synthetic tones, no browser."""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import misturar_musica, musica  # noqa: E402

ok = falhou = 0


def caso(nome, cond):
    global ok, falhou
    if cond: ok += 1
    else: falhou += 1; print("FALHOU:", nome)


def tom(caminho, freq, dur):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur}", "-c:a", "aac", str(caminho)], check=True)


def duracao(caminho):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(caminho)], capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def volume(caminho, ini, dur):
    r = subprocess.run(["ffmpeg", "-v", "info", "-ss", str(ini), "-t", str(dur), "-i", str(caminho), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    linha = [x for x in r.stderr.splitlines() if "mean_volume" in x]
    return float(linha[0].split("mean_volume:")[1].split("dB")[0]) if linha else -999.0


caso("sem música escolhida, a padrão continua a animada", musica({}, {}, {}).name == "animada.ogg")
caso("a ficha escolhe a música", musica({"_musica": "tecnologica"}, {"musica": "leve"}, {}).name == "tecnologica.ogg")
cmd = misturar_musica("v.m4a", "m.ogg", 60.0, "o.m4a")
caso("mistura dura o vídeo inteiro", "-t" in cmd and cmd[cmd.index("-t") + 1] == "60.000")
caso("música em laço (faixa mais curta que o vídeo)", "-stream_loop" in cmd)
caso("música baixa por padrão", "volume=0.14" in " ".join(cmd))

if shutil.which("ffmpeg"):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        tom(d / "voz.m4a", 440, 4)       # narration ends at 4 s
        tom(d / "mus.m4a", 220, 3)       # track shorter than the video: must loop
        subprocess.run(misturar_musica(d / "voz.m4a", d / "mus.m4a", 10.0, d / "o.m4a"), check=True)
        caso("saída com a duração do vídeo", abs(duracao(d / "o.m4a") - 10.0) < 0.2)
        com_voz, so_musica = volume(d / "o.m4a", 1, 2), volume(d / "o.m4a", 5, 2)
        caso("depois da voz a música continua (laço)", so_musica > -60)
        caso("a voz fica bem acima da música", com_voz - so_musica > 10)
else:
    print("(sem ffmpeg: só a montagem do comando foi testada)")

print(f"{ok} ok, {falhou} falharam")
sys.exit(1 if falhou else 0)

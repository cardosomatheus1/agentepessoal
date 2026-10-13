#!/usr/bin/env python3
"""Renders a template (molde) with a ficha and a brand.

    render.py <molde> <ficha.json> [--formato reel|story|carrossel] [--saida DIR] [--previa] [--area] [--sem-conferir]

--previa: only the check (at the middle and the end of every scene, or every slide) and a contact sheet prev.jpg;
without it: the finished video (video.mp4, 1080x1920, 30 fps, audio at -14 LUFS) or the slides (slide1.jpg…).
Exit codes: 0 ok, 2 ficha or template error, 3 the check found problems (text cut, small letters, outside the area
Instagram covers). The report goes to <saida>/relatorio.json.
"""
import argparse, hashlib, json, os, subprocess, sys, tempfile
from multiprocessing import Pool
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "motor"))
from validar import validar  # noqa: E402

FPS = 30
CACHE_VOZ = Path(os.environ.get("MOLDES_CACHE", Path.home() / ".cache" / "moldes")) / "voz"


def carregar(molde, ficha_path, formato=None):
    pasta = RAIZ / molde
    if not (pasta / "molde.html").exists():
        raise SystemExit(f"molde não existe: {molde}")
    esquema = json.loads((pasta / "esquema.json").read_text())
    ficha = json.loads(Path(ficha_path).read_text())
    erros = validar(esquema, ficha)
    marca_id = ficha.get("_marca", "raiz")
    marca_dir = RAIZ / "marcas" / marca_id
    if not (marca_dir / "marca.json").exists():
        erros.append(f"_marca: marca {marca_id} não existe")
        marca = {}
    else:
        marca = json.loads((marca_dir / "marca.json").read_text())
    formato = formato or ficha.get("_formato") or esquema.get("formatos", ["reel"])[0]
    if formato not in esquema.get("formatos", []):
        erros.append(f"formato {formato} não é deste molde")
    return pasta, esquema, ficha, marca, marca_dir, formato, erros


def voz(ficha, esquema, marca):
    modo = esquema.get("voz", "nao")
    falas = ficha.get("falas")
    if modo == "nao" or not falas or (modo == "opcional" and not ficha.get("_voz", True)):
        return None, None
    v = marca.get("voz") or {"id": "Camila", "motor": "generative"}
    CACHE_VOZ.mkdir(parents=True, exist_ok=True)
    arqs, dur = [], []
    for f in falas:
        h = hashlib.sha1(f"{v['id']}|{v.get('motor', 'generative')}|{f}".encode()).hexdigest()[:16]
        mp = CACHE_VOZ / f"{h}.mp3"
        if not mp.exists():
            subprocess.run(["aws", "polly", "synthesize-speech", "--region", "us-east-1", "--engine", v.get("motor", "generative"),
                            "--voice-id", v["id"], "--output-format", "mp3", "--sample-rate", "24000", "--text", f, str(mp)],
                           check=True, capture_output=True)
        d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp)]))
        arqs.append(mp); dur.append(d + 0.25)
    dur[-1] += 1.4
    tempos = [0.0]
    for x in dur: tempos.append(round(tempos[-1] + x, 3))
    return tempos, list(zip(arqs, dur))


def filmagens():
    base = RAIZ / "midia" / "filmagem"
    return {d.name: len(list(d.glob("q*.jpg"))) for d in base.iterdir() if d.is_dir()} if base.exists() else {}


def init_script(ficha, marca, marca_dir, formato, tempos):
    dados = {"FICHA": ficha, "MARCA": marca, "FORMATO": formato, "TEMPOS": tempos,
             "MIDIA": (RAIZ / "midia").as_uri() + "/", "MARCA_BASE": marca_dir.as_uri() + "/", "FILMAGENS": filmagens()}
    return "".join(f"window.{k}={json.dumps(v, ensure_ascii=False)};" for k, v in dados.items())


def abrir(pw, pasta, script, formato):
    b = pw.chromium.launch(executable_path=os.environ.get("CHROME") or None, args=["--allow-file-access-from-files", "--disable-web-security"])
    pg = b.new_page(viewport={"width": 1080, "height": 1350 if formato == "carrossel" else 1920})
    pg.add_init_script(script)
    pg.goto((pasta / "molde.html").as_uri())
    pg.wait_for_function("window.MOTOR_PRONTO === true", timeout=60000)
    return b, pg


def _trabalho(args):
    from playwright.sync_api import sync_playwright
    pasta, script, formato, quadros, saida = args
    with sync_playwright() as pw:
        b, pg = abrir(pw, Path(pasta), script, formato)
        for i, t in quadros:
            pg.evaluate(f"render({t})"); pg.screenshot(path=saida.format(i))
        b.close()


def folha(imagens, destino, largura=270, por_linha=6):
    if not imagens: return
    ins = sum([["-i", str(i)] for i in imagens], [])
    n = len(imagens); linhas = (n + por_linha - 1) // por_linha
    filtros = [f"[{i}:v]scale={largura}:-1[s{i}]" for i in range(n)]
    pad = por_linha * linhas - n
    blocos = []
    for r in range(linhas):
        idx = list(range(r * por_linha, min(n, (r + 1) * por_linha)))
        entradas = "".join(f"[s{i}]" for i in idx)
        if len(idx) < por_linha and linhas > 1:
            filtros.append(f"{entradas}hstack={len(idx)},pad={largura * por_linha}:ih:0:0:black[l{r}]")
        elif len(idx) > 1:
            filtros.append(f"{entradas}hstack={len(idx)}[l{r}]")
        else:
            filtros.append(f"{entradas}null[l{r}]")
        blocos.append(f"[l{r}]")
    filtros.append("".join(blocos) + (f"vstack={linhas}[o]" if linhas > 1 else "null[o]"))
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + ins + ["-filter_complex", ";".join(filtros), "-map", "[o]", "-q:v", "3", str(destino)], check=True)


def musica(ficha, esquema, marca):
    pasta = RAIZ / "motor" / "musica"
    lic = json.loads((pasta / "licencas.json").read_text()) if (pasta / "licencas.json").exists() else {}
    nome = ficha.get("_musica") or marca.get("musica") or esquema.get("musica") or (sorted(lic) or [None])[0]
    return (pasta / lic[nome]["arquivo"]) if nome in lic else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("molde"); ap.add_argument("ficha")
    ap.add_argument("--formato"); ap.add_argument("--saida"); ap.add_argument("--previa", action="store_true")
    ap.add_argument("--area", action="store_true"); ap.add_argument("--sem-conferir", action="store_true")
    ap.add_argument("--processos", type=int, default=4)
    a = ap.parse_args()
    pasta, esquema, ficha, marca, marca_dir, formato, erros = carregar(a.molde, a.ficha, a.formato)
    saida = Path(a.saida) if a.saida else pasta / "saida" / f"{Path(a.ficha).stem}-{formato}"
    saida.mkdir(parents=True, exist_ok=True)
    rel = {"molde": a.molde, "ficha": str(a.ficha), "formato": formato, "erros": erros, "problemas": [], "avisos": []}
    if erros:
        (saida / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1))
        print("FICHA RECUSADA:\n  " + "\n  ".join(erros)); sys.exit(2)
    tempos, audios = voz(ficha, esquema, marca) if formato != "carrossel" else (None, None)
    script = init_script(ficha, marca, marca_dir, formato, tempos)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b, pg = abrir(pw, pasta, script, formato)
        info = pg.evaluate("({erros: Motor.erros, avisos: Motor.avisos, S: Motor.S, N: Motor.N, DUR: Motor.DUR, slides: Motor._slides.length})")
        rel["avisos"] = info["avisos"]
        if info["erros"]:
            rel["erros"] = info["erros"]; (saida / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1))
            print("MOLDE RECUSOU:\n  " + "\n  ".join(info["erros"])); b.close(); sys.exit(2)
        if a.area: pg.evaluate("Motor.mostrarArea()")
        imgs = []
        if formato == "carrossel":
            for i in range(info["slides"]):
                pg.evaluate(f"Motor.slide({i})"); pg.wait_for_timeout(60)
                for x in ([] if a.sem_conferir else pg.evaluate("Motor.conferir()")): rel["problemas"].append({"slide": i + 1, "msg": x})
                img = saida / f"slide{i + 1}.jpg"; pg.screenshot(path=str(img), type="jpeg", quality=92); imgs.append(img)
        else:
            S, N = info["S"], info["N"]
            amostras = []
            for i in range(N):
                ini, fim = S[i], S[i + 1]
                amostras += [(i, round(ini + (fim - ini) * 0.6, 3), True), (i, round(max(ini, fim - 0.08), 3), False)]
            for i, t, foto in amostras:
                pg.evaluate(f"render({t})")
                if not a.sem_conferir:
                    for x in pg.evaluate("Motor.conferir()"): rel["problemas"].append({"cena": i + 1, "t": t, "msg": x})
                if foto:
                    img = saida / f"p{i + 1:02d}.jpg"; pg.screenshot(path=str(img), type="jpeg", quality=80); imgs.append(img)
            rel["duracao"] = info["DUR"]
        b.close()
    vistos = set(); unicos = []
    for pr in rel["problemas"]:
        if pr["msg"] not in vistos: vistos.add(pr["msg"]); unicos.append(pr)
    rel["problemas"] = unicos
    folha(imgs, saida / "prev.jpg")
    if not a.previa and formato != "carrossel":
        dur = info["DUR"]; n = int(dur * FPS) + 1
        with tempfile.TemporaryDirectory() as tmp:
            k = max(1, a.processos)
            jobs = [(str(pasta), script, formato, [(i, round(i / FPS, 4)) for i in range(j, n, k)], f"{tmp}/f{{:05d}}.png") for j in range(k)]
            with Pool(k) as pl: pl.map(_trabalho, jobs)
            audio = None
            if audios:
                ins = sum([["-i", str(f)] for f, _ in audios], [])
                af = ";".join(f"[{i}:a]apad=whole_dur={d:.3f}[a{i}]" for i, (_, d) in enumerate(audios)) + ";" + "".join(f"[a{i}]" for i in range(len(audios))) + f"concat=n={len(audios)}:v=0:a=1[o]"
                audio = f"{tmp}/voz.m4a"
                subprocess.run(["ffmpeg", "-v", "error", "-y"] + ins + ["-filter_complex", af, "-map", "[o]", audio], check=True)
            else:
                m = musica(ficha, esquema, marca)
                if m:
                    audio = f"{tmp}/mus.m4a"
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(m), "-t", f"{dur:.3f}", "-af", f"afade=t=in:d=0.3,afade=t=out:st={max(0, dur - 1.2):.3f}:d=1.2", audio], check=True)
            cmd = ["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", f"{tmp}/f%05d.png"]
            if audio: cmd += ["-i", audio, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "160k", "-shortest"]
            cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium", "-movflags", "+faststart", str(saida / "video.mp4")]
            subprocess.run(cmd, check=True)
        rel["video"] = str(saida / "video.mp4")
    (saida / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1))
    if rel["avisos"]: print("avisos: " + "; ".join(rel["avisos"]))
    if rel["problemas"]:
        print(f"CONFERÊNCIA: {len(rel['problemas'])} problema(s)")
        for pr in rel["problemas"][:30]: print("  ", pr)
        sys.exit(3)
    print("ok", saida)


if __name__ == "__main__":
    main()

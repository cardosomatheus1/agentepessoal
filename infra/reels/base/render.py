# uso: render.py <pasta> [t1 t2 ...]  -> sem tempos: vídeo completo pasta/reel.mp4; com tempos: pasta/prev.png
import sys, os, re, subprocess
from multiprocessing import Pool
from playwright.sync_api import sync_playwright
d=os.path.abspath(sys.argv[1]); fps=30
S=eval(re.search(r"\[.*\]",open(f"{d}/tempos.js").read()).group(0)); total=S[-1]
def trab(args):
    idx,tempos,saida=args
    with sync_playwright() as pw:
        b=pw.chromium.launch(executable_path=os.environ.get("CHROME") or None,args=["--allow-file-access-from-files"])
        pg=b.new_page(viewport={"width":1080,"height":1920})
        pg.goto(f"file://{d}/index.html"); pg.wait_for_timeout(600)
        for i,t in zip(idx,tempos):
            pg.evaluate(f"render({t})"); pg.screenshot(path=saida.format(i))
        b.close()
if len(sys.argv)>2:
    ts=[float(x) for x in sys.argv[2:]]; os.makedirs(f"{d}/prev",exist_ok=True)
    trab((list(range(len(ts))),ts,f"{d}/prev/p{{:02d}}.png"))
    ins=sum([["-i",f"{d}/prev/p{i:02d}.png"] for i in range(len(ts))],[])
    fc=f"hstack={len(ts)}," if len(ts)>1 else ""
    subprocess.run(["ffmpeg","-v","error","-y"]+ins+["-filter_complex",f"{fc}scale={360*len(ts)}:-1",f"{d}/prev.png"],check=True)
else:
    os.makedirs(f"{d}/fr",exist_ok=True)
    n=int(total*fps)+1; k=4
    jobs=[(list(range(j,n,k)),[i/fps for i in range(j,n,k)],f"{d}/fr/f{{:05d}}.png") for j in range(k)]
    with Pool(k) as pl: pl.map(trab,jobs)
    subprocess.run(["ffmpeg","-v","error","-y","-framerate",str(fps),"-i",f"{d}/fr/f%05d.png","-i",f"{d}/voz.m4a","-c:v","libx264","-pix_fmt","yuv420p","-crf","18","-preset","medium","-c:a","aac","-b:a","128k","-shortest","-movflags","+faststart",f"{d}/reel.mp4"],check=True)
    subprocess.run(["rm","-rf",f"{d}/fr"])
    print("ok",f"{d}/reel.mp4",total)

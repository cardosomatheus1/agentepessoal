# uso: carrossel.py <pasta>  -> pasta/slide1.png… (1080x1350), cada .slide do index.html
import sys, os, subprocess
from playwright.sync_api import sync_playwright
d=os.path.abspath(sys.argv[1])
with sync_playwright() as pw:
    b=pw.chromium.launch(executable_path=os.environ.get("CHROME") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",args=["--allow-file-access-from-files"])
    pg=b.new_page(viewport={"width":1080,"height":1350})
    pg.goto(f"file://{d}/index.html"); pg.wait_for_timeout(800)
    n=pg.evaluate("document.querySelectorAll('.slide').length")
    for i in range(n):
        pg.evaluate(f"document.querySelectorAll('.slide').forEach((s,k)=>s.style.display=k=={i}?'block':'none')")
        pg.evaluate("document.fonts.ready"); pg.wait_for_timeout(150); pg.screenshot(path=f"{d}/slide{i+1}.png")
    b.close()
ins=sum([["-i",f"{d}/slide{i+1}.png"] for i in range(n)],[])
subprocess.run(["ffmpeg","-v","error","-y"]+ins+["-filter_complex",f"hstack={n},scale={300*n}:-1",f"{d}/prev.png"],check=True)
print("ok",n)

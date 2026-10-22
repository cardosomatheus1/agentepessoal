# uso: carrossel.py <pasta>  -> pasta/slide1.png… (1080x1350), cada .slide do index.html
import sys, os, subprocess
try:
    from playwright.sync_api import sync_playwright
except ImportError:  # the agent VM has patchright (same API) and its own Chromium (22/10)
    from patchright.sync_api import sync_playwright
CHROMES = ("/opt/pw-browsers/chromium-1194/chrome-linux/chrome", "/a0/tmp/playwright/chromium-1228/chrome-linux/chrome")
d=os.path.abspath(sys.argv[1])
# a CSS background of a slide that was hidden only starts loading when the slide shows: wait for every one (22/10: the
# photo of c_garantia's slide 4 came out blank on a re-render)
FUNDOS = """Promise.all([...document.querySelectorAll('*')].map(e => getComputedStyle(e).backgroundImage)
  .flatMap(b => [...b.matchAll(/url\\("?([^")]+)"?\\)/g)].map(m => m[1]))
  .map(u => new Promise(ok => { const i = new Image(); i.onload = i.onerror = ok; i.src = u; })))"""
with sync_playwright() as pw:
    b=pw.chromium.launch(executable_path=os.environ.get("CHROME") or next((c for c in CHROMES if os.path.exists(c)), None),args=["--allow-file-access-from-files"])
    pg=b.new_page(viewport={"width":1080,"height":1350})
    pg.goto(f"file://{d}/index.html"); pg.wait_for_timeout(800)
    n=pg.evaluate("document.querySelectorAll('.slide').length")
    for i in range(n):
        pg.evaluate(f"document.querySelectorAll('.slide').forEach((s,k)=>s.style.display=k=={i}?'block':'none')")
        pg.evaluate("document.fonts.ready"); pg.evaluate(FUNDOS); pg.wait_for_timeout(150); pg.screenshot(path=f"{d}/slide{i+1}.png")
    b.close()
ins=sum([["-i",f"{d}/slide{i+1}.png"] for i in range(n)],[])
subprocess.run(["ffmpeg","-v","error","-y"]+ins+["-filter_complex",f"hstack={n},scale={300*n}:-1",f"{d}/prev.png"],check=True)
print("ok",n)

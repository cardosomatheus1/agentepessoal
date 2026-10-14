from playwright.sync_api import sync_playwright
import os
d=os.path.dirname(os.path.abspath(__file__))
rod='''<div style="width:100%;font-family:sans-serif;font-size:7px;color:#58665e;padding:0 18mm;display:flex;justify-content:space-between"><span>Raiz Connect · Plano de marketing · Lucro na Mão em 30 Dias</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'''
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",args=["--allow-file-access-from-files"])
    pg=b.new_page(); pg.goto(f"file://{d}/plano.html"); pg.wait_for_timeout(800); pg.evaluate("document.fonts.ready")
    pg.pdf(path=f"{d}/Plano-de-marketing-Raiz-Lucro-na-Mao.pdf",format="A4",print_background=True,prefer_css_page_size=True,
           display_header_footer=True,header_template="<span></span>",footer_template=rod)
    b.close()

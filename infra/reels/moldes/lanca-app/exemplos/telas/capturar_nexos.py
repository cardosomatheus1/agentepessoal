# Captures NEXOS screens from the real site (dev.sejanexos.com.br): the hero demo window ("janela") and the
# product pieces ("recorte") placed inside that same window, so each print looks like the app screen it comes from.
import sys
from playwright.sync_api import sync_playwright
import os
OUT = os.path.dirname(os.path.abspath(__file__)) + "/"
JS = r"""
([titulo, sub, peca, menu, larg]) => {
  const fig = document.querySelector('figure[class*=janela]');
  const c = fig.cloneNode(true);
  const tela = c.querySelector('[class*=janelaTela]');
  if (peca !== null) {
    const rec = document.querySelectorAll('li[class*=fachada_peca] > [class*="fachada_recorte__"]')[peca].cloneNode(true);
    const linha = tela.querySelector('[class*=janelaLinha]').cloneNode(true);
    const cab = tela.querySelector('[class*=janelaCabeca]').cloneNode(true);
    cab.querySelector('[class*=janelaTitulo]').textContent = titulo;
    cab.querySelector('[class*=janelaSubtitulo]').textContent = sub;
    tela.innerHTML = ''; tela.append(linha, cab, rec);
    rec.style.marginTop = '18px'; Object.assign(tela.style, {display: 'block', flex: '1 1 auto', minHeight: '0', overflow: 'hidden'}); if (innerWidth > 800) { rec.style.maxWidth = (larg || 800) + 'px'; rec.style.zoom = '1.4'; }
  }
  c.querySelectorAll('[class*=janelaMenu] li').forEach((li, i) => {
    li.className = document.querySelector('[class*=janelaMenu] li:nth-child(2)').className;
    if (i === menu) li.className = document.querySelector('[class*=janelaMenuAtivo]').className;
  });
  const box = document.createElement('div');
  box.id = 'cap';
  Object.assign(box.style, {position: 'fixed', inset: '0', zIndex: 2147483647, background: 'rgb(10,10,10)', overflow: 'hidden', padding: '0'});
  Object.assign(c.style, {margin: '0', width: '100%', height: '100%', maxWidth: 'none', borderRadius: '0', transform: 'none', opacity: '1', animation: 'none', position: 'absolute', inset: '0'});
  box.appendChild(c); document.querySelector('[class*=fachada_fachada]').appendChild(box);
  document.documentElement.style.overflow = 'hidden';
  scrollTo(0, 0);
}
"""
TELAS = [  # name, title, subtitle, piece index (None = the hero window itself), active menu item
  ("conversas", "Conversas", "2 sem resposta", 1, 1, 470),
  ("clientes", "Clientes", "5 retornos para hoje", 2, 2, 800),
  ("resultados", "Resultados", "Setembro fechado", 4, 5, 800),
  ("sobra", "Resultados", "Setembro fechado", 5, 5, 440),
  ("hoje", None, None, None, 0, 800),
]
def main(modo):
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        vp = {"width": 300, "height": 649} if modo == "celular" else {"width": 1440, "height": 900}
        sel = sys.argv[2:]
        ctx = b.new_context(viewport=vp, device_scale_factor=2.6 if modo == "celular" else 2, is_mobile=modo == "celular", has_touch=modo == "celular")
        for nome, tit, sub, peca, menu, larg in TELAS:
            if sel and nome not in sel: continue
            pg = ctx.new_page()
            pg.goto("https://dev.sejanexos.com.br/", wait_until="networkidle")
            h = pg.evaluate("document.body.scrollHeight")
            for y in range(0, h, 400): pg.evaluate(f"scrollTo(0,{y})"); pg.wait_for_timeout(60)
            pg.wait_for_timeout(600)
            pg.evaluate(JS, [tit, sub, peca, menu, larg])
            pg.wait_for_timeout(500)
            pg.screenshot(path=f"{OUT}nexos-{'pc-' if modo != 'celular' else ''}{nome}.png")
            pg.close()
        b.close()
main(sys.argv[1])

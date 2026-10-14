# Etapa I do kit para carrossel: confere cada slide antes de subir.
# uso: validar_carrossel.py c_<nome> [...]   -> sai 1 se algum slide falhar
import sys, os, json
from playwright.sync_api import sync_playwright
JS = r"""async (i) => {
  const s = [...document.querySelectorAll('.slide')]; s.forEach((e,k)=>e.style.display=k==i?'block':'none');
  await document.fonts.ready; await new Promise(r => setTimeout(r, 150));
  const el = s[i], erros = [], r = el.getBoundingClientRect();
  if (r.width !== 1080 || r.height !== 1350) erros.push(`tamanho ${r.width}x${r.height}`);
  for (const f of ['800 40px M', 'italic 40px S']) if (!document.fonts.check(f)) erros.push('fonte não carregou: ' + f);
  const pe = el.querySelector('.pe').getBoundingClientRect(), area = el.querySelector('.area');
  if (area) {
    const a = area.getBoundingClientRect();
    for (const c of area.querySelectorAll('*')) {
      if (c.closest('.celular') && !c.classList.contains('celular')) continue;  // tela recortada de propósito
      const b = c.getBoundingClientRect(); if (!b.width || !b.height) continue;
      if (b.bottom > a.bottom + 1 || b.right > 1080 - 60) erros.push(`sai da área: <${c.tagName.toLowerCase()} class="${c.className}"> "${(c.textContent||'').trim().slice(0,40)}"`);
      if (b.bottom > pe.top - 16) erros.push(`encosta no rodapé: "${(c.textContent||'').trim().slice(0,40)}"`);
    }
  }
  for (const h of el.querySelectorAll('h1,h2')) { const n = h.textContent.trim().split(/\s+/).length; if (n > 12) erros.push(`manchete com ${n} palavras (máx. 12)`); }
  for (const t of el.querySelectorAll('*')) {
    if (![...t.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    const fs = parseFloat(getComputedStyle(t).fontSize); if (fs < 20) erros.push(`texto pequeno (${fs}px): "${t.textContent.trim().slice(0,30)}"`);
  }
  if (/[\u{1F300}-\u{1FAFF}\u{2600}-\u{26FF}]/u.test(el.innerText)) erros.push('emoji no slide');
  if (/R\$\s?\d/.test(el.innerText) && !/exemplo|valores ilustrativos|R\$ ?197|R\$ ?1\.697|R\$ ?(600|400|200|300)\b/i.test(el.innerText) && !el.closest('[data-sem-exemplo]'))
    erros.push('número em R$ sem "valores de exemplo" no slide');
  for (const img of el.querySelectorAll('img')) if (!img.complete || !img.naturalWidth) erros.push('imagem não carregou: ' + img.src.split('/').pop());
  return [...new Set(erros)];
}"""
ruim = 0
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=os.environ.get("CHROME") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args=["--allow-file-access-from-files"])
    for pasta in sys.argv[1:]:
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        pg.goto(f"file://{os.path.abspath(pasta)}/index.html"); pg.wait_for_timeout(800); pg.evaluate("document.fonts.ready")
        n = pg.evaluate("document.querySelectorAll('.slide').length")
        for i in range(n):
            e = pg.evaluate(JS, i)
            if e: ruim += 1; print(f"{pasta} slide {i+1}: " + "; ".join(e))
        print(f"{pasta}: {n} slides conferidos")
    b.close()
sys.exit(1 if ruim else 0)

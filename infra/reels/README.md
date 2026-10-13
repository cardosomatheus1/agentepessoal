# Reels em motion da @raiz.connect

Cada pasta é um Reel: `falas.json` (narração, voz da AWS Polly) e `index.html` (animação com `render(t)`).
As fontes Inter ficam em `base/fonts/` (copie de `/usr/share/fonts/opentype/inter/`).

    python3 base/gen.py 2_brigadeiro        # gera a voz e os tempos (tempos.js)
    python3 base/render.py 2_brigadeiro 3 8 # prévia de quadros -> prev.png
    python3 base/render.py 2_brigadeiro     # vídeo final -> reel.mp4 (1080x1920, 30 fps)

Os valores são de exemplo e aparecem como "valores de exemplo" na tela.
Sem o Chromium do Playwright instalado, aponte `CHROME=/caminho/do/chrome`.

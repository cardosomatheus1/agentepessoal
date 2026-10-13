# Reels em motion da @raiz.connect

Cada pasta é um Reel: `falas.json` (narração, voz da AWS Polly) e `index.html` (animação com `render(t)`).
As fontes Inter ficam em `base/fonts/` (copie de `/usr/share/fonts/opentype/inter/`).

    python3 base/gen.py 2_brigadeiro        # gera a voz e os tempos (tempos.js)
    python3 base/render.py 2_brigadeiro 3 8 # prévia de quadros -> prev.png
    python3 base/render.py 2_brigadeiro     # vídeo final -> reel.mp4 (1080x1920, 30 fps)

Os valores são de exemplo e aparecem como "valores de exemplo" na tela.
Sem o Chromium do Playwright instalado, aponte `CHROME=/caminho/do/chrome`.

Visual v2: `base/kit.css` + `base/kit.js` (vidro, texto por palavra, transição em círculo, granulação, quadros de filmagem).
Filmagens (AWS Nova Reel) ficam fora do git: `base/frames.sh video.mp4 <pasta>` gera `<pasta>/v/q0001.jpg…`.
Carrosséis (`c_*`): `python3 base/carrossel.py c_frases` gera slide1.png… (1080x1350).
`r_pov`: Reel sem voz (o áudio em alta entra na hora de postar).

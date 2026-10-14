# Reels em motion da @raiz.connect

> **Regra do Matheus (14/10/2026): todo vídeo da Raiz Connect segue o kit de motion graphics da Raiz**, que mora no
> repositório erp-saas (branch `claude/integrar-instrucoes-ywizpw`): `.claude/skills/motion-graphics/SKILL.md`
> (etapas A–K), `marketing/brand-system.md` (logo, cores, Manrope + Instrument Serif, área segura, movimento, som,
> voz Carolina) e o modelo `marketing/_modelo-motion-html/`. Cada vídeo novo é um projeto em `marketing/<nome>/` lá.
> Os Reels desta pasta e os moldes deste repositório **não** valem mais para vídeo da Raiz (ficam como histórico e,
> no caso dos moldes, para outras marcas).
>
> **Carrosséis (`c_*`, 14/10/2026):** seguem a mesma identidade do kit (o Matheus achou os anteriores feios). Base
> comum em `base/raiz-carrossel.css` + `base/raiz-carrossel.js` (topo com logo, rodapé com progresso) e fontes/logos
> do kit em `base/kit/`. Fundo night com creme alternado, lima só para o que sobra, uma palavra em Instrument Serif
> por slide, números com `tabular-nums`, "valores de exemplo" em todo número, sem emoji. Gere com
> `python3 base/carrossel.py c_<nome>` (1080×1350). Para trocar as imagens de um post já agendado, suba os JPGs nos
> mesmos endereços do S3 com a mesma quantidade (a agenda guarda o endereço, não a imagem).
>
> **Padrão x liberdade criativa (Matheus, 14/10, mais tarde):** a qualidade é a do kit, mas nem todo vídeo ou
> carrossel segue o mesmo molde, "senão fica repetitivo e sem graça". **Fixo** (é o que faz reconhecer a marca):
> logo, Manrope + Instrument Serif, a família de cores do brand-system (night, creme, verdes, lima para o que sobra),
> as regras de comunicação (valores de exemplo, sem promessa, sem jargão, sem emoji), a voz Carolina e o processo
> (materiais reais, revisão com nota ≥ 8, validação). **Livre** (muda de peça para peça): o conceito visual, a
> composição e o grid, o formato do slide/cena (foto, tipografia gigante, tela do produto, conversa, caderno,
> etiqueta, recibo...), o ritmo, a textura, as cores de apoio dentro da família, a trilha e as transições. Duas
> peças seguidas não usam o mesmo conceito. A base `raiz-carrossel.css` é ponto de partida, não molde.
>
> **Processo do kit nos carrosséis (pedido do Matheus, 14/10):**
> - **B, materiais reais:** tela real do produto (`base/kit/tela-calculadora.jpg`, bloco `.cta-calc` no slide final).
>   Foto de comida/produto é foto real ou gerada (Stability no Bedrock, como no kit), nunca desenhada em código, com
>   "imagem ilustrativa" no slide. Tudo registrado em `base/kit/inventario.md`.
> - **H, revisão:** folha de contato e notas de 1 a 10 (narrativa, identidade, composição, legibilidade, técnica,
>   plano) por um revisor que não fez os slides; mínimo 8 em tudo; até 3 ciclos.
> - **I, validação:** `python3 base/validar_carrossel.py c_<nome>` precisa sair limpo antes de subir: tamanho, fontes
>   carregadas, nada fora da área ou encostando no rodapé, manchete ≤ 12 palavras, texto ≥ 20 px, sem emoji, imagem
>   carregada, número em R$ com "valores de exemplo".


Cada pasta é um Reel: `falas.json` (narração com a Carolina, do Amazon Nova 2 Sonic; `npm ci` em `moldes/motor/`) e `index.html` (animação com `render(t)`).
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

# navegador_visual

Ajusta os painéis **Navegador**, **Computador** e **Celular** sem alterar os plugins originais:

- **No celular:** os painéis abrem em tela cheia.
- **Teclado na tela (xpra, no Navegador e no Computador):** fica escondido por padrão; o botão de teclado
  (na barra do Navegador e no topo do Computador) mostra ou esconde.
- **Afastar / aproximar:** `−` e `+` mudam o tamanho da tela remota (100% a 250%; abaixo de 540 px de largura ela cresce sozinha, porque o Chromium não fica mais estreito que isso) e a imagem é reduzida
  para caber no painel, então dá para ver a página inteira. A escolha fica salva no aparelho.
- **Zoom com os dedos na página toda:** a interface vinha com `maximum-scale=1`, que desliga a pinça do celular; agora ela fica liberada (até 5x).
- **Lupa (Navegador, Computador e Celular):** dois dedos ampliam e movem a tela (no PC, Ctrl + rodinha);
  o selo `− 150% + ⟲` aparece quando ampliado e volta ao normal. No Celular a tela vem de outro endereço,
  então o botão `🔍 Zoom` liga uma camada que recebe os gestos (um dedo move); desligue para tocar no celular.
- **Gestos de celular no Navegador:** um toque clica; arrastar com um dedo rola a página (ou move a tela ampliada);
  segurar ~0,5 s e arrastar arrasta de verdade (controles deslizantes, peça de captcha); dois dedos dão zoom.
  Os toques vão pela API do navegador do agente, com a posição corrigida: a janela dele fica com as barras de
  abas e endereço acima da tela, então ponto na tela ≠ ponto na página.
- **Diagnóstico:** `api/diag.py` guarda em `/a0/usr/navegador_visual/diag.log` o que os toques fizeram no aparelho.
- **Teclado do celular ao tocar num campo (Navegador):** um toque na tela pergunta ao navegador do agente
  (`api/foco.py`) se o foco caiu num campo de texto; se sim, o teclado do próprio celular sobe e o que se digita
  vai para esse campo (inclusive previsão de palavras e corretor); tocar fora ou em Voltar o recolhe.
- **Digitar:** o botão de lápis abre uma barra embaixo; o texto vai para o campo focado na página com o
  teclado do próprio celular/PC, com botões de Enter, apagar e Tab.

A lupa está em `extensions/webui/initFw_end/lupa.js`; o resto em `extensions/webui/initFw_end/navegador-visual.js`, que envolve três métodos do store
`browserPage` (`surfaceViewportMeasurement`, `prepareInteractiveViewFrame`, `applyViewer`).

# navegador_visual

Ajusta os painéis **Navegador**, **Computador** e **Celular** sem alterar os plugins originais:

- **No celular:** os painéis abrem em tela cheia.
- **Teclado na tela (xpra, no Navegador e no Computador):** fica escondido por padrão; o botão de teclado
  (na barra do Navegador e no topo do Computador) mostra ou esconde.
- **Afastar / aproximar:** `−` e `+` mudam o tamanho da tela remota (100% a 250%; abaixo de 540 px de largura ela cresce sozinha, porque o Chromium não fica mais estreito que isso) e a imagem é reduzida
  para caber no painel, então dá para ver a página inteira. A escolha fica salva no aparelho.
- **Digitar:** o botão de lápis abre uma barra embaixo; o texto vai para o campo focado na página com o
  teclado do próprio celular/PC, com botões de Enter, apagar e Tab.

Tudo está em `extensions/webui/initFw_end/navegador-visual.js`, que envolve três métodos do store
`browserPage` (`surfaceViewportMeasurement`, `prepareInteractiveViewFrame`, `applyViewer`).

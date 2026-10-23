---
name: navegador-leitura-e-rolagem
description: "Abrir páginas no navegador do agente, rolar e dizer o que aparece (seção no topo, título, trecho), com rolagem que funciona e leitura confiável da posição."
version: 1.0.2
adaptada_hermes: 2026-10-23
origem_a0: 1.0.2
origem: aprendizado
atualizada: 2026-10-21
tags: ["aprendizado"]
trigger_patterns:
  - "role a página"
  - "rolar"
  - "scroll"
  - "seção no topo"
  - "título da seção"
  - "abra no navegador"
  - "wheel"
  - "o que aparece na página"
---

# Leitura e rolagem de páginas no navegador

Vale para pedidos simples do tipo "abra tal página, role N vezes e me diga o que aparece". Para login, veja login-sites-navegador. Para formulários, veja formularios-portais-parceiros.

## Fluxo
1. Abra a URL com `browser_navigate`. Redirecionamento de URL é normal (ex.: um título entre parênteses que vira outra página). Siga na página final e cite a URL final no relato.
2. Para rolar a página inteira, use `browser_scroll` (direction "down", ou "up" para voltar).
3. Se o Matheus pediu N rolagens, faça exatamente N chamadas de `browser_scroll`, uma de cada vez, e confira que cada uma executou. Se alguma não executar, o número de rolagens fica incerto.
4. Se ele pediu espera ("espere 2 segundos"), rode `terminal` com `sleep N` depois da rolagem, usando esse tempo.
5. Para saber qual seção está no topo, não adivinhe pelo print. Use `browser_console` para listar os títulos **visíveis e com texto** e pegar o mais próximo do topo. Páginas como a Wikipédia têm h2/h3 ocultos e vazios que viram "primeiro visível" com texto em branco. Use como expression:
   `(() => { const hs=[...document.querySelectorAll('h1,h2,h3,h4')].filter(h=>h.offsetParent!==null && h.innerText.trim()); const vis=hs.filter(h=>h.getBoundingClientRect().top>=0); const antes=hs.filter(h=>h.getBoundingClientRect().top<0); const el=document.elementFromPoint(innerWidth/2, 120); return {primeiro_visivel: vis[0]?.innerText.trim(), ultimo_acima: antes.at(-1)?.innerText.trim(), trecho_no_topo: (el?.innerText||'').slice(0,150), scrollY: window.scrollY}; })()`
   A seção "no topo" é a do último título que já passou do topo, ou a do primeiro visível, se ele estiver colado no topo. Se os dois forem diferentes, diga qual critério usou.
6. Se o último título acima for o `h1` do artigo (nome da página), o topo ainda está na **introdução**, antes da primeira seção numerada. Diga isso ("introdução do artigo X") e cite também o primeiro título que vem a seguir. Não apresente o `h1` como se fosse uma seção.
7. Se quiser conferir visualmente, use `browser_vision` com a pergunta. O print sozinho não substitui a leitura por `browser_console`.

## Armadilhas
- Não responda "não consegui identificar" quando o `browser_console` resolve. Tente a leitura pelo DOM antes de desistir de uma pergunta de leitura. Se o resultado vier com campo vazio (`""`), é título oculto: refaça com o filtro de visíveis e não responda em cima do vazio.
- Só cite texto da página que veio do `browser_console`, do `browser_snapshot` ou do `browser_vision`. Não complete trechos de memória: citação inventada tira a confiança na resposta.
- Faça só o que foi pedido ("não faça mais nada"). Nada de rolagens extras para tentar de novo. Se precisar corrigir, diga isso numa frase.
- A resposta final é curta: a seção encontrada, quantas rolagens foram feitas e a URL final. Sem narrar os erros intermediários.

---
name: landing-page-raiz
description: "Criar landing page HTML de arquivo único da oferta da Raiz Connect (nome da oferta, garantia exata, chamada para a calculadora grátis, marca) e gravar prints de celular e computador com a largura pedida."
version: 1.0.1
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-23
tags: ["aprendizado"]
trigger_patterns:
  - "landing page"
  - "landing.html"
  - "celular.png"
  - "computador.png"
  - "página da oferta"
  - "print 390"
  - "print 1440"
  - "oferta da Raiz"
---

# Landing page da oferta da Raiz (HTML único + prints)

Vale para pedidos de "faça uma landing page simples" da oferta/marca da Raiz Connect, com `landing.html` autocontido e prints de celular e computador. Não publica nem envia nada: só gera arquivos locais e abre no navegador do agente.

## Fluxo
1. **Material.** Se `contexto.zip` já estiver extraído (procure `entrada/extraido/` ou `trabalho/contexto/`), use-o. Se não, extraia com Python `zipfile` (`execute_code`), porque `unzip` e `file` não existem na máquina. Leia por inteiro (`read_file`):
   - `segundo_cerebro/Raiz/oferta.md`: nome da oferta, o que inclui, preço, **garantia** e links oficiais.
   - `segundo_cerebro/Raiz/marca.md` e `marca_raiz/marca.json`: cores, fontes, regras de comunicação.
   - `marca_raiz/logo_claro.png` e `logo_escuro.png`, e as fontes (Manrope e Instrument Serif; procure `trabalho/fonts/`).
   - Se a leitura vier truncada, leia o trecho que faltou, pois as regras de comunicação ficam no meio do texto.
2. **Conteúdo.** Use o nome da oferta, a garantia **copiada palavra por palavra** do `oferta.md` (inclusive os exemplos entre parênteses) e a chamada "calculadora grátis" apontando para o link da calculadora que está no `oferta.md`. Valores e benefícios vêm só do `oferta.md`. Não invente prazos nem promessas (ex.: "em 1 minuto" é do simulador de delivery, não da calculadora). A calculadora "começa sem cadastro", mas o preço sugerido vem no cadastro completo; não prometa mais que isso.
3. **Marca.** Cores da família da marca (verde-escuro, lima, creme), Manrope para texto e Instrument Serif para títulos. Logo claro sobre fundo escuro e logo escuro sobre fundo claro (confira olhando o print). **Sem emoji** (regra de comunicação da marca): use números, filetes ou formas CSS no lugar de ícones. Sem promessa de resultado e sem jargão.
4. **"Nada externo além de fontes".** Mesmo assim, embuta as fontes e os logos em base64 (`@font-face` com `data:`) para o arquivo abrir em qualquer lugar. Gere o HTML com Python em `execute_code` (f-string com chaves duplicadas no CSS) e grave em `landing.html`.
5. **Abrir e fotografar.** `browser_navigate` com `file:///.../landing.html`, depois:
   - Ajuste a largura pedida com `browser_cdp` method `Emulation.setDeviceMetricsOverride` (celular: `{"width":390,"height":844,"deviceScaleFactor":1,"mobile":true}`; computador: `{"width":1440,"height":900,"deviceScaleFactor":1,"mobile":false}`), tire o print da página inteira com `browser_cdp` method `Page.captureScreenshot` e params `{"format":"png","captureBeyondViewport":true}`, e grave o base64 devolvido direto no nome pedido (`celular.png`, `computador.png`) com `execute_code`.
   - **Meça o arquivo gerado**: `terminal` com `python3 -c "from PIL import Image; print(Image.open('celular.png').size)"`. A largura precisa ser exatamente a pedida. A barra de rolagem do navegador costuma tirar cerca de 15 px (o print sai 375 em vez de 390, 1425 em vez de 1440). Se acontecer, ponha no CSS `html{scrollbar-width:none}` e `::-webkit-scrollbar{display:none}`, ou aumente o viewport pela diferença, e tire de novo até bater.
   - Abra os dois prints com `vision_analyze` (caminho do arquivo) e olhe de verdade: logo visível e com contraste, garantia legível, botão da calculadora, nada cortado no celular.
6. **Resposta curta**: o que fez, o que decidiu sozinho (qual link usou, o que cortou), caminho dos arquivos e as larguras reais medidas dos prints.

## Armadilhas
- **Não declare "390 px" ou "1440 px" sem medir.** Escrever a largura do viewport no relato como se fosse a do arquivo entrega print fora da especificação.
- **Emoji como ícone viola a marca.** Trocar ícone externo por emoji "para não depender de CDN" resolve um problema e cria outro; use CSS puro.
- **Garantia "exata" é cópia literal**, não paráfrase. Compare o trecho do HTML com o `oferta.md` antes de entregar.
- **Só os links oficiais do `oferta.md`**, no formato que ele indica. Não invente URL de cadastro.
- Se o pedido proíbe perguntar, decida o mais sensato e registre cada decisão na resposta final.

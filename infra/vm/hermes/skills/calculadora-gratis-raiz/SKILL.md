---
name: calculadora-gratis-raiz
description: "Preencher a calculadora grátis de precificação da Raiz (raizconnect.com.br/materiais/precificacao/calculadora) com um exemplo, ler quanto sobra por venda e gravar o print do resultado."
version: 1.0.1
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-23
tags: ["aprendizado"]
trigger_patterns:
  - "calculadora grátis"
  - "calculadora da Raiz"
  - "precificação"
  - "quanto sobra por venda"
  - "calculadora.png"
  - "materiais/precificacao"
---

# Calculadora grátis de precificação da Raiz (navegador)

Vale para pedidos de abrir a calculadora pública, preencher um exemplo e reportar "quanto sobra" segundo a própria página, com print. Não precisa de login nem de cadastro. NÃO preencha nome, e-mail e WhatsApp do formulário final (é captação de lead): o diagnóstico com o valor que sobra aparece antes dele.

## Fluxo
1. `browser_navigate` na URL e `browser_snapshot` (full=true). A calculadora é um assistente de 6 etapas: Produto, Quanto custa, Onde vende, Negócio e mercado, Promoção, Diagnóstico. Releia com `browser_snapshot` a cada etapa, porque as refs mudam.
2. Etapas 1 e 2: o nome do produto é obrigatório. Se o pedido não deu, invente um simples (ex.: "Marmita teste") e diga isso na resposta. Preencha custos com `browser_type` na ref do campo, no formato brasileiro (`3,00`), e confira o "✓ conferido".
3. Etapa 3 ("Quanto o canal e os impostos levam"):
   - Os campos já vêm com padrões (ex.: Taxa de pagamento 3). Zere o que o pedido não mencionou, senão o resultado sai diferente do exemplo.
   - "Taxa do app" não tem campo próprio: lance o valor fixo em **Outras cobranças por pedido**. Comissão em % só se o pedido deu.
   - "Onde este produto é vendido?" parece select, mas escolher a opção pela ref falha. Funciona `browser_console` com expression no `<select>` real (`document.querySelector('select')`): defina `value` com o texto da opção e dispare `input` e `change`. Depois confira no `browser_snapshot` o `selected=`.
   - Se o pedido não diz o canal, escolha o mais coerente (app de delivery → iFood) e diga na resposta.
4. Avance só com o botão **Próximo** pela ref (`browser_click`) (e **Ver meu diagnóstico** na etapa 5). Não clique nas abas numeradas: não faz nada e dispara o aviso de ação repetida.
5. Etapa Diagnóstico: o texto "No preço atual de R$ X, sobram **R$ Y** por venda (Z%)" é a resposta. Leia dele, não de conta própria. Se Y não bater com preço − custos − taxas, confira se algum padrão ficou sem zerar.
6. Print: `browser_scroll` até o topo do bloco do diagnóstico e use `browser_vision` perguntando se o texto "sobram R$ …" está visível no print, antes de entregar. Se não estiver, role e tire de novo. Use o caminho do print que ele devolve.
7. Gravar: o print sai em JPEG. Se o pedido manda `.png`, converta de verdade com `terminal` (`python -c "from PIL import Image; Image.open(src).convert('RGB').save(dst,'PNG')"`), não só renomeie com `cp`. Confira com `file` e o tamanho.
8. Resposta curta: valores digitados, resultado literal da página (R$ e %), o que você decidiu sozinho (nome, canal, onde lançou a taxa, padrões zerados), caminho do arquivo.

## Armadilhas
- Repetir o mesmo clique que não funcionou não adianta; troque para a ref certa ou para o botão Próximo.
- Não diga que conferiu o arquivo do print se só listou o diretório: olhe a imagem de fato (`vision_analyze` no arquivo gravado).
- Não registre nem envie nada ao final (e-mail, WhatsApp, planilha): o pedido é só ler o resultado.

---
name: formularios-portais-parceiros
description: "Preencher formulários de qualificação/cadastro em portais de parceiros (99Food, Keeta e similares) pelo navegador: campos de texto, seletores, telefone, modal de loja de teste, leitura dos rótulos, inventário de campos e entrega com print. Só envia ou confirma quando o pedido autoriza."
version: 1.0.3
adaptada_hermes: 2026-10-23
origem_a0: 1.0.3
origem: aprendizado
atualizada: 2026-10-21
tags: ["aprendizado"]
trigger_patterns:
  - "formulário 99Food"
  - "formulário Keeta"
  - "cadastro de desenvolvedor"
  - "qualificação"
  - "preencher formulário"
  - "seletor de código do país"
  - "+55"
  - "campos opcionais"
---

# Preencher formulários de portais de parceiros

Vale para formulários de qualificação e cadastro de desenvolvedor (99Food, Keeta e portais parecidos, em geral Element UI/Vue). Login: skill login-sites-navegador. Por padrão NÃO envie: não clique em Enviar/Confirmar final, não aceite termos, não anexe arquivos. A exceção é quando o pedido manda criar ou "tentar de novo" (ver loja de teste abaixo).

## Fluxo
1. Use a página já aberta no formulário; não recarregue nem navegue (pode perder o que foi digitado). Se o formulário não estiver aberto, abra a URL pedida com `browser_navigate`.
2. `browser_snapshot` para pegar as refs atuais (`@e12`). Use sempre a ref do último snapshot: elas mudam (por exemplo, uma linha nova aparece depois de clicar em "Adicionar").
3. **Descubra o rótulo de CADA campo antes de preencher.** O snapshot muitas vezes mostra campos sem rótulo (só a ref). Não adivinhe pela ordem. Liste rótulo, placeholder, valor e obrigatoriedade pelo DOM com `browser_console`, por exemplo, com expression =
   `[...document.querySelectorAll('input,textarea')].map(e=>({ph:e.placeholder, v:e.value, rotulo:(e.closest('.el-form-item')?.querySelector('label')?.innerText||'').trim(), obrig:!!e.closest('.el-form-item.is-required')}))`
   Se o DOM não der o rótulo, use `browser_vision`. Placeholders em chinês (请选择 = "Selecione") indicam seletor.
4. **Mapeie todos os dados do pedido aos campos antes de digitar** (nome, e-mail, telefone, razão social, CNPJ, país, tipo, descrição). Preencha cada dado que o pedido trouxe.
5. Campos de texto: `browser_type` com a ref e o texto. Ele limpa o campo antes de digitar, então digitar em campo já preenchido substitui o valor e serve para testar outro formato. Confira o valor com novo `browser_snapshot` ou `browser_console`. Textos longos podem aparecer truncados com "..." no snapshot; é só exibição.
6. **Seletores/combobox** (campo com placeholder "Selecione"/"请选择"): clique no campo para abrir; a lista pode aparecer no fim do snapshot como texto solto, SEM ref. Digitar o nome da opção filtra a lista; depois clique na opção (pela ref, se o `browser_snapshot` full=true der uma, ou `browser_console` achando o item pelo texto e clicando nele). Confirme que o campo ficou com o valor certo (ex.: +55). Em telefone, o código do país fica no seletor e o número vai sem o código no input ao lado (se o seletor já mostra +55, digite só DDD+número).
7. Campos que o Matheus mandou deixar vazios ficam vazios; no relato, diga o formato que cada campo pede.
8. **Só pergunte ao Matheus por dados que não estão no pedido**, depois de ler rótulo e obrigatoriedade de todos os campos vazios. Pergunte uma vez, listando tudo que falta.
9. Entrega: print da página inteira (`browser_vision`, rolando com `browser_scroll` se precisar) e lista do que ficou em cada campo, lida do `browser_snapshot`/`browser_console`, não de memória. Botão Submit desabilitado costuma significar obrigatório vazio ou termos não marcados: diga qual.

## Modal "Adicionar estabelecimento de teste" (developer-food.99app.com)
Caminho: Gerenciamento de aplicativo → abrir o app de teste → botão "Adicionar estabelecimento de teste". Campos: Nome, AppShopID, plataforma, entrega, OpenAPI, cidade/coordenadas (travadas), telefone do gerente (+55 + número) com botão "Adicionar", e no rodapé Cancelar/Confirmar.
1. Preencha Nome e AppShopID por ref e confira o valor.
2. Telefone: `browser_type` na ref do input, depois "Adicionar" (aparece outra linha vazia de telefone; releia o `browser_snapshot` antes de usar refs). Para testar vários formatos, um de cada vez, digite o novo valor por cima (`browser_type` na mesma ref) e clique em "Adicionar" de novo, anotando o que o portal mostrou a cada um.
3. "Adicionar" sozinho não prova nada: o portal só valida o gerente ao **Confirmar**. Se o pedido é tentar criar a loja, clique em Confirmar antes de responder; sem isso o teste não terminou. Se o pedido proíbe criar, pare antes e diga que não confirmou.
4. A mensagem de erro (ex.: "Falha na solicitação") é um aviso curto que some. Leia o `browser_snapshot` ou use `browser_vision` logo depois do clique e cite o texto literal; se não houver motivo, diga que o portal só deu essa mensagem.
5. Se a loja for criada, o shop_id e o app_shop_id aparecem na lista de lojas do app; leia de lá, não invente.
6. Prefira clique por ref (`browser_click`). Outros jeitos de clicar neste modal podem não registrar; confira sempre com novo `browser_snapshot`.

## Armadilhas
- **Parar na metade sem ler os campos**: devolver "não li o rótulo desses campos" é pedido pela metade. Leia (passo 3) e preencha o que o pedido cobre.
- **Seletor que não rola**: se `browser_scroll` não muda a lista em 2 tentativas, pare de repetir. Mude de mecanismo: digitar para filtrar, setas + Enter via `browser_press`, `browser_console` pelo texto, `browser_vision` para ver onde a lista está.
- **Não deixe o pedido pela metade por causa de um bloqueio**: faça o que não depende do campo travado. Informe só o que ficou pendente.
- **Relate só o que fez.** Não diga "não cliquei em Confirmar" nem "tentei várias vezes" sem conferir; se corrigir depois, corrija de forma explícita e curta. Uma ação repetida igual não conta como tentativa nova.
- Se o pedido diz que a causa provável é outra (ex.: número precisa de conta no app de lojista), confirme com a mensagem real do portal antes de afirmar; não crie conta nesse outro app em nome do Matheus.
- Termos/privacidade: marque só se o pedido autorizou; NDA, contrato ou assinatura: pare e mostre ao Matheus. Captcha ou código por e-mail/SMS: peça ajuda e espere.

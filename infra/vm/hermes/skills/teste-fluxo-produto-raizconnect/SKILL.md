---
name: teste-fluxo-produto-raizconnect
description: "Testar de ponta a ponta o sistema Raiz Connect (raizconnect.com.br) como um cliente novo, com conta de teste, roteiro de módulos e relatório de problemas com prints."
version: 1.0.2
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-24
tags: ["aprendizado"]
ressemear: campos-raiz-2410
trigger_patterns:
  - "testar raizconnect"
  - "conta de teste"
  - "fluxo básico"
  - "cliente novo"
  - "onboarding"
  - "restaurante novo"
  - "relatório de problemas"
  - "ficha técnica"
---

# Testar o fluxo do produto Raiz Connect como cliente novo

Vale quando o Matheus (ou o operador em nome dele) pede para usar o sistema em produção como um cliente novo e relatar o que funciona e o que quebra. O trabalho é longo e tem muitos módulos. Faça o pedido inteiro. Um aviso de andamento não encerra a tarefa.

## Antes de começar
1. É uma tarefa longa: abra com `tarefa_iniciar` (um passo por módulo do roteiro) e siga a skill `tarefa-longa` (resultado de cada módulo no `tarefa_passo`, cadastro e qualquer ação de fora com `acao` antes e `prova` depois, uma entrega só no fim com `tarefa_concluir`). Se parar no meio, o vigia retoma sozinho; na retomada, confira o cadastro no site antes de refazer.
2. Senha da conta de teste: o pedido costuma mandar gerar uma senha forte e guardar no cofre com um nome dado. Gere a senha no `terminal`. Antes de dizer que não há como guardar, procure a ferramenta do cofre: use `cofre_descrever` ou faça um `tool_search` com os textos "senha", "cofre" e "secret". Para digitar a senha no site, use `§§secret(NOME)` dentro do `browser_type`. Nunca escreva a senha em claro no relato.
3. Só pare por falta de credencial depois de buscar a ferramenta. Nesse caso, faça uma única pergunta listando tudo o que falta (senha, e-mail, nome) e já adiante o que não depende dela.

## Cadastro
1. Na home, o botão "Começar meus 15 dias grátis" abre `#/register`. O cadastro tem 2 etapas: "Seus dados" (nome, e-mail, senha, confirmar senha) e "Sua empresa".
2. Use o formulário de e-mail e senha. NÃO clique no botão com a foto de perfil ("Imagem do perfil de ..."). Esse botão é o login com Google e abre um seletor com as contas pessoais do Matheus. Se o seletor abrir, saia dele sem escolher nenhuma conta (`browser_back` ou volte para `#/register` com `browser_navigate`).
3. Se o cadastro pedir confirmação por e-mail, confirme pela caixa do agente: use a skill email-outlook-web ou o Gmail só leitura do conector Google (`mcp__google__...`). Nome da empresa e CNPJ seguem o pedido. Deixe o CNPJ em branco se for opcional.

## Roteiro e limites
- Ordem: empresa, insumos, produtos, ficha técnica (conferir o custo calculado à mão), fornecedor e entrada de estoque, saldos e ajuste, produção, cliente, 2 vendas (balcão em dinheiro; cliente cadastrado em Pix manual), conferência da baixa de estoque, caixa e comanda, financeiro (a receber e a pagar), CMV e Dashboard.
- Faça os cálculos esperados (custo da ficha, saldo após venda, CMV) antes de olhar o resultado do sistema. Só assim a divergência vira um problema anotado.
- Não emita nota fiscal, não pague, não assine plano, não conecte maquininha nem iFood, não convide pessoas reais. Se uma tela empurrar para algum desses passos, pare ali e anote.
- Dê nomes claros aos dados de teste (prefixo TESTE) para facilitar a limpeza depois.

## Como anotar problemas
Para cada problema, registre:
- a tela;
- o que fez;
- o que esperava;
- o que aconteceu, com a mensagem literal;
- o caminho do print.

A mensagem costuma ser um aviso curto que some. Por isso, logo depois do clique, leia a página com `browser_snapshot` ou tire o print com `browser_vision`.

Salve as anotações num arquivo em `/a0/usr/workdir` durante o teste, não só de memória.

No relatório final, ordene os problemas do mais grave ao menos grave, diga o que funcionou e onde estão os prints.

Para formulários e refs, siga a skill formularios-portais-parceiros: leia os rótulos antes de preencher e use os refs do último `browser_snapshot`.

## Armadilhas
- Não termine na primeira etapa por um bloqueio contornável. Parar com o formulário vazio é entregar o pedido pela metade.
- Não marque um passo "falhou" na primeira tentativa: tente 3 caminhos (outro clique, teclado, outra tela) antes. "Não
  consegui usar o campo" não é defeito do sistema; diga no relatório o que fez e o que a tela mostrou (24/10: 4 de 10
  passos "falharam" por isso e o sistema funcionava).
- Campos de escolha com busca (ficha técnica "Selecione um insumo...", "+ Produto" da tabela de preço, fornecedor…)
  são comboboxes: clique no campo, digite no "Pesquisar por nome ou código", espere a lista e clique na opção
  (role=option) ou use setas + Enter.
- Min/Max: LT, ES e LC não têm botão de editar; são campos de número na própria linha. Digite e aparece "Salvar" na
  linha (ou "Salvar Alterações" em cima). Anote como sugestão de UX que eles não parecem editáveis.
- Lotes nascem de: produto com "Controlar lote e validade" ligado (cadastro do produto) + produção; entrada em
  "Movimentar estoque" com Validade; recebimento de pedido com "Validade de <item>". Teste os três antes de dizer que
  não há caminho.

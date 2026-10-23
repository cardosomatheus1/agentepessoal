---
name: pesquisa-concorrentes-tabela
description: "Pedidos avulsos do Matheus para listar os principais concorrentes da Raiz Connect com dados comparáveis (preço, integração iFood, Instagram, fonte) e gravar em CSV/tabela; parte do que ele já registrou e completa na web."
version: 1.0.1
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-23
tags: ["aprendizado"]
trigger_patterns:
  - "principais concorrentes"
  - "concorrentes da Raiz"
  - "concorrentes.csv"
  - "plano mais barato"
  - "integra com o iFood"
  - "instagram dos concorrentes"
  - "tabela de concorrentes"
---

# Tabela de concorrentes (pedido avulso, com CSV)

Vale quando o Matheus pede "os N principais concorrentes" com campos objetivos (preço do plano mais barato, integra iFood, @ do Instagram, fonte) e um arquivo. O relatório semanal/completo com ações e prazos é a skill relatorio-concorrentes. Esta cobre só a tabela pontual.

## Fluxo
1. **Primeiro o que ele já registrou. Só diga que consultou depois de a chamada dar certo.**
   - `cerebro` com `acao: consultar` e `texto: "concorrentes"` traz as decisões. A decisão vigente é que a Raiz é um sistema de gestão e que seus concorrentes são outros sistemas de gestão (não apps só de precificação nem mentorias). Leia isso ANTES de escolher a categoria.
   - A ferramenta `concorrentes` lista tudo o que ele acompanha, com grupos (direto / gestão / conteúdo), preço visto e Instagram já conferido. A saída vem cortada. Leia o arquivo indicado inteiro (`read_file`, ou `grep`/`sed` pelo `terminal`) em vez de decidir pelo trecho visível.
   - Se `cerebro` responder "NÃO FEITO" para uma ação, tente outra (`consultar`) na hora. Não siga adiante afirmando que consultou: o conferente barra a resposta.
2. **Escolha dos N**: use um critério explícito entre os do grupo certo (relevância para delivery/food service brasileiro, porte, presença no iFood) e diga no relato qual foi. Não pegue só os primeiros da lista.
3. **Completar na web**: faça uma busca com `web_search` por concorrente × dado (preço, integração iFood, Instagram). Depois leia as páginas oficiais com `web_extract`. Anote a URL de cada dado para a coluna fonte.
4. **Instagram**: o `web_search` serve só para achar o link `instagram.com/<perfil>`, com consultas tipo "<site do concorrente> instagram". Consultas genéricas devolvem lixo. A ordem de preferência para o @ é:
   - o @ já conferido na ferramenta `concorrentes`;
   - o linkado no site oficial ou no Linktree da marca.

   Perfil achado só em busca ou em rede de terceiro entra como "não confirmado" na coluna. A coluna fonte cita onde o @ apareceu de fato. Não coloque a URL do Instagram como fonte se você não a abriu.
5. **Preço**: use o plano pago ou gratuito mais barato divulgado em página oficial. Escreva a condição (anual × mensal, limite de pedidos, data da consulta). Se páginas oficiais divergem, grave o menor valor com a observação da divergência e as duas fontes.
6. **iFood**: separe "integra pedidos do marketplace" de "só logística/entrega sob demanda". Escreva sim / não / parcial com a nota, nunca arredonde.
7. **CSV**: grave na pasta pedida com `write_file`, com as colunas exatamente como no pedido. Ponha aspas nos campos com vírgula e separe várias fontes por " ; ". Confira com `cat` e `wc -l` pelo `terminal`.
8. **Resposta final curta**: traga a tabela enxuta, o critério de escolha, o que ficou não confirmado e o caminho do arquivo. Em modo "decida sozinho", liste as decisões tomadas, sem perguntar.

## Armadilhas
- Escolher a categoria de concorrente antes de ler a decisão registrada. O pedido manda usar primeiro o que ele já registrou, e confirmar depois é ordem trocada.
- Dizer "consultei o Cérebro" quando a chamada falhou: o juiz recusa e a resposta é perdida.
- Tratar como confirmado o que a pesquisa deixou como "não confirmado". Repasse a ressalva.

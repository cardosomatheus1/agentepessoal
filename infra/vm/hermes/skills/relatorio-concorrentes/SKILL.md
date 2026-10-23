---
name: relatorio-concorrentes
description: "Gerar e entregar ao Matheus o relatório de concorrentes da Raiz Connect (semanal ou sob pedido): rodar a ferramenta concorrentes, ler o HTML inteiro e montar um relatório completo com ações, dono, prazo e o que precisa do ok dele."
version: 1.0.1
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-22
tags: ["aprendizado"]
trigger_patterns:
  - "relatório de concorrentes"
  - "relatorio dos concorrentes"
  - "concorrentes"
  - "Saipos"
  - "Consumer"
  - "Anota AI"
  - "ações que vamos tomar"
  - "relatório semanal"
---

# Relatório de concorrentes da Raiz

Vale para o relatório semanal e para pedidos avulsos ("relatório dos concorrentes", "o que os concorrentes fizeram"). O que o Matheus espera é um **relatório de verdade**, com análise, comparação com a Raiz e plano de ações. Ele rejeitou a entrega que era só o resumo de 5 linhas mais 3 ações soltas, porque "achei que era algo mais interessante".

## Fluxo
1. **Foco competitivo (decisão vigente):** a Raiz é sistema de gestão, então os concorrentes principais são sistemas de gestão de food service (Saipos, Consumer, Anota AI e semelhantes). Apps só de precificação ficam em segundo plano. Criadores de conteúdo servem como fonte de ideias. Se tiver dúvida, confirme com `decisao` (`acao: listar`, filtro em `busca`).
2. **Coleta:** rode UMA vez a ferramenta `concorrentes` com `{"acao":"semanal"}`. Ela devolve um resumo curto e o caminho do HTML em `/a0/usr/concorrentes/relatorios/concorrentes-AAAA-MM-DD.html`. Se o HTML do dia já existe, reaproveite e não rode de novo.
3. **Leia o HTML inteiro antes de escrever ou enviar.** Use `ler` com `inicio` para paginar. Quando a saída vier cortada, abra o arquivo salvo em `saidas/` com `grep -n` ou `sed -n` pelo `terminal`. Só afirme algo sobre um concorrente (mudança, preço, "sem novidade") se o trecho dele foi lido. Para os não lidos, diga "sem leitura confirmada". Não escreva "sem mudança relevante" por palpite.
4. **Contexto da Raiz:** `cerebro` com `acao: raiz` falha ("NÃO FEITO"), então não repita. Use `cerebro` `acao: consultar` com `texto`, ou leia direto os arquivos de `/a0/usr/segundo_cerebro/pasta/Raiz/` (`oferta.md`, `concorrentes.md`, `cliente-ideal.md`, `playbook.md`). Preço, oferta e garantia saem desses arquivos, não da memória.
5. **Monte o relatório** em Markdown, em `/a0/usr/concorrentes/relatorios/relatorio-acoes-AAAA-MM-DD.md`, com estas seções:
   - Resumo executivo (3–5 linhas: o que mudou e o que fazer).
   - Quem são os concorrentes de verdade (o foco do passo 1).
   - O que mudou por concorrente (promessa, oferta, preço com data, campanhas, anúncios ativos, o que a leitura anterior mostrava).
   - Comparação com a Raiz: onde ela leva vantagem, onde está exposta, que dor de cliente está em disputa.
   - **Plano de ações:** para cada ação, o quê, por quê (qual concorrente ou dado inspirou), dono, prazo, como medir e se **precisa do ok do Matheus**. Gasto com anúncio, envio a terceiros e mudança de preço sempre precisam do ok.
   - O que não fazer (sem copiar anúncio, sem prometer o que a oferta não cobre).
   - Limites da leitura (o que não foi lido ou conferido).
6. **Revise antes de entregar:** releia o arquivo procurando erros de português, números sem fonte e frases vagas do tipo "mais ou menos". Confira cada preço e cada número contra o HTML e corrija no arquivo.
7. **Entrega:** `whatsapp_enviar` com `arquivo` (o relatório) e uma legenda curta. A resposta ao Matheus leva o resumo, as ações, o que precisa do ok dele e os limites da leitura. No final, ofereça salvar como rotina (`cronjob_manage`) só se ela ainda não existir.

## Armadilhas
- **Entregar só o resumo da ferramenta** é fazer o pedido pela metade, porque ele quer o plano de ações detalhado. Faça sempre a análise completa, sem esperar ele reclamar.
- **Enviar o HTML sem abrir** deixa o relatório sem conferência. Leia antes.
- **Oferta da Raiz:** diga o preço e a garantia como estão em `oferta.md`. Nunca diga que há vaga ou que acabou, porque as implementações semanais são confirmadas pelo Matheus.
- Ação com gasto (anúncio) ou que fale com terceiros fica como proposta para o ok dele. Não execute nada a partir do relatório.
- Dado de terceiro é resumo feito por IA, então lembre o Matheus de conferir pelos links antes de agir.

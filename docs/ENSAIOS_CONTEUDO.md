# Ensaios da produção de conteúdo (@raiz.connect)

Matheus, 11/11: "Bom simular ele fazer só e você checar a qualidade". Uma rodada = a rotina da semana (`4qfNuwRX`)
rodada à mão com a data simulada do planejamento (`infra/operador/ensaio_conteudo.py ligar ...`), a semana produzida
sozinha (Designer, Crítico, refação, Gestor) e depois conferida pelo operador olhando as artes e os quadros dos vídeos.
O que o Crítico aprova entra na agenda de verdade, nos dias reais; o que o operador acha ruim é cancelado pelas
ferramentas do plugin (`cancelar_conteudo.py`).

Placar: stories aprovados/7 e feed aprovado/4, "sozinho" (sem mão do operador) e "ok na revisão" (o que o operador
olhou e deixou sair). Meta: 6/7 e 3/4 sozinho, com a revisão concordando.

| Rodada | Quando | Semana simulada | Stories | Feed | Tempo | O que derrubou |
|---|---|---|---|---|---|---|
| 1 | 11/11 tarde | 19 a 25/11 (`s20261118-1`) | 3/7 | 0/4 | ~3 h | formato da vaga não imposto ao Designer (ficha "reel" em vaga de carrossel); moldes de cliente final para a Raiz (comentário de cliente inventado); todo POV de humor morria na regra da tela real; story que chama o post julgado antes do post existir |
| 2 | 11/11 noite | 19 a 25/11 (`s20261118-2`) | 7/7 (um redesenhado pelo operador depois de corrigir o layout tela-zoom) | 2/4 sozinho, 3/4 com o operador rejulgando depois de corrigir a regra | ~4 h | carrossel 24/11: "ficha: produto: falta" e conta sem origem; Reel 25/11: número sem "valores de exemplo", depois "não mostra coxinhas" (regra lida errado), descartado em 4 versões |
| 3 | 12/11 00:36 a 04:10 | 26/11 a 02/12 (`s20261125-1`) | 1ª passada 3/7; no fim 7/7 no Crítico (2 criados pelo Gestor), 6/7 na revisão (27/11 saiu junto com o post) | 1ª passada 0/4; no fim 3/4 no Crítico, 2/4 na revisão | ~3,5 h, com duas travas de 15 min do navegador e a produção refeita | o Chromium travava no TMPDIR do Hermes (render de 15 min, story de 16 min); o Designer escrevia descrição no campo de foto e inventava foto; correção "ilegível" sem segunda tentativa e o Crítico chamado sem arte ("a arte não veio"); o Gestor estourava as 8.000 fichas pensando e voltava sem texto ou com o JSON cortado; quadro 2 do POV tirado no meio da virada (lido como texto cortado); POV com relógio 19:45 sobre 23:12; ideia de regra de app de terceiro (repasse, estorno) que o Cérebro não confirma; "Valores de exemplo." depois de cada frase. Revisão: quiz de 27/11 com a capa que já dava a resposta (cancelado); Reel de 29/11 bom, com "(valores de exemplo)" repetido em cada passo; mito de 01/12 bom; Reel de 02/12 (criado pelo Gestor, aprovado depois) com pizza de pepperoni e "PRA VOCÊ" no fecho (cancelado) |
| 4 | 12/11 04:10 a 06:10 | 03 a 09/12 (`s20261202-1`) | 1ª passada 6/7 (o 7º esperava o Reel); no fim 7/7, revisão 7/7 | 1ª passada 1/4; no fim 3/4 no Crítico (09/12 ainda em refação quando parei), revisão 3/4 (um bom, dois corretos mas fracos) | produção 15 min; ~2 h com a refação | o POV semanal reprovado como "mais do mesmo" do POV da semana anterior (regra errada, corrigida); Designer devolvendo "bloqueado, preciso de dado real" no custo-escondido; molde chat apagando as mensagens na virada (lido como ilegível); Gestor do ensaio sem teto próprio (gastou o do dia real). Revisão: POV de 06/12 bom (conta da pizza meio a meio fecha); carrossel de 04/12 fino (pergunta-cliente: uma pergunta e uma resposta de 21 min); quiz de 08/12 com a explicação citando a sobra de 13 e 12 reais que a peça não mostra |
| revisão | 12/11 00:30 | fila real 12 a 25/11 | 13 stories olhados: todos ok | 7 posts olhados: 5 ok, 2 cancelados | | 20/11 (pergunta-cliente "quando o dinheiro do app entra"): a resposta não responde e a tela é a da cozinha; 24/11 (quiz): capa quase vazia começando por "Valores de exemplo:". Os dois tinham passado no Crítico. O story de 20/11 que chamava o carrossel saiu junto. |

## Produção real (fora do ensaio), 01 a 12/11
- Feed publicado: 03, 06, 08 e 10/11 (todos carrosséis). Nenhum Reel saiu desde 01/11: 01, 08 e 11/11 cancelados
  depois de reprovações; 11/11 ficou sem post nenhum.
- Crítico: de 04 a 11/11, cerca de 170 reprovações para 45 aprovações (10/11: 31 x 4; 11/11: 47 x 19, já com o
  ensaio). O Gestor bateu o teto do dia (US$ 4) em 10 e 11/11; em 11/11 o ensaio gastou o teto e o Gestor real ficou
  parado do fim da tarde até a meia-noite.
- A fila de 12 a 18/11 (feita depois das correções de 11/11) está boa: os 2 Reels (15 e 18/11) conferidos quadro a
  quadro, contas fechando; o carrossel de 13/11 é fraco (genérico, "3 erros que custam caro") mas correto.

## Onde parou (12/11, 06:15 UTC)
- Ensaio desligado; o laço que acelerava a refação foi parado. O Reel de 09/12 (`s20261202-1-12`) segue na refação
  normal do agente: se o Crítico aprovar, entra na agenda sem ter passado pela revisão do operador (conferir).
- Dias sem post no feed por cancelamento da revisão: 20/11 e 24/11 (a rotina de 16/11 e a de 23/11 refazem), 25/11
  (Reel descartado na rodada 2), 27/11 e 02/12 (a rotina de 23/11 e a de 30/11 refazem).
- Gestor real de 12/11: o teto do dia (US$ 4) foi gasto pelos ensaios antes da correção do teto separado; volta à
  meia-noite. Dali em diante o ensaio tem teto próprio.

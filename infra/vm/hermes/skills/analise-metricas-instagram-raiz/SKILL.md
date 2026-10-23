---
name: analise-metricas-instagram-raiz
description: "Analisar um CSV de métricas de posts do Instagram da Raiz (alcance total, melhor post, média) e recomendar a próxima semana à luz das metas do plano de marketing, gravando resumo.md."
version: 1.0.1
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-23
tags: ["aprendizado"]
trigger_patterns:
  - "metricas_instagram"
  - "alcance total"
  - "média de alcance"
  - "post com mais alcance"
  - "recomendação para a próxima semana"
  - "resumo.md"
  - "plano de marketing"
  - "metas do plano"
---

# Análise de métricas do Instagram da Raiz + recomendação

Vale para pedidos do tipo "com o CSV de métricas dos últimos N dias, diga alcance total, melhor post, média e uma recomendação considerando o plano de marketing". Não envia nem publica nada: só lê, calcula e grava o `resumo.md`.

## Fluxo
1. **Leia o CSV inteiro** (colunas típicas: data, tipo FEED/REELS, link, alcance, salvos, curtidas, comentários, compartilhamentos, views). Calcule com Python (`execute_code`, módulo `csv`), não de cabeça: total, média (total ÷ nº de posts), post de maior alcance (data + link) e total/média por tipo.
2. **Contexto do Matheus.** Se houver `contexto.zip`, extraia com Python em `execute_code` (`zipfile.ZipFile(...).extractall('/tmp/ctx')`); o `unzip` pode não existir. Dentro dele, em `segundo_cerebro/`:
   - `Decisoes/` (plano de marketing, ritmo do Instagram, público/posicionamento), `Raiz/oferta.md`, `Raiz/playbook.md`, `Raiz/indice.md`.
   - Se existir, `/a0/usr/conteudo/agenda.json` (a decisão do plano diz que a agenda de posts vale pelo que está lá).
3. **Procure as METAS de verdade antes de dizer que não existem.** Rode no `terminal` `grep -ril 'meta\|objetivo\|alcance\|seguidores\|leads' segundo_cerebro/` (ou use `search_files`) e leia os arquivos achados por inteiro com `read_file`. O plano completo pode ser um link externo que não dá para abrir; nesse caso, diga isso. Só então escreva "o plano não traz meta numérica de alcance" e deixe claro que qualquer número proposto é sugestão sua.
4. **Recomendação concreta e ancorada**: 2–4 ações ligadas ao ritmo vigente (posts por semana, formatos, dias, stories, público), cada uma com o dado que a sustenta. Se propuser meta numérica, a conta precisa fechar (ex.: "+50% sobre 211 = ~316") e dizer de onde vem.
5. **Grave `resumo.md`** na pasta pedida (`write_file`): primeiro os números pedidos (alcance total, melhor post com data e link, média), depois a leitura por formato, depois a recomendação. Confira o arquivo com `wc -l`/`head` no `terminal`.
6. **Resposta final curta**: o que fez, o que decidiu sozinho, caminho do arquivo.

## Armadilhas
- **Amostra pequena não vira conclusão firme.** Com poucos posts por formato, uma ou duas peças puxam a média; diga "nesta amostra" e cite os outliers (um Reel também pode ser um dos dois maiores alcances). Se os números não sustentam a tese, diga que é hipótese a testar.
- **Post recém-publicado (último dia) ainda não acumulou alcance**: avise que o valor baixo pode ser só falta de tempo, em vez de contá-lo como fraco.
- **Não invente dados que o CSV não tem** (horário de pico, público, origem do tráfego). Só use o que está nas colunas ou nas decisões do Cérebro.
- **Cheque a aritmética das metas e dos percentuais** antes de gravar; frase como "dobro +50%" que não bate com o número perde a confiança no resumo inteiro.
- Respeite as regras da oferta: no post público vale a oferta aprovada (Lucro na Mão); link/receita/vaga têm regras próprias na conversa privada. Não proponha pedir a receita nem dizer que acabaram as vagas.
- Fatos do posicionamento: a Raiz é sistema de gestão para food service (inclui pizzaria, hamburgueria, lanchonete, delivery), e o ritmo vigente é o da decisão mais recente do Instagram, não o de planos antigos.
- Em pedidos de "teste lado a lado" ou "sem perguntar", decida pelo mais sensato, registre cada decisão no resumo e na resposta, e não use `delegate_task` nem outros agentes (OpenClaw).

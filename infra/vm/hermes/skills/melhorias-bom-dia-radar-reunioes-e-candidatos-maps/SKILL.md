---
name: melhorias-bom-dia-radar-reunioes-e-candidatos-maps
description: "Complementa rotinas existentes com briefing objetivo, inbox só leitura, pesquisa pré-reunião, pós-reunião deduplicado, pipeline review e candidatos Maps com proveniência."
version: 1.0.0
adaptada_hermes: 2026-10-23
origem_a0: 1.0.0
tags: ["rotina"]
trigger_patterns:
  - "Bom Dia Radar"
  - "classificação inbox"
  - "pré-reunião"
  - "pós-reunião deduplicado"
  - "pipeline review"
  - "candidatos Maps"
---
# Melhorias Bom Dia Radar reuniões e candidatos Maps

Rotina salva em 17/10/2026.

## Quando usar
Nas rotinas existentes Bom Dia/Radar, briefing e resposta pós-reunião, revisão semanal de prospecção e entrada de CSV real Maps; decisão canônica #34, sem agendamentos novos.

## Entradas e acessos
Conector Google do Matheus somente leitura (ferramentas mcp__google__<ferramenta>, achadas com `tool_search` e chamadas com `tool_call`); `fios`/`decisao`/`ficha` canônicos; `prospeccao` contexto/playbook/metricas; adaptador local e instruções em /a0/usr/workdir/playbook_rotinas_20261017/local/README.md (ler com `read_file`). CSV Maps e HTML público associado ao site oficial, quando realmente disponíveis.

## Passos
1. Antes de agir, ler a decisão #34 e listar fios; conferir execução e registros anteriores. Não duplicar decisão, ficha, fio ou tarefa; não editar fontes canônicas diretamente.
2. Bom Dia: usar o conector Google (Agenda e Gmail, só leitura) para agenda do dia e threads recentes, fios existentes e pendências reais. Uma tela: foco, compromissos, respostas devidas comprovadas pela thread completa e até 3 prioridades. Não inferir vínculos, prazos ou compromissos; faltas de dados ficam explícitas.
3. Radar/inbox: somente classificação de leitura MANTER, BAIXA_PRIORIDADE ou INDEFINIDO com razão. Financeiro, boleto, segurança e conversas pessoais não são lixo. Não marcar lido, arquivar, excluir, rotular nem enviar. Atualizar fios apenas pelas ferramentas canônicas e somente quando há pendência comprovada; avisos deduplicados e limites existentes preservados.
4. Pré-reunião: identificar evento e participantes pelo convite; ler descrição, threads relevantes e fios. Quando pertinente, pesquisar com `web_search`/`web_extract` apenas informação pública confirmada da organização/pessoa identificada, citando URLs/data e incertezas. Não pesquisar nomes ambíguos como se fossem a mesma pessoa; não enviar conteúdo privado a buscadores. Entregar contexto, pendências e 2–3 perguntas, sem modificar agenda.
5. Pós-reunião: aguardar relato do Matheus; extrair apenas compromissos explícitos, ação, dono e prazo quando dito. Dedupe por evento_id + ação normalizada + dono, conferindo fios existentes e fontes. Usar `fios` salvar com id para atualizar existente; não inventar ligações. Somente depois de conferir registros, registrar o pós-reunião; não criar agendamento nem rotina (`cronjob_manage`) nesta implementação.
6. Pipeline review: ler contexto/metricas da `prospeccao` e sinais atuais. Respeitar assumidos pelo Matheus, pendente:, etapas, cotas e revisor. Apontar gargalos e próximos passos sem mudar etapa por inferência e sem enviar fora `prospeccao` canônica.
7. Maps: motor validado em 17/10/2026 via SSM no host Docker existente ARM64 (comandos pelo `terminal`). Evidências e modelos: /a0/usr/workdir/playbook_rotinas_20261017/maps_real_20261017_2128/ (host_job.sh, enrich.py, STATUS.json). Na busca existente, se faltar estoque e houver tempo, fazer no máximo uma coleta pequena por dia, duas consultas, depth 1, concorrência 1, 1 CPU, 1536 MB, timeout 240 s, imagem fixada já cacheada; diretório e nome de job novos, sem sobrescrever saídas. Usar operador SSM existente e limites/limpeza do modelo; não executar o script de teste com paths fixos novamente. Não provisionar, iniciar daemon, usar privileged ou proxy; se acesso faltar, usar CSV real disponível ou registrar falha sem bloquear outras fontes. Mapear website do CSV original corretamente para web_site do adaptador. Enriquecer até cinco sites públicos oficiais, validar DNS/IP público e redirects, parar captcha/429/bloqueio. Exigir origem Maps, cidade, evidência de produção própria de comida e Instagram linkado no site com proveniência; incerteza e texto genérico de plataforma (ex.: franquia no rodapé) vão para revisão, nunca exclusão automática comprovada. Dedupe contra snapshot somente leitura atualizado. Não guardar telefone/e-mail desnecessário. Verificar saída e ausência de containers/processos do job; candidatos não são leads confirmados.
8. Gerar JSON novo e sidecar de proveniência; deduplicar handle, Maps URL e nome/cidade frente ao estoque conhecido. Dados sintéticos nunca entram na fila. Importação REAL somente `prospeccao` importar_lista com arquivo novo em /a0/usr/prospeccao/; depois fontes/conferência/avaliação canônicas. Entrada é candidato, não encaixe validado, aquecimento nem autorização de envio.
9. Segundo Cérebro: verificar adaptador local de leitura contra fontes canônicas fixas de Matheus e presença da decisão #34/fio repositório sem mostrar conteúdo privado. Decisões e fios canônicos entram; CSV, relatório e observações não viram memória automaticamente. Não inferir vínculos nem criar segunda memória. Frontend permanece local.

## Como verificar que deu certo
Conferir saídas de testes em local/, proveniência e dedupe do adaptador; prova Node de loadSecondBrain contra /a0/usr sem escrita (pelo `terminal`); rotinas agendadas (`cronjob_manage`) permanecem intactas e atualização depende do parent. Não declarar ativo o que depende de bloco ainda não adicionado à tarefa.

## O que entregar
Resumo feito/testado/bloqueado; relatório IMPLEMENTACAO.md e blocos exatos com UUIDs para o parent atualizar as rotinas agendadas sem criar tarefas.

## Precisa de aprovação do usuário
Melhorias locais autorizadas pela decisão #34. Gmail/Agenda só leitura. Nenhum envio a terceiros fora fluxo `prospeccao`, nenhuma aceitação de termos, gasto novo, commit/push/deploy AWS, ERP ou exclusão; cotas/revisor da `prospeccao` sempre obrigatórios.

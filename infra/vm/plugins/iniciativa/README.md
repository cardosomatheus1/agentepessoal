# iniciativa

O agente que "mostra serviço": sem gatilho, ele olha o que está acontecendo e, quando pensa em algo que vale a
interrupção, manda uma mensagem — de preferência já com o trabalho adiantado.

- **Rodada "💡 Iniciativa"** (tarefa agendada, de 2 em 2 h das 9:37 às 19:37, America/Bahia): lê o contexto
  (`iniciativa contexto` = fios soltos + conversas + tarefas + memória das últimas 48 h, mais o histórico de
  iniciativas e reações), pensa em **uma** coisa de alto valor — adiantar um trabalho (pesquisa, rascunho num Doc
  da pasta "Agente"), uma ideia para um projeto, uma novidade externa que afeta algo em andamento, um padrão que
  vira rotina, uma conexão entre assuntos — faz a parte segura antes e manda com `iniciativa enviar`. Se nada valer
  a pena, `SEM NOVIDADE`.
- **Limites**: até 3 por dia, com 100 min entre elas; não repete assunto de 3 dias; respeita o horário de silêncio
  (vai como progresso). Nada que envie, pague, apague ou mude algo fora daqui sem aprovação.
- **Aprendizado**: botões "✅ Bora" (o agente continua/executa na conversa do Telegram), "👍 Útil" e "👎 Não
  precisa"; o placar por tipo e os `aprendizados` (o que a pessoa disse que quer ou não) entram na próxima rodada.

- **Revisor** (GPT-6.1 Sol, olhos novos): antes de sair, confere fatos contra o panorama e o arquivo, novidade, valor,
  preferências e forma; envia, ajusta o texto ou descarta (o motivo volta para a próxima rodada). Se cair, a mensagem
  vai como está (só chega ao dono).

Registro: `/a0/usr/iniciativa/<login>.json`. Os botões chegam por `plugins/whatsapp/api/receber.py` (`ini:`).

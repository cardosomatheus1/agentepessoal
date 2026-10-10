# fios_soltos

A "inteligência do Dots": perceber o que ficou esquecido e ligar informações que estão em lugares
diferentes.

- **Registro** (`/a0/usr/fios/<login>.json`): cada fio tem título, dono (você/agente), prazo, prioridade,
  próximo passo e **ligações** (com o que se conecta). Resolvidos ficam 14 dias para não voltarem.
- **Panorama** (`helpers/fios.py → coletar`): junta as últimas 72 h de conversas (pedidos, última resposta,
  avisos `notify_user`, pendências do `contexto.md`), tarefas agendadas (último resultado), objetivos,
  aprovações e a memória da pessoa — para o modelo cruzar.
- **Em toda conversa** (`system_prompt/_26_fios_soltos.py`): os fios em aberto e um índice das outras
  conversas recentes entram no prompt; o agente diz "Isso se liga com …" quando há relação, lembra no fim
  o que é importante e mantém o registro com a ferramenta `fios`.
- **Rodada "🧵 Fios soltos"** (tarefa agendada, 09:10, 13:10 e 18:10 America/Bahia): coleta o panorama, olha
  e-mail e agenda pelo conector `google`, atualiza o registro e manda ao celular só o que é novo ou piorou
  (até 3 itens, com a ligação e o que o agente pode fazer). Sem novidade, `SEM NOVIDADE` (não envia).

Só leitura fora do próprio registro: nunca envia, responde, paga, apaga ou altera nada.

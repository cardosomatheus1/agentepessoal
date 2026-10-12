# Central: livro de ações e conferência (revisão de 12/10, §4.1)

- **Livro** (`helpers/livro.py`): `/a0/usr/central/agente.db` (SQLite, WAL). A tabela `acao` só acrescenta (gatilhos
  recusam alterar e apagar). Cada linha é uma fase de uma ação: `executada`, `falhou`, `cancelada`…, com quem, onde
  (`alvo`, ex.: `instagram:@zen.marmitas`), hash e prévia do texto e a chave da ação (`prosp:<id>`). Gravar nunca
  levanta erro: o livro não pode parar o trabalho que registra. Logins `teste_*` não entram.
- **Quem grava hoje**: a prospecção (`resultado`, `comentado`, `marcar_apagada`).
- **Conferência** (`extensions/python/job_loop/_45_conferencia.py`): a cada 30 min, sem modelo, procura a mesma
  mensagem para a mesma pessoa executada 2× em 24 h e avisa uma vez por achado (tabela `alerta`).
- **Ferramenta `livro`**: "o que você fez hoje?" respondido pelo registro, não pela memória.
- **Backup**: `backup.sh` manda ao S3 uma cópia consistente (`agente.copia.db`), nunca o banco vivo no meio de uma
  gravação; o snapshot diário do disco também guarda.

Próximos passos do plano: gancho das aprovações (mensagens fora da prospecção), conferência na tela 3×/dia, "Feito
hoje" e `/livro` gerados daqui.

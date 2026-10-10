# estilo_claude

A conversa do Agent Zero passa a se ler como Claude/ChatGPT, sem alterar o núcleo:

- **Trabalhando:** enquanto o agente roda, aparece no fim da conversa uma marca girando com o que ele está
  fazendo e há quanto tempo (`✻ Pesquisando preços… · 1m 05s`). Some quando ele termina ou é pausado.
- **Etapas:** o cabeçalho de cada bloco de etapas já concluído vira uma linha discreta
  (`Etapas (7) · 1m 01s`), sem os selos (END, UTL) e contadores; clicar continua abrindo os detalhes.
- **Manutenção da memória:** os blocos só de utilidade ("Processing…", "memorizing…") ficam escondidos.

Lista de conversas: a ordem "mais recentes em cima" e a lista sem pastas de projeto são opções do
plugin nativo `_sidebar_folders` (`folder_view: false`, `sort_by: recent`), gravadas na configuração dele.

Código: `extensions/webui/initFw_end/estilo-claude.js`.

`extensions/python/hist_add_before/_05_ultima_atividade.py` corrige a hora da última atividade da
conversa: o Agent Zero gravava `last_message` no agente e não no contexto que a barra lateral lê, então
a ordem "recentes" ficava igual à de criação.

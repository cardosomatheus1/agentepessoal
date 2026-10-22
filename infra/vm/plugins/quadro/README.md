# quadro (Tarefas)

Quadro de tarefas (22/10, do Claude Duet: abas Active / Up next / Scheduled / Resolved, "só você marca como concluída",
cada tarefa com o seu sub-chat). Menu lateral → **Tarefas**.

| Coluna | O que mostra |
|---|---|
| Ativas | fios soltos em aberto (de quem é, prazo, próximo passo) e objetivos (/goal) em andamento |
| A conferir | o que o agente diz que terminou, com a nota do que fez: **só você fecha** |
| Próximas | o que foi adiado, com a data em que volta |
| Resolvidas | fechadas nos últimos 14 dias (dá para reabrir) |
| Agendadas | rotinas que rodam sozinhas: quando, última vez (só leitura) |

Botões: **▶ Faz pra mim** abre uma conversa só daquela tarefa ("Tarefa: …", com aviso no celular quando termina);
**✅ Concluir** fecha (só pelo quadro ou pela sua fala); **↩ Reabrir**.

A fonte é o registro de fios (`plugins/fios_soltos`), que continua sendo o único que escreve; o quadro só lê e chama
`concluir`, `reabrir` e `mesclar` (a conversa ligada à tarefa). A ferramenta `fios` do agente, ao terminar algo, manda o
fio para "a conferir" (`para_conferir`); só fecha direto quando você disse ("pode fechar"), com a sua fala em `pedido_dele`.

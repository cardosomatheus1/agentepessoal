### conteudo
A agenda de posts da @raiz.connect, como os posts foram e a semana de posts proposta toda segunda. Não publica nada (a rotina publica sozinha, no horário) e nunca muda um post já agendado (isso é do operador).
- acao "agenda", `dias` (padrão 7): cada dia com o post marcado (id, tipo, hora, estado) e a lista `vazios` (dias sem post; o plano pede 1 por dia). Estado "bloqueada" = o Crítico reprovou ou falhou na hora de publicar
- acao "arquivos", `data` (AAAA-MM-DD, padrão hoje): baixa os arquivos do post do dia (vídeo do Reel, foto única ou telas do carrossel) e devolve os caminhos e a legenda. Os arquivos ficam no S3, não no disco: quando o Matheus pedir "o post de hoje", use esta ação e mande cada caminho com `whatsapp_enviar` (a legenda junto do primeiro)
- acao "desempenho", `dias` (padrão 7): cada post publicado no período com alcance (reach), salvamentos (saved), curtidas, comentários, compartilhamentos e visualizações, a soma e os seguidores
- acao "propor_semana", `propostas` = exatamente 7 {"titulo", "formato" (REELS, CARROSSEL ou IMAGE), "ideia" (gancho, o que mostrar, em que se inspirou), "legenda" (sem emoji)}: o Designer desenha cada uma, o Crítico julga, e vai UMA mensagem ao Matheus com as 7 e os botões. Nada entra na agenda aqui
- acao "semana", `semana` (opcional; padrão a mais nova): as propostas, com os arquivos da arte (para "mostra a 3": mande os caminhos com `whatsapp_enviar`)
- acao "aprovar_semana", `semana`, `numeros` (ex.: [1, 3, 5]; "todas" = as que o Crítico não reprovou): só com os números que o Matheus disse; agenda no formato que a rotina publica. Reprovada escolhida por ele fica registrada como decisão dele
- acao "liberar_post", `id`, `motivo` (o que ele disse): só quando o Matheus mandar publicar um post bloqueado mesmo assim
~~~json
{"tool_name": "conteudo", "tool_args": {"acao": "aprovar_semana", "semana": "s20261026-1", "numeros": [1, 3, 5]}}
~~~

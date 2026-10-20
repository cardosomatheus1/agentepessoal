### conteudo
Só leitura: a agenda de posts da @raiz.connect e como os posts foram. Não agenda, não muda e não publica nada (isso é do operador).
- acao "agenda", `dias` (padrão 7): cada dia com o post marcado (id, tipo, hora, estado) e a lista `vazios` (dias sem post; o plano pede 1 por dia)
- acao "arquivos", `data` (AAAA-MM-DD, padrão hoje): baixa os arquivos do post do dia (vídeo do Reel, foto única ou telas do carrossel) e devolve os caminhos e a legenda. Os arquivos ficam no S3, não no disco: quando o Matheus pedir "o post de hoje", use esta ação e mande cada caminho com `whatsapp_enviar` (a legenda junto do primeiro)
- acao "desempenho", `dias` (padrão 7): cada post publicado no período com alcance (reach), salvamentos (saved), curtidas, comentários, compartilhamentos e visualizações, a soma e os seguidores
~~~json
{"tool_name": "conteudo", "tool_args": {"acao": "desempenho", "dias": 7}}
~~~

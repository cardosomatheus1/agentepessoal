### monitor
Guarda um monitor de evento para o Radar conferir em cada rodada (5 por dia): "me avise quando chegar e-mail do contador", "se mudar a reunião de sexta", "quando aparecer fatura da Vivo".
- `acao`: "criar" | "listar" | "remover"
- `fonte`: "gmail" ou "agenda"
- `condicao`: o que procurar, bem concreto (remetente, assunto, palavra, evento)
- `o_que_fazer`: o que fazer quando achar (padrão: avisar com resumo; nunca envia nem altera nada sozinho)
- `id`: para remover
~~~json
{"tool_name": "monitor", "tool_args": {"acao": "criar", "fonte": "gmail", "condicao": "e-mail de contador@escritorio.com.br", "o_que_fazer": "me avisar na hora com um resumo"}}
~~~

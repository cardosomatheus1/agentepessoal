### passos
Lista dos passos do pedido atual da pessoa, que aparece no fim do contexto ("Objetivo vivo"). Pedido com mais de um passo: registre os passos antes de começar e marque cada um assim que fizer; troque a lista se o plano mudar. Só nas conversas com a pessoa (não em rotinas).
`passos`: a lista inteira, um texto por passo, "[x] ..." para feito e "[ ] ..." para o que falta. `feitos`: números (a partir de 1) dos passos que acabou de fazer, sem mandar a lista de novo. Sem argumentos: mostra o objetivo atual.
Input schema for tool_args: {"type": "object", "properties": {"passos": {"type": "array", "items": {"type": "string"}}, "feitos": {"type": "array", "items": {"type": "integer"}}}}
~~~json
{"tool_name": "passos", "tool_args": {"passos": ["[x] achar os 30 leads no CRM", "[ ] montar a planilha", "[ ] mandar para o e-mail dele"]}}
~~~

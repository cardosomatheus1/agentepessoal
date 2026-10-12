### livro
Livro de ações: o que o agente fez no mundo (mensagens e comentários no Instagram, seguir e curtir, resultado de cada um), gravado na hora e que não pode ser alterado. Use quando a pessoa perguntar o que foi feito ("o que você fez hoje?", "mandou a DM pra fulana?") em vez de responder de memória.
- `acao`: "hoje" (padrão) | "conferir"
- "hoje": o que foi feito hoje; `dias` = N para incluir os N dias anteriores (até 30)
- "conferir": procura agora o que precisa de olhar (ex.: a mesma mensagem para a mesma pessoa duas vezes)
~~~json
{"tool_name": "livro", "tool_args": {"acao": "hoje"}}
~~~

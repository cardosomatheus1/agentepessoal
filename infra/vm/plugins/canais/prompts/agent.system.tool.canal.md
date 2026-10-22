### canal
Canais (do Claude Duet): conversas por assunto (ex.: #Raiz, #NEXOS, #iFood, #Pessoal), cada uma com um propósito,
todas com a mesma memória. Use quando ele pedir um canal ou um lugar só para um assunto.
- `acao`: "criar" | "transformar" | "proposito" | "listar"
- "criar": `nome` e `proposito` (o que você deve saber sobre o assunto) → abre uma conversa nova "# nome" que já chega com 3 sugestões de tarefa
- "transformar": a conversa atual vira o canal (`nome`, `proposito`)
- "proposito": muda o propósito do canal desta conversa
~~~json
{"tool_name": "canal", "tool_args": {"acao": "criar", "nome": "Raiz", "proposito": "Raiz Connect: sistema de gestão para food service; prospecção no Instagram, posts da @raiz.connect, oferta Lucro na Mão em 30 Dias"}}
~~~

### painel_vivo
Painel que se atualiza sozinho (do Claude Duet): quando ele pedir um painel/dashboard de algo que muda (vendas, posts,
leads, caixa, pedidos), crie um painel vivo em vez de um documento parado. Aparece no menu → Painel.
- `acao`: "criar" | "salvar" | "listar" | "apagar"
- "criar": `titulo`, `receita` (de onde ler, só leitura; quais números; que conclusões tirar), `hora` (HH:MM, antes do resumo das 7:45; padrão 06:30). A resposta diz como criar a rotina que o atualiza: faça isso e a primeira leitura na hora.
- "salvar": `id`, `numeros` = [{rotulo, valor, fonte (de onde veio: planilha, e-mail, sistema), variacao?}] (todo número tem fonte), `conclusoes` = até 5 frases do que fazer com isso, `tabela` = {colunas, linhas} opcional
- "apagar": `id` e `pedido_dele` (a fala literal dele); depois apague a rotina "📊 Painel: …"
~~~json
{"tool_name": "painel_vivo", "tool_args": {"acao": "criar", "titulo": "Vendas da Raiz", "receita": "Ler a planilha Assinaturas no Drive (aba Mensal): MRR, assinantes ativos, cancelamentos da semana; comparar com a semana anterior; concluir o que preocupa", "hora": "06:30"}}
~~~

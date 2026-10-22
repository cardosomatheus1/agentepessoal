### fios
Registro dos "fios soltos" da pessoa: o que ficou em aberto (pedido não concluído, promessa sua, tarefa travada, prazo, algo que depende dela) e as ligações entre assuntos.
- `acao`: "listar" | "coletar" | "salvar" | "resolver" | "adiar"
- "coletar": panorama das últimas `horas` (padrão 72) — conversas, tarefas agendadas, avisos, objetivos, aprovações, memória e o registro atual. Use para cruzar informações.
- "salvar": `fios` = lista de objetos {id (para atualizar um existente), titulo, detalhe, fontes (conversas/e-mails), dono ("você" ou "agente"), prazo (AAAA-MM-DD), prioridade (alta|media|baixa), proximo_passo, ligacoes (com o que se conecta), area (raiz | nexos | orbyte | agente | pessoal | geral: a frente da vida dele a que o fio pertence)}; `resolvidos` = ids que já se resolveram
- "resolver": `resolvidos` (ou `id`), e `nota` (o que você fez, 1 linha) — quando VOCÊ concluiu: o fio vai para "a conferir" e só ele fecha (quadro de Tarefas). Se foi ELE quem disse que está resolvido ("pode fechar", "já resolvi"), mande `pedido_dele` com a fala literal dele e o fio fecha
- "adiar": `id` e `ate` (AAAA-MM-DD) — quando a pessoa pedir para lembrar depois
- "avisar": `id` (um ou lista) — manda cada fio ao celular da pessoa como mensagem própria com botões "✅ Faz pra mim", "⏰ Amanhã" e "🙈 Ignorar"; `urgente: true` (só prioridade alta que vence hoje/amanhã ou trava outro trabalho) chega mesmo no horário de silêncio
~~~json
{"tool_name": "fios", "tool_args": {"acao": "salvar", "fios": [{"titulo": "Checar a análise da fase 2 do app Nexos na Meta", "dono": "você", "prioridade": "alta", "proximo_passo": "abrir developers.facebook.com no seu celular", "ligacoes": "conta do Facebook restrita em 09/10", "area": "nexos"}]}}
~~~

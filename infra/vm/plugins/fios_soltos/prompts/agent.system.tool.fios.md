### fios
Registro dos "fios soltos" da pessoa: o que ficou em aberto (pedido não concluído, promessa sua, tarefa travada, prazo, algo que depende dela) e as ligações entre assuntos.
- `acao`: "listar" | "coletar" | "salvar" | "resolver" | "adiar"
- "coletar": panorama das últimas `horas` (padrão 72) — conversas, tarefas agendadas, avisos, objetivos, aprovações, memória e o registro atual. Use para cruzar informações.
- "salvar": `fios` = lista de objetos {id (para atualizar um existente), titulo, detalhe, fontes (conversas/e-mails), dono ("você" ou "agente"), prazo (AAAA-MM-DD), prioridade (alta|media|baixa), proximo_passo, ligacoes (com o que se conecta)}; `resolvidos` = ids que já se resolveram
- "resolver": `resolvidos` (ou `id`) — quando algo foi concluído
- "adiar": `id` e `ate` (AAAA-MM-DD) — quando a pessoa pedir para lembrar depois
~~~json
{"tool_name": "fios", "tool_args": {"acao": "salvar", "fios": [{"titulo": "Checar a análise da fase 2 do app Nexos na Meta", "dono": "você", "prioridade": "alta", "proximo_passo": "abrir developers.facebook.com no seu celular", "ligacoes": "conta do Facebook restrita em 09/10"}]}}
~~~

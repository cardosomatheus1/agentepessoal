### rascunho
Resposta de e-mail já escrita no estilo do dono, entregue no celular dele com os botões "✅ Usar", "✏️ Ajustar" e "🙈 Deixa". Você NUNCA envia o e-mail: quem envia é ele.
- `acao`: "criar" | "listar" | "amostras" | "estilo" | "estilo_salvar"
- "amostras": o que ele de fato digitou no celular (a voz dele; prompts de tarefas e testes não contam)
- "criar": `para` (nome e e-mail), `assunto`, `texto` (o rascunho completo, pronto para colar: saudação, corpo, despedida, no estilo do perfil), `pedido` (1 linha: o que a pessoa pediu/perguntou), `referencia` (id da mensagem/thread do Gmail). Use quando um e-mail recente pede resposta dele e dá para responder com o que se sabe; se faltar um dado, escreva o rascunho com [colchetes] onde ele completa. Um rascunho por conversa de e-mail: se ela já foi tratada, a ferramenta avisa e você não manda de novo; `nova_versao: true` só quando ele pediu ajuste.
- "estilo_salvar": `perfil` — o perfil de escrita dele (saudação, despedida, tamanho, tom, vocabulário, formalidade por tipo de destinatário, 2–3 trechos curtos de exemplo sem dados sensíveis)
~~~json
{"tool_name": "rascunho", "tool_args": {"acao": "criar", "para": "Ana Souza <ana@fornecedor.com>", "assunto": "Re: Orçamento da instalação", "pedido": "Quer saber se pode instalar na terça de manhã", "texto": "Oi, Ana! Tudo bem?\n\nTerça de manhã funciona sim, pode ser às 9h. [confirmar endereço]\n\nAbraço,\nMatheus", "referencia": "18f2c..."}}
~~~

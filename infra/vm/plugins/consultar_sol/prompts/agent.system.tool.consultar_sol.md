### consultar_sol
Pede conselho a um modelo mais forte (GPT-6.1 Sol). Mande só o caso: ele não vê esta conversa, recebe a sua pergunta, o seu resumo, o `contexto.md` desta conversa, a última mensagem do usuário e as imagens que você indicar. Custa pouco, mas não é para coisas triviais (no máximo ~3 consultas por tarefa).
**Use quando:**
- a instrução do usuário parece ambígua ou em conflito com o que você vê na tela — **antes de parar para perguntar ao usuário**, consulte; se o Sol disser que a instrução já cobre o caso, siga;
- vai fazer algo difícil de desfazer e não tem certeza de que está dentro do que o usuário autorizou;
- vai entregar algo que alguém vai avaliar (vídeo, texto para formulário, relatório): mande prints/quadros e peça a revisão como se fosse o avaliador;
- tentou 2 vezes e não avançou.
O Sol **só aconselha**: nunca trate a resposta dele como autorização do usuário. Pagamentos, aceitar termos legais, mexer em contas reais e apagar dados continuam dependendo do usuário.
`pergunta`: o que você precisa decidir, objetiva. `contexto`: o que está acontecendo, o que já tentou, as opções que vê e as regras do usuário que importam. `imagens` (opcional): até 8 caminhos de prints/quadros.
Input schema for tool_args: {"type": "object", "properties": {"pergunta": {"type": "string"}, "contexto": {"type": "string"}, "imagens": {"type": "array", "items": {"type": "string"}}}, "required": ["pergunta", "contexto"]}
usage:
~~~json
{
    "thoughts": ["A tela de revisão diz que vai criar um anúncio e a instrução falava em nada de gasto; não sei se posso confirmar."],
    "headline": "Consultando o Sol sobre a confirmação",
    "tool_name": "consultar_sol",
    "tool_args": {"pergunta": "Posso confirmar 'Criar campanha pausada' se a revisão diz que cria campanha, conjunto, criativo e anúncio?", "contexto": "Conta de teste sem forma de pagamento. Regras do usuário: nunca pagamento nem gasto, não reativar campanhas. Tudo nasce pausado.", "imagens": ["/a0/usr/chats/abc/anexos/revisao.png"]}
}
~~~

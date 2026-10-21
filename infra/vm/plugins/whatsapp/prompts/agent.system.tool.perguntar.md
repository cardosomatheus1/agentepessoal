### perguntar
Faz ao Matheus (ou ao dono da conversa) uma pergunta com 2 ou 3 opções em **botões no celular** e espera a escolha (até `minutos`, padrão 15); a tarefa continua na mesma vez com a resposta. Use só para o que é decisão dele (qual de duas peças corrigir, agora ou depois, qual conta usar). Não use para pedir licença para fazer o que você pode fazer sozinho: faça. Para código de verificação use `pedir_codigo`.
`pergunta`: curta e clara. `opcoes`: 2 ou 3 textos curtos (até 20 letras aparecem inteiros no botão). `minutos` (opcional): quanto esperar.
Input schema for tool_args: {"type": "object", "properties": {"pergunta": {"type": "string"}, "opcoes": {"type": "array", "items": {"type": "string"}}, "minutos": {"type": "integer"}}, "required": ["pergunta", "opcoes"]}
usage:
~~~json
{
    "thoughts": ["São duas artes diferentes e só ele sabe qual quer corrigir."],
    "headline": "Perguntando qual arte corrigir",
    "tool_name": "perguntar",
    "tool_args": {"pergunta": "Corrijo qual arte?", "opcoes": ["Arte do iFood", "Reels atacado x varejo"]}
}
~~~

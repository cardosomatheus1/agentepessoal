### criar_gatilho
Cria, lista ou apaga **gatilhos** do usuário: um endereço secreto que qualquer serviço chama (POST) quando algo acontece — formulário, loja, NEXOS, encaminhamento de e-mail, Zapier/Make. A cada chamada a VM acorda se precisar e o conteúdo chega na conversa "Gatilhos" com a instrução salva; o resultado vai para o WhatsApp do usuário.
Use quando o usuário pedir "quando acontecer X, faça Y". Depois de criar, diga onde configurar o endereço no serviço de origem.
`acao`: criar | listar | apagar. `nome`: curto, sem espaços (ex.: novo-lead). `instrucao`: o que fazer ao disparar (só para criar).
Input schema for tool_args: {"type": "object", "properties": {"acao": {"type": "string", "enum": ["criar", "listar", "apagar"]}, "nome": {"type": "string"}, "instrucao": {"type": "string"}}}
usage:
~~~json
{
    "thoughts": ["Ele quer saber na hora quando chegar lead novo no NEXOS."],
    "headline": "Criando o gatilho de lead novo",
    "tool_name": "criar_gatilho",
    "tool_args": {"acao": "criar", "nome": "novo-lead", "instrucao": "Resuma o lead (nome, empresa, interesse) e me avise no WhatsApp. Não responda ao lead."}
}
~~~

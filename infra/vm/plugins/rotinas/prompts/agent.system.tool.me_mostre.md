### me_mostre
Grava o **usuário fazendo uma tarefa uma vez** no Navegador desta conversa, para você transformar em rotina. `acao: "iniciar"` começa (telas a cada mudança, até 20 min); quando ele disser que terminou, `acao: "parar"` devolve a linha do tempo e as imagens. Depois: `analisar_imagens` na pasta, descreva os passos e as decisões, pergunte só o que ficou ambíguo, e `salvar_rotina`.
Use quando o usuário disser "vou te mostrar", "aprende comigo", "me observa fazendo".
Input schema for tool_args: {"type": "object", "properties": {"acao": {"type": "string", "enum": ["iniciar", "parar"]}}, "required": ["acao"]}
usage:
~~~json
{
    "thoughts": ["Ele vai me mostrar como emite a nota; vou gravar."],
    "headline": "Gravando a demonstração",
    "tool_name": "me_mostre",
    "tool_args": {"acao": "iniciar"}
}
~~~

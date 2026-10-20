### ferramentas_extras
Ferramentas que não estão na sua lista para ela ficar curta: conectores (Gmail, Agenda, Drive, Docs, Planilhas, GitHub) e ferramentas usadas de vez em quando. A lista delas, com os argumentos obrigatórios, vem na descrição desta ferramenta.
- `acao: "buscar"`, `texto`: o que você precisa ou o nome. Mostra a descrição inteira e os parâmetros das que combinam.
- `acao: "usar"`, `nome`, `args` (objeto com os argumentos da ferramenta): roda a ferramenta, com as mesmas regras e conferências de uma chamada direta.
Se já sabe o nome e os argumentos, vá direto em `usar`; na dúvida sobre os parâmetros, `buscar` antes. Quando uma instrução, rotina ou skill mandar usar uma ferramenta que não está na sua lista, ela está aqui.
Input schema for tool_args: {"type": "object", "properties": {"acao": {"type": "string", "enum": ["buscar", "usar"]}, "texto": {"type": "string"}, "nome": {"type": "string"}, "args": {"type": "object"}}, "required": ["acao"]}
usage:
~~~json
{
    "thoughts": ["Preciso dos eventos de amanhã; a agenda é uma ferramenta extra."],
    "headline": "Lendo a agenda",
    "tool_name": "ferramentas_extras",
    "tool_args": {"acao": "usar", "nome": "google_get_events", "args": {"time_min": "2026-10-22T00:00:00-03:00", "time_max": "2026-10-23T00:00:00-03:00"}}
}
~~~

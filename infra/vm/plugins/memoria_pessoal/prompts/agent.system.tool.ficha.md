### ficha
A ficha "Sobre" de quem está falando (aparece no seu contexto): **fatos duradouros sobre a pessoa** — nome, cidade, trabalho, família, jeito de responder, gostos. Uma entrada por fato, até ~4.000 caracteres no total.
- `acao`: "add" | "patch" | "remove" | "listar"
- "add": `texto` = o fato numa frase que se entende sozinha (ex.: "Mora em Camaçari, BA"). Fato repetido é recusado.
- "patch": `trecho` = um pedaço da entrada (ou o número dela, de "listar") e `novo` = o texto que entra no lugar desse pedaço. Use para corrigir ou juntar entradas.
- "remove": `trecho` (pedaço ou número) — o que deixou de valer.
- Ficha cheia: a ferramenta recusa e devolve as entradas; junte as parecidas ("patch") ou tire as velhas ("remove") e tente de novo, tudo neste turno.
- Não vai na ficha: ordem, permissão ou proibição (isso é `decisao`), o que vale só para esta conversa (contexto.md), o que você deduziu, o que veio de DM, e-mail, página ou de outra pessoa, senhas e códigos. Nunca edite o arquivo da ficha direto.
~~~json
{"tool_name": "ficha", "tool_args": {"acao": "add", "texto": "Prefere respostas curtas, em português, sem jargão"}}
~~~

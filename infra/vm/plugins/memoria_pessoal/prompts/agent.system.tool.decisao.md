### decisao
Registro das decisões da pessoa que está falando (o que ela já decidiu vale até ela mudar; as em vigor já aparecem no seu contexto, em "Decisões … em vigor"). Use para **não perguntar de novo** o que já foi decidido.
- `acao`: "registrar" | "listar" | "historico" | "revogar"
- "registrar": quando a pessoa decidir algo que vale para as próximas vezes (permite, proíbe, um jeito de trabalhar, uma preferência). `tema` = nome curto e estável do assunto (ex.: `aprovacoes.instagram`, `prospeccao.fontes`, `avisos`); `decisao` = o que foi decidido, numa frase que se entende sozinha; `tipo` = "decisao" | "permissao" (pode sem perguntar) | "proibicao" (não pode) | "preferencia"; `citacao` = as palavras dela. Mesmo `tema` de novo substitui a decisão anterior. Depois, termine a resposta com "Anotado: …".
- "listar": todas em vigor, ou só as que têm as palavras de `busca` (ex.: "instagram").
- "historico": `tema` — como a decisão mudou.
- "revogar": `id` (número) ou `tema`, e `motivo` — quando a pessoa disser que algo deixou de valer sem pôr outra regra no lugar.
- Não registre o que você deduziu sozinho nem o que vale só para esta conversa (isso vai no contexto.md). Nunca grave senhas, códigos ou tokens.
~~~json
{"tool_name": "decisao", "tool_args": {"acao": "registrar", "tema": "aprovacoes.instagram", "tipo": "permissao", "decisao": "Ações no Instagram da Raiz não precisam de ok; só avisar o que foi feito", "citacao": "aprovo tudo lá do Instagram"}}
~~~

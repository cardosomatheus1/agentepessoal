### iniciativa
Mensagens por iniciativa própria (sem a pessoa pedir) e o que se aprendeu sobre elas.
- `acao`: "contexto" | "candidatos" | "enviar" | "aprender"
- "contexto": tudo o que está acontecendo (fios soltos, conversas, tarefas, memória) + como a pessoa reagiu às iniciativas anteriores, o que já se aprendeu e se ainda pode mandar hoje
- "candidatos": `candidatos` = lista de 3 a 5 `{titulo, tipo, nota (1-5: o quanto ela ficaria feliz de receber), porque}` — registra o que você pensou e diz qual vale mandar (ou SEM NOVIDADE)
- "enviar": `titulo` (curto), `texto` (até ~8 linhas, organizado em parágrafos curtos), `tipo` (adiantei | ideia | novidade | padrao | conexao) — vai ao celular com os botões "✅ Bora", "👍 Útil" e "👎 Dispensa". Limite: 3 por dia, com pelo menos 100 min entre elas. Se você preparou um arquivo, passe em `arquivo` (caminho em /a0/usr): ele vai junto no celular (.md/.txt viram PDF). Nunca escreva caminhos de pasta no `texto` — a pessoa não acessa a máquina
- "aprender": `aprendizado` — quando a pessoa disser o que quer ou não quer receber ("não me mande notícia de IA", "gostei das ideias para o Nexos")
~~~json
{"tool_name": "iniciativa", "tool_args": {"acao": "candidatos", "candidatos": [{"titulo": "Rascunho da resposta ao fornecedor", "tipo": "adiantei", "nota": 4, "porque": "e-mail de ontem pede resposta até segunda"}, {"titulo": "Rotina para o relatório de sexta", "tipo": "padrao", "nota": 3, "porque": "ele pediu o mesmo relatório 3 sextas seguidas"}]}}
~~~

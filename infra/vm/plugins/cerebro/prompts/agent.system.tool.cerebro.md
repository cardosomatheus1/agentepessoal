### cerebro
O Segundo Cérebro do Matheus (a Pasta). Decisões e pendências continuam com `decisao` e `fios`; esta ferramenta faz o resto.
- `acao: consultar`, `texto`: busca em toda a Pasta (decisões, pendências, assuntos, contexto, reuniões, notas do dia) e devolve as notas. Use para responder "o que eu decidi…", "onde parou…", "quem é…"; o que não vier, não está registrado.
- `acao: assunto`: abrir (`titulo`, `onde_parou`, `area`) ou mover um assunto (`ref` = id, `onde_parou`, `estado` andamento|parado|encerrado). `acao: assuntos` lista os abertos.
- `acao: desfazer`, `ref` ("ultimo" = a última anotação automática, ou "decisao:35", "pendencia:ab12cd", "assunto:x1y2z3"), `motivo`: quando ele disser que a anotação estava errada. Nada se apaga: vai para o arquivo morto.
- `acao: contexto`: sem `conteudo` mostra a próxima seção da entrevista (ou a `secao` pedida) e o que já existe; com `secao`, `conteudo` e `aprovado` (as palavras do ok dele) grava. Uma seção por vez, nunca sem o ok.
- `acao: nota_do_dia` escreve a nota de hoje agora; `acao: auditoria` roda a auditoria da Pasta e dá a nota.

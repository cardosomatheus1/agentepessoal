---
name: prospeccao-rascunho-primeiras-mensagens
description: "Escrever (sem enviar) a primeira mensagem de Direct da Raiz para uma lista de leads vinda de arquivo, seguindo o playbook da ferramenta prospeccao, os temas da semana e as decisões do Matheus, e gravar em JSON."
version: 1.0.1
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-23
tags: ["aprendizado"]
trigger_patterns:
  - "primeira mensagem"
  - "mensagens.json"
  - "leads.json"
  - "rascunho de direct"
  - "não envie"
  - "escreva a mensagem para os leads"
  - "playbook da prospecção"
  - "tema da mensagem"
---

# Rascunho de primeiras mensagens de Direct (sem enviar)

Vale quando o pedido traz uma lista de leads (ex.: `leads.json`) e manda escrever a 1ª mensagem de cada um, sem enviar, gravando um arquivo `[{handle, tema, texto}]`. Mecânica de envio real: instagram-direct-navegador. Regras de quando e a quem prospectar: prospeccao-instagram.

## Fluxo
1. **Pegue o playbook**: `prospeccao` com `acao: "playbook"`. Chamar `prospeccao` sem argumentos devolve a mesma resposta, então não chame as duas formas. `prospeccao` é ferramenta direta (uma das nossas), não é conector MCP: não precisa de `tool_search`.
2. **Leia o playbook inteiro**: a saída pode vir cortada. Abra o arquivo indicado (`.../saidas/NNNN-prospeccao.txt`) em blocos com `read_file` ou `terminal` com `sed -n 'A,Bp'`, ou procure com `search_files` / `terminal` com `grep -n` em "Primeira mensagem", "Tema", "Nexo", "Tom de voz". As regras que mais pesam estão nas seções 3 (tom) e 5 (modelos, tema, nexo).
3. **Decisões do Matheus**: `decisao acao: listar busca: "prospec"` (o filtro é `busca`). Se a saída truncar, use `grep -i` pelo `terminal`. O Segundo Cérebro ("Prospecção e geração de leads...") diz quais temas estão pausados ou em teste. Se o pedido diz "inclusive o que não está dando certo", o tema pausado (hoje: preço/calculadora) não pode aparecer, nem de passagem.
4. **Contexto zip**: não há `unzip` na máquina; extraia pelo `terminal` com `python -c "import zipfile; zipfile.ZipFile(src).extractall(dst)"` (ou direto no `execute_code`).
5. **Para cada lead**, parta só do que está escrito em `motivo`/`segmento`/`cidade`. Escolha o tema pelo gancho (nexo): iFood → pedidos entram sozinhos; encomenda/produção → lista de compras e baixa de insumos; congelado/validade → estoque; vários canais → tudo num lugar só. Escreva a mensagem:
   - 2 a 4 frases curtas, até 250 caracteres, português de celular, sem travessão, no máximo 1 emoji, sem jargão (ERP, gestão, solução).
   - Abra pelo detalhe do lead, citado pelo assunto. Evite "essa semana", "hoje", "ontem" e "último post", porque a mensagem sai horas depois.
   - Diga quem fala ("Sou/Aqui é o Matheus, da Raiz Connect") e o que a Raiz é numa frase de até 15 palavras, escrita diferente em cada mensagem.
   - Sem link, sem calculadora, sem oferta de preço ou "Lucro na Mão". Variante A = uma pergunta ligada ao tema; B = oferta leve mais "Te mando como funciona?".
   - "Sou daqui de Salvador também" só se o lead for de Salvador. Não cite a bio entre aspas. Não invente fato.
   - Varie saudação e estrutura entre as mensagens (nenhuma começa igual à outra).
6. **Grave e confira por código** (`execute_code`): escreva o JSON com `ensure_ascii=False`, leia de volta e valide limite de caracteres, ausência de "—", "http"/"raizconnect.com.br", palavras de tempo e inícios repetidos. Corrija e regrave antes de responder.
7. **Resposta curta**: o que fez, o tema escolhido por lead, o que decidiu sozinho e o caminho do arquivo. Diga que nada foi enviado.

## Armadilhas
- Não diga que variantes A/B foram sorteadas "como a ferramenta faria" se você as escolheu à mão. Relate o que fez de fato.
- Se os leads do arquivo não estão na fila da ferramenta, não há tema indicado: escolha pelo gancho e diga isso.
- Lead com `nota` nula ou `post_recente` nulo: use apenas o `motivo`, sem inventar post.
- Reescreva se passar de 250 caracteres; a ferramenta e o revisor recusam textos maiores.

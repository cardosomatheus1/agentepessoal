---
name: status-homologacao-integracoes-parceiros
description: "Responder \"quais os passos para homologar a integração X (99Food, iFood, Keeta) e o que já foi feito / falta\" a partir do Segundo Cérebro (contexto.zip) mais pesquisa pública, gravando um .md com passos, links oficiais e pendências."
version: 1.0.1
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-23
tags: ["aprendizado"]
trigger_patterns:
  - "homologar"
  - "homologação"
  - "99Food"
  - "integração 99Food"
  - "o que falta"
  - "o que já foi feito"
  - "passos para homologar"
  - "links oficiais"
---

# Status e passos de homologação de integrações com parceiros

Esta skill vale para pedidos do tipo "quais os passos para homologar a integração da Raiz com X e, pelo que o Matheus registrou, o que já foi feito e o que falta". É trabalho de leitura e redação: não entra no portal, não envia nada e não abre e-mail dele. Para mexer no portal, use formularios-portais-parceiros e login-sites-navegador. Para perguntas gerais sobre o Cérebro, use respostas-do-segundo-cerebro.

## Fluxo
1. **Extraia o zip com Python**, porque `unzip` pode não existir. Use `execute_code` com `zipfile.ZipFile(...).extractall('/tmp/ctx')`. Se já houver pasta `extraido/`, use-a.
2. **Ache o Assunto da integração.** Rode `ls segundo_cerebro/Assuntos | grep -i <parceiro>` no `terminal` (ex.: `...-integracao-99food-...`, `...-homologacao-do-ifood-...`). Leia o arquivo inteiro com `read_file`.
   - A linha `historico:` do frontmatter é uma lista numa linha só e NÃO é JSON válido. Não perca tempo com `json.loads`. Use a seção `## Histórico` do corpo, que vem em ordem cronológica, e o `onde_parou` do topo, que é o estado mais recente.
   - Se o arquivo for longo, leia o trecho do meio por partes com `read_file` ou com `grep -n`/`sed -n` no `terminal`.
3. **Siga as ligações** (`## Ligações`).
   - Leia as `Decisoes/` citadas: o que o Matheus autorizou ou vetou, por exemplo o que dispensa ok e o que continua exigindo.
   - Leia as `Pendencias/` abertas: NDA, resposta do parceiro, prazos.
   - Rode também `grep -ril '<parceiro>' segundo_cerebro/` no `terminal` (ou `search_files`) para pegar decisões e fios que não estão ligados.
4. **Pesquise o processo público** com `web_search`: portal do desenvolvedor do parceiro, etapas, sandbox, loja/app de teste, homologação, produção. Uma busca basta. Se precisar ler uma página oficial achada, use `web_extract`.
   - Se não achar documentação oficial legível, diga isso.
   - Não complete com guias de terceiros: a central de ajuda de outro software ensina a ativar loja, não a homologar parceiro.
5. **Monte o `.md` na pasta pedida** com `write_file`, com estas seções:
   - Passos para homologar. Separe o que é confirmado por fonte oficial do que é a sequência reconstruída pelo histórico do Matheus, e escreva essa distinção no próprio texto.
   - Já feito, com a data do registro e a decisão que sustenta cada item.
   - Falta, em ordem de dependência. Item sem confirmação no registro (ex.: NDA assinado, envio formal para homologação, deploy) vai como "não confirmado", nunca como feito nem como pendente certo.
   - Links oficiais, só os que você viu (portal, documentação), e o que não foi encontrado.
   - Decisões em vigor (número + 1 linha).
   - O que você decidiu sozinho.
6. **Confira o arquivo** com `ls -la` e `wc -l` no `terminal`. Responda curto: o que fez, o que decidiu sozinho e o caminho do arquivo.

## Armadilhas
- **Não copie segredos para o .md.** Isso inclui senha, apelido de segredo do cofre e e-mail com credencial que aparecem em pendências. Escreva "credencial no cofre" e nada mais, porque o arquivo circula fora do cofre.
- **O estado mais novo ganha.** O `onde_parou` e o último item do histórico mandam. Pendências antigas podem já estar resolvidas pelo que veio depois: por exemplo, acesso à API liberado implica que parte do caminho andou. Aponte a contradição em vez de escolher em silêncio.
- **Não invente passos oficiais.** Se a pesquisa não confirma uma etapa, rotule como "prática registrada", porque o Matheus pode repassar o arquivo a quem vai agir com base nele.
- **Cite números e datas só do registro**: testes que passaram, falhas, prazos. Se for usar a data de "hoje", converta para UTC-3.
- **Em pedidos "sem perguntar a ninguém", não bloqueie por dado faltante.** Registre a lacuna em "Falta" e liste a decisão em "O que decidi sozinho".

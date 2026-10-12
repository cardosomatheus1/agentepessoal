---
name: prospeccao-instagram
description: "Fluxo completo da prospecção da Raiz Connect pela conta @raiz.connect: achar leads (catálogo de CNPJ, listas, buscador e Instagram), dar nota, aquecer (seguir, curtir, comentar), mandar a primeira mensagem e o lembrete no Direct, ler e responder quem respondeu, com a ferramenta prospeccao. Vale para as rodadas agendadas e para pedidos avulsos do Matheus."
version: 3.0.0
tags: ["instagram", "prospecção", "prospeccao", "raiz connect", "leads", "direct", "dm", "comentário", "curtir", "seguir"]
trigger_patterns:
  - "prospec"
  - "instagram"
  - "raiz.connect"
  - "lead"
  - "direct"
  - "dm"
  - "marmitaria"
  - "confeitaria"
---

# Prospecção da Raiz Connect: fluxo completo

A ferramenta `prospeccao` decide **o quê**: limites, nota, sequência, revisor e aprovações. Esta skill ensina **o
como**. O playbook (`prospeccao` acao "playbook") tem o cliente ideal, o tom e os modelos de texto: leia-o inteiro
antes de escrever qualquer mensagem, porque ele muda.

## Quem aprova o quê

**Nada vai ao celular do Matheus para aprovar** (pedido dele, 12/10: "não preciso aprovar as coisas do Instagram,
pode me avisar que foi feito"). Todo texto passa pelo revisor automático, dentro dos limites do dia:

| Ação | O que acontece |
|---|---|
| achar e registrar leads | você faz; nada é enviado |
| aquecer (seguir, curtir, comentar) | sem texto: direto; comentário: revisor |
| primeira mensagem, lembrete, resposta, parceiro | revisor; aprovado sai na rodada |
| revisor reprovou | volta para você com o motivo: **reescreva** e proponha de novo (até 3 versões por perfil e tipo no dia) |

O Matheus fica sabendo do que saiu: aviso na hora quando alguém responde, "↩️ Respondi…" quando a resposta sai e o
resumo das 20h17.

## Regras que nunca mudam

- **Quem envia** é sempre **@raiz.connect**, nunca a conta pessoal @cardosomatheus1. O destinatário é o @ da ação
  aprovada. Pode ser qualquer lead do registro, inclusive o perfil pessoal do Matheus quando ele pede um teste.
- **Só execute o que `proxima` entregar**, com o texto EXATO. Nada fora dela, nada a mais.
- **Bloqueio de ação** ("tente mais tarde", "ação bloqueada", "suspeita de automação", verificação): pare tudo e
  mande `resultado` com bloqueio: true. A prospecção pausa 48 h e o Matheus é avisado.
- **Captcha:** nunca resolva. Pare e diga "PRECISA DE VOCÊ".
- **"http 429" numa consulta** (busca ou avaliação por script) **não é bloqueio de ação**: não use `resultado`
  nem "PRECISA DE VOCÊ". Pare os scripts e use as fontes fora do Instagram (seção 2a).
- **Leia a página:** abrir uma página não traz o texto dela. Depois de navegar, leia o conteúdo (`browser`
  content, ou `list` com include_content true) e decida só pelo que leu.
- **Nunca apague (desfaça o envio) de mensagem** sem ordem explícita do Matheus, e só depois de VER na conversa que
  há de fato duas iguais. Se uma mensagem nossa foi apagada, registre `prospeccao` acao "apagada" (acao_id, detalhe):
  ela deixa de contar como resposta, e uma única mensagem nova pode ser proposta. Resposta automática de robô
  (Manychat, "já já entraremos em contato") não é fala da pessoa.
- **Contato só pelo Instagram.** Nunca por WhatsApp, e-mail ou telefone, mesmo que a fonte traga esses dados.

## As rodadas do dia (tarefas agendadas)

| Rodada | Quando (Bahia) | O que faz |
|---|---|---|
| 🎯 Prospecção — buscar | 9h23 e 14h23 | seção 4 (mensagens e lembretes devidos) e seções 2 e 3 (repor o estoque de 100 leads) |
| 🎯 Prospecção — executar | :20 e :50, das 9h às 19h | seção 6 (lê respostas) e seção 5 (executa até 3 ações) |
| 🎯 Prospecção — resumo do dia | 20h17 | `prospeccao` acao "hoje": relatório ao celular |
| 🎯 Prospecção — semana | segunda, 8h41 | `metricas` de 7 e 28 dias: o que funcionou e o que muda |

Rodada sem novidade termina com a resposta exata **SEM NOVIDADE** (não vai ao celular).

## 1. Conta certa

1. Abra https://www.instagram.com/accounts/edit/. O campo de nome de usuário mostra a conta ATIVA.
2. Se não for `raiz.connect`: em https://www.instagram.com/, abra "Mais" (≡) ou a foto do perfil → **Trocar de
   conta** → `raiz.connect`. Ela já está adicionada e não pede senha. Confira de novo em /accounts/edit/.
3. Se `raiz.connect` não aparecer, ou pedir senha ou código: pare com "PRECISA DE VOCÊ: a conta da Raiz saiu do
   navegador".

## 2. Achar leads

**Estoque:** manter **100 leads prontos para aquecer** (o `contexto` mostra quanto falta). A busca (9h23 e 14h23)
repõe; a execução consome (a vaga de aquecer é preenchida sozinha com o melhor lead do estoque). Contam os que
encaixam, não os perfis abertos. As buscas na internet têm teto por dia: quando a ferramenta avisar, pare.

### 2a. Primeiro: fontes fora do Instagram (não gastam consulta no Instagram e não levam 429)

`prospeccao` acao "fontes" (`limite` 20). A ferramenta, sozinha:
1. pega empresas das **listas importadas** (planilha do SDR) e do **catálogo de CNPJ** (GuiaPJ: marmitas, pratos
   prontos, confeitaria e padaria em Salvador, Lauro de Freitas e Camaçari), avançando página por página;
2. acha o Instagram de cada empresa pelo buscador (Tavily) e só aceita quando o perfil bate com a empresa: mesmo
   telefone, @ dado pela fonte, ou mesmo nome e cidade;
3. pula bar, lanchonete, pizzaria e MEI com nome de pessoa sem gastar busca;
4. registra com nota os que encaixam e anota os recusados.

Chame de novo até bater a meta ou a fila acabar. Esses leads vêm com `conferir_atividade`, porque a data do último
post e às vezes os seguidores não aparecem na busca. A conferência acontece na visita do aquecimento (seção 5).

### 2b. Se faltar: busca no Instagram (por script)

1. `prospeccao` acao "buscar_script" com `termos` = até 3 buscas de região e segmento (ex.: "marmita salvador",
   "congelados salvador", "confeitaria lauro de freitas").
2. Rode o script com `browser` action "evaluate" numa aba em https://www.instagram.com/. Ele devolve um JSON com os
   @ achados.
3. Passe esse JSON para `perfis_script` (`achados` = o texto). A ferramenta tira os já conhecidos e rejeitados e
   devolve o script de avaliação (seção 3).
4. Não abra post por post para descobrir o autor. Sem @ novos, troque os termos.

## 3. Avaliar e dar nota

Você coleta evidência; a nota (0 a 100) é calculada pela ferramenta. Mínimo **55**; **75 ou mais é quente** e vai
primeiro. Leads das fontes (2a) já chegam avaliados.

Para os da busca no Instagram (2b):
1. Tente `avaliar_api` com `achados`. Se a API não estiver configurada, use o script.
2. **Script:** rode o texto de `perfis_script` com `browser` "evaluate" (5 perfis por vez, cerca de 2 s cada) e
   passe o JSON inteiro para `avaliar_perfis`. Ela registra os que encaixam, recusa os que não encaixam (parado,
   privado, pequeno ou grande demais, franquia, curso) e devolve em "conferir" só os que não dizem cidade ou
   segmento.
3. Para os de "conferir": abra o perfil, descubra o que falta e use `registrar` (com o item como base) ou `rejeitar`.
4. **429:** pare e volte para a seção 2a. Se ainda faltar, avalie abrindo os perfis um a um e registre com
   `registrar`. Use segmento, cidade, seguidores, `ultimo_post` (data do primeiro post NÃO fixado, conferida
   abrindo o post), canais, sinais, cardápio, link de pedido, exclusões e `post_recente`.

**Posts fixados** (alfinete) aparecem primeiro na grade e podem ser antigos. O "mais recente" é o primeiro NÃO
fixado; confira a data.

## 4. Propor as ações

Tudo numa só chamada: `prospeccao` acao "propor" com a lista (lead_id, tipo, texto, variante, base). O `lead_id` pode
ser o id ou o @. Em `base`, diga o que você viu e onde (post e data), ou "achado em fontes".

- **aquecer** (leads novos, maiores notas primeiro). Comentário só se houver algo genuíno a dizer sobre o
  `post_recente`: útil, específico, sem venda, sem citar a Raiz. Leads das fontes ainda não tiveram os posts
  vistos: proponha sem texto; o comentário é escrito na visita (seção 5, passo 5).
- **dm_abertura** (2+ dias depois do aquecimento; quem seguiu de volta, curtiu ou comentou vai primeiro).
  1. Abra o perfil e veja os 3 posts mais recentes NÃO fixados.
  2. Escreva pelo modelo do playbook, alternando:
     - **A:** pergunta sobre como precificam, sem oferta;
     - **B:** oferta da calculadora grátis, perguntando se pode mandar o link (sem o link).
  3. Cite UMA coisa concreta e verdadeira que você viu agora.
  4. **Sem link e sem preço**, assinando "— Matheus, da Raiz Connect".
- **dm_lembrete** (3+ dias depois da primeira mensagem, sem resposta): curto, com o link da **calculadora** (ou o do
  simulador de delivery para quem vende no iFood), diferente para cada pessoa.
- **resposta** (quem respondeu, seção 6): comece com "Oi, pessoal da {nome}!", retome o que a pessoa disse,
  apresente-se como Matheus, da Raiz Connect, e **ofereça a ferramenta gratuita**: o link da calculadora (o do
  simulador de delivery para quem vende no iFood) dizendo o que ela mostra e que é grátis. Vale mesmo se a resposta foi num
  comentário e ainda não falou de preço. O revisor libera e ela sai na rodada de execução (antes das
  outras ações).
- **Nunca peça a receita** (nem "me manda a receita que eu calculo"): soa invasivo, como se quiséssemos usar a
  receita da pessoa. A oferta é sempre a ferramenta grátis.
- **Saudação em toda mensagem:** perfil de negócio → "Oi, pessoal da {nome}!"; "Oi, {nome}!" só para perfil de
  pessoa.
- **Nunca:** texto igual para duas pessoas, fato inventado, mais de 2 mensagens sem resposta, contatar de novo quem
  disse não ou foi descartado.

O revisor confere cada texto contra o playbook. Proposta recusada traz o motivo ("REESCREVA…"): corrija exatamente o
que ele apontou e proponha de novo, até passar (no máximo 3 versões por perfil e tipo no dia).

## 5. Executar (uma ação por vez)

Antes da primeira ação da rodada: leia as respostas (seção 6) e registre `conferido`. Sem isso, `proxima` não
libera nada.

Depois, `prospeccao` acao "proxima" com `conta_ativa` = o @ ativo agora. Para a ação recebida:

**Aquecer: seguir, curtir e comentar**
1. Abra o perfil (link na ação).
2. **Se vier "ANTES DE SEGUIR" (lead das fontes):** confira três coisas:
   - que o perfil é mesmo do negócio indicado;
   - a data do primeiro post NÃO fixado (até 30 dias);
   - os seguidores (de 300 a 50 mil).

   Se falhar: NÃO siga nem curta. Chame `etapa` com etapa "descartado" e a nota ("parado há N dias", "perfil de
   outro negócio" ou "N seguidores"), e depois `resultado` com ok=false. Se passar, siga em frente e diga no
   detalhe a data do último post.
   **Descartou? Vem o próximo:** chame `proxima` de novo na hora. A vaga do dia não se perde: a ferramenta repõe
   com o melhor lead novo da fila (seguir e curtir, sem comentário). Descarte não conta nas 3 ações da rodada.
3. **Seguir:** botão "Seguir". Se já diz "Seguindo", está ok.
4. **Curtir:** abra 1 ou 2 posts recentes e curta; o ícone vira "Descurtir"/"Unlike".
5. **Sem texto na ação? Escreva um comentário na visita:** abra o primeiro post NÃO fixado e leia do que ele trata.
   Se houver algo genuíno a dizer (útil, específico, uma pergunta sobre o produto; sem venda, sem citar a Raiz, até
   220 caracteres), chame `prospeccao` acao "comentar" com acao_id, texto e base (o post e a data) ANTES do
   `resultado`. Só publique se vier **COMENTÁRIO APROVADO**; depois chame "comentado" (ok e detalhe).
   **"REESCREVA"** (o revisor reprovou): leia o motivo, escreva outra versão que resolva exatamente isso e chame
   "comentar" de novo, até aprovar (a ferramenta dá até 4 versões). Se vier "NÃO COMENTE", só siga e curta.
6. **Comentar** (se a ação já trouxer texto, ou depois de "COMENTÁRIO APROVADO"):
   - pegue o link do primeiro post NÃO fixado (`https://www.instagram.com/p/<código>/`) e abra esse link;
   - clique em "Adicione um comentário…", digite o texto EXATO e clique em **Publicar**;
   - confira que o comentário aparece na lista.
7. `resultado` com ok=true se SEGUIU, mesmo que o comentário falhe. Diga no detalhe o que saiu e o que não saiu.

**Mandar no Direct (primeira mensagem, parceiro, lembrete, resposta):**
1. Abra a conversa: se já existe, pela caixa de entrada; senão, perfil → **Mensagem**.
2. **Botão "Mensagem" parece desativado ou sem campo de texto:** a página costuma ainda estar carregando. Espere
   5 s, leia de novo e **clique nele mesmo assim** (em 11/10, Zen e Anna: o botão "desativado" abriu a conversa).
   Se não abrir, recarregue UMA vez. Só depois disso conte como falha.
3. **Não digite à mão.** Clique no campo de mensagem e aperte **Control+A** e depois **Backspace** (ações press do
   browser): isso apaga o rascunho de tentativas anteriores (o Instagram guarda e o texto saía duplicado: Zen e Anna,
   11/10). Depois rode o script "PARA DIGITAR NO DIRECT" que a `proxima` traz, com `browser` "evaluate": ele confere
   que o campo está vazio, coloca o texto uma vez e espera ele aparecer.
4. Só aperte Enter/Enviar se o script devolver **OK**. "CAMPO NÃO ESTÁ VAZIO": repita o passo 3. Outra resposta: não
   envie; rode de novo.
5. **Confira:** leia a conversa e veja a sua última mensagem: o texto tem de aparecer UMA vez, igual ao aprovado.
6. `resultado` só DEPOIS de conferir. **Depois de mandar `resultado`, não toque mais nessa conversa**: ação dada
   como falha nunca é enviada depois; se a tela mudar, proponha de novo na próxima rodada.

**Depois de cada ação:** `resultado` (acao_id, ok, detalhe = o que apareceu na tela). Espere 3 minutos antes da
próxima; no máximo 3 ações feitas por rodada (descarte não conta). Enquanto houver vaga de «aquecer» no dia, a
`proxima` sempre traz o próximo lead novo: só "NADA AGORA" encerra a rodada.

**Aquecimentos dos últimos 3 dias sem comentário** (pedido do Matheus): `prospeccao` acao "sem_comentario" lista quais
são. Para cada um, um por vez: abra o primeiro post NÃO fixado, escreva o comentário, "comentar" (acao_id, texto,
base); "REESCREVA" = corrija pelo motivo do revisor e tente de novo até aprovar; só publique com COMENTÁRIO
APROVADO; depois "comentado". Respeite o "ESPERE" (3 minutos entre ações).

## 6. Ler respostas (sempre antes de executar)

1. **Direct, conversa por conversa.** O `contexto` lista "Conversas no Direct para conferir": quem recebeu
   mensagem nossa. Para cada uma:
   - abra https://www.instagram.com/<@>/ → **Mensagem** e leia a conversa;
   - se a ÚLTIMA mensagem é da pessoa, é resposta;
   - a caixa de entrada (/direct/inbox/) NÃO mostra a lista como texto: nunca conclua "caixa vazia" por ela;
   - veja também https://www.instagram.com/direct/requests/, abrindo cada pedido de mensagem de @ do registro.
2. **Resposta automática não é resposta:** "Automation powered by Manychat", "já já entraremos em contato",
   "recebemos sua mensagem" e similares, que chegam segundos depois da nossa, são robôs. Não registre `etapa`, não
   proponha resposta e não avise o Matheus; anote só no `conferido` e espere a pessoa escrever de verdade.
3. **Notificações** (https://www.instagram.com/accounts/activity/): procure "respondeu ao seu comentário",
   "mencionou você", "replied to your comment" e "mentioned you". Curtida não é resposta.
4. **Para cada @ do registro que respondeu (pessoa, não robô):**
   - `etapa` com "respondeu", "lead" (pediu o link, usou a calculadora ou quer conversar) ou "descartado" (disse não), `nota` = o
     que a pessoa disse e `onde` = "direct" ou "comentario". O Matheus é avisado na hora, uma vez por resposta;
   - proponha a `resposta` (seção 4).
5. **`conferido`** com:
   - `direct`: quantas conversas novas e de quem;
   - `notificacoes`: as primeiras linhas copiadas da página;
   - `interagiram`: os @ do registro que seguiram de volta, curtiram ou comentaram.

## 7. Caminho do lead

novo → (aquecer) → aquecido → (primeira mensagem, 2+ dias) → abordado → (lembrete, 3+ dias) → lembrado → (5 dias sem
resposta) → sem_resposta, sem terceira mensagem.

Respondeu em qualquer ponto: respondeu → lead → demo → teste → cliente. Disse não: descartado (agradeça uma vez).

## 8. Limites

| Período | aquecer | primeira mensagem | lembrete | resposta | parceiro |
|---|---|---|---|---|---|
| Primeira semana (piloto) | 15 | 5 | 5 | 15 | 3 |
| Depois | 20 | 12 | 10 | 15 | 5 |

Só das 9h às 20h (Bahia), com 3 minutos entre ações. A ferramenta aplica tudo isso: se ela disser que não dá
agora, não force.

## 9. Pedidos avulsos do Matheus

- **"Acha N leads de Y":** seções 2a e 2b até criar N leads que encaixam (ou examinar 30 perfis no Instagram).
  Depois proponha «aquecer» para eles; se a cota do dia acabou, ficam para amanhã.
- **"Responde fulano" / "o que ele disse?":** seção 6 para esse @, depois proponha a resposta (o revisor libera).
- **"Como está a prospecção?":** `prospeccao` acao "hoje" (o dia) ou "metricas" (a semana).
- **"Importa esta lista":** salve como .json (nome, cidade, uf, segmento, telefone, instagram, site, evidencia,
  fonte) em /a0/usr/prospeccao/ e chame `importar_lista` com `arquivo`. Depois, `fontes` transforma a lista em
  leads.

## Ações da ferramenta `prospeccao`

| Ação | Para quê |
|---|---|
| `playbook`, `contexto` | regras e textos; cotas de hoje, quem deve receber o quê, conversas para conferir |
| `fontes`, `importar_lista` | leads fora do Instagram; importar lista de empresas |
| `buscar_script`, `perfis_script`, `avaliar_perfis`, `avaliar_api` | busca e avaliação no Instagram |
| `registrar`, `rejeitar` | lead à mão (com evidência); perfil examinado que não encaixa |
| `propor`, `editar` | propor ações; nova versão de um texto |
| `conferido`, `proxima`, `resultado` | liberar e executar uma ação por vez |
| `etapa` | mudar o estado do lead (respondeu, lead, demo, descartado…) |
| `hoje`, `metricas` | relatório do dia e números da semana |

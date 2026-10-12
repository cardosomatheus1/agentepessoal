---
name: prospeccao-instagram
description: "Como fazer a prospecção da Raiz Connect pela conta @raiz.connect no navegador: achar e avaliar leads, aquecer (seguir, curtir, comentar), mandar mensagens no Direct, ler e registrar respostas, sempre pela ferramenta prospeccao. Vale para as rodadas agendadas e para pedidos avulsos do Matheus."
version: 5.0.0
tags: ["instagram", "prospecção", "prospeccao", "raiz connect", "leads", "direct"]
trigger_patterns:
  - "prospec"
  - "raiz.connect"
  - "lead"
---

# Prospecção da Raiz Connect no navegador

Três fontes, cada uma com o seu assunto:
- **a ferramenta `prospeccao`** decide o quê e quando (limites, prazos, quem recebe o quê, revisor, pausas) e entrega
  o texto exato de cada ação;
- **o playbook** (`prospeccao` acao "playbook") tem as regras comerciais e os modelos. Leia-o inteiro antes de escrever
  qualquer texto: é por ele que o revisor confere;
- **esta skill** ensina o como: o navegador e a ordem das chamadas.

Todo texto passa por um revisor automático; nada vai ao Matheus para aprovar. Reprovado volta com "REESCREVA" e o
motivo: corrija exatamente isso e mande de novo só esse item (mensagem: `propor`, até 3 versões por perfil e tipo no
dia; comentário: `comentar`, até 2). `editar` troca o texto de uma ação aprovada que ainda não saiu.

## Regras que nunca mudam

- **Quem envia** é sempre **@raiz.connect** (seção 1), nunca a conta pessoal @cardosomatheus1.
- **Só execute o que a `proxima` entregar**, com o texto EXATO. Nada fora dela, nada a mais.
- **Bloqueio** (depois de um clique seu, como seguir, curtir, comentar ou enviar, ou em qualquer tela: "Ação
  bloqueada", "Tente novamente mais tarde", "suspeita de automação", código, selfie, "confirme que é você", captcha):
  não resolva, não clique de novo, pare tudo. `resultado` com bloqueio: true (com o `acao_id` se havia ação; sem ele,
  se não havia) e termine com "PRECISA DE VOCÊ: o Instagram bloqueou ou pediu verificação". A prospecção pausa 48 h.
- **Limite de consulta** (só quando um script de busca, avaliação ou conferência devolve "http 429", sem clique seu):
  a ferramenta registra sozinha ao receber o resultado do script; se ela não avisou, chame `limite_consulta`. Até o
  dia seguinte: nenhum script e nenhum perfil aberto para avaliar (abrir o perfil de quem vai receber mensagem
  continua valendo). Termine com "CONSULTA LIMITADA (429)". **Na dúvida entre bloqueio e limite, é bloqueio.**
- **Leia a página:** abrir uma página não traz o texto dela. Depois de navegar, leia o conteúdo (`browser` content, ou
  `list` com include_content true) e decida só pelo que leu.
- **O que conta como visto:** só o que está escrito (legenda, texto na arte, nome e preço do produto, bio, cardápio,
  destaque) ou o que você viu num print (`browser` screenshot). A descrição automática do Instagram ("Pode ser uma
  imagem de…") não é fato: nunca cite o que vem só dela. Em `base`, copie entre aspas o trecho que sustenta o detalhe
  e a data do post. **Último post** = o mais recente entre os 4 primeiros da grade (até 3 podem estar fixados, e o
  alfinete nem sempre aparece no texto): compare as datas abrindo-os.
- **Contato só pelo Instagram.** Você nunca contata por WhatsApp, e-mail ou telefone. Se a pessoa pedir, peça o número
  (playbook) e registre "demo": quem chama é o Matheus.
- **Nunca apague mensagem** (desfazer envio) sem ordem explícita do Matheus, nem a que saiu duplicada ou cortada
  (registre como está, seção 5). Apagada por ordem dele: `apagada` (acao_id, detalhe).
- **Tentativas têm fim:** o script de digitar, no máximo 2 vezes por ação. Não deu: `resultado` ok=false com o que
  viu, e siga.
- **Esperar:** "ESPERE" diz até que horas. Espere no terminal (code_execution_tool) com o comando que a ferramenta
  mostra (cerca de 3 min por vez; repita) e chame de novo. Se o horário passar do início da próxima rodada, termine.

## As rodadas

| Rodada | Quando (Bahia) | Roteiro |
|---|---|---|
| 🎯 buscar | 9h23 e 14h23 | seção 1; seção 4 (propor o que é devido); seções 2 e 3 (repor o estoque) |
| 🎯 executar | minutos 8 e 38, das 9h às 21h | seção 1; seção 6 e `caixa_lida`; seção 5 (`proxima` até 3 ações feitas ou "NADA AGORA") |
| 🎯 resumo do dia | 20h17 | `prospeccao` acao "hoje" |

Depois das 20h e no dia de folga (domingo), a `proxima` só entrega respostas a quem escreveu, até 22h; o resto espera.

**Resposta final da rodada, uma linha só:** SEM NOVIDADE (as falas das pessoas já chegam ao Matheus pela ferramenta,
e o que foi feito vai no resumo das 20h17); ou CONSULTA LIMITADA (429); ou "PRECISA DE VOCÊ:" e o que impediu a
rodada (bloqueio, verificação, conta, erro), em até 3 linhas.

## 1. Conta certa (início de toda rodada)

1. Em https://www.instagram.com/, leia o link "Perfil" do menu lateral: ele tem de apontar para
   https://www.instagram.com/raiz.connect/. Se não der para ler, abra https://www.instagram.com/accounts/edit/ e leia
   o nome de usuário.
2. Outra conta ativa: "Mais" (≡) ou a foto do perfil → **Trocar de conta** → `raiz.connect` (já está adicionada, não
   pede senha). Confira de novo.
3. `raiz.connect` não aparece, ou pede senha ou código: pare com "PRECISA DE VOCÊ: a conta da Raiz saiu do navegador".

## 2. Achar leads (rodada de busca)

O `contexto` mostra o estoque de leads prontos por fonte e quanto falta em cada parte. **Prefira o que não usa a
nossa conta**; script no navegador é o último recurso, com teto diário (a ferramenta conta e avisa).

1. **Planilha e catálogo:** `fontes` (`limite` 20), de novo até a ferramenta dizer que a parte encheu ou a fila acabou.
2. **Parte do Instagram:** `fontes_instagram` (Apify, sem usar a nossa conta), de novo até a parte encher ou a
   ferramenta avisar a verba do mês.
3. **Sem Apify, e só se a ferramenta deixar:** `buscar_script` com até 3 buscas de segmento e cidade (ex.: "marmita fit
   bh", "confeitaria recife") → rode o script com `browser` action "evaluate" numa aba em https://www.instagram.com/ →
   leve o JSON inteiro para a seção 3. Sem @ novos, troque os termos. Não abra post por post para achar o autor.
4. **Conferir o estoque** (leads achados fora do Instagram): `conferir_estoque`. Ela confere sozinha quando pode; senão
   devolve um script: rode com "evaluate" e passe o texto para `estoque_conferido`. No máximo 3 vezes por rodada;
   "Nada a conferir", pausa ou teto: pare esta parte.

## 3. Avaliar (você coleta evidência; a nota é da ferramenta)

1. Primeiro `avaliar_api` com os `achados`. Sem a API: `perfis_script` → rode o script com "evaluate" → passe o JSON
   inteiro para `avaliar_perfis`. Ela registra os que encaixam, recusa os que não encaixam e devolve em "conferir" só
   os que não dizem cidade ou segmento.
2. Para cada um de "conferir": abra o perfil, descubra o que falta e use `registrar` (copie os dados do item e complete
   o que faltava) ou `rejeitar`.

## 4. Propor (rodada de busca)

Tudo numa só chamada: `prospeccao` acao "propor" com a lista de {lead_id, tipo, texto, base}. O `lead_id` pode ser o
id ou o @. O `contexto` lista quem "deve receber" cada tipo agora; os textos seguem o playbook (seção 5).

- **dm_abertura:** abra o perfil, leia a bio e os posts recentes e escreva na variante que o `contexto` indica para
  aquele lead. Deixe `variante` em branco: a ferramenta sorteia, para a comparação A × B valer. Em `base`, o trecho
  copiado entre aspas e a data do post.
- **dm_lembrete** (só aparece para quem segue a Raiz ou interagiu) e **seguimento** (2 dias depois do link): pelo
  playbook. Em `base`, o que há de novo no perfil, se houver.
- **aquecer:** não proponha. A ferramenta tira do estoque sozinha, e o comentário é escrito na visita (seção 5).
- **resposta:** na rodada de execução, logo depois de registrar a fala (seção 6).

## 5. Executar (rodada de execução, uma ação por vez)

Depois da seção 6 e da `caixa_lida`: `prospeccao` acao "proxima" com `conta_ativa` = o @ ativo. A ação que ela entrega
é só desta rodada. "ESPERE": espere (regras) e chame de novo. "NADA AGORA" ou 3 ações feitas: termine.

**"CONFIRA ANTES DE QUALQUER ENVIO"**: uma rodada anterior pegou essa ação e não registrou o resultado; ela pode ter
saído. Só olhe a tela (a conversa ou o botão «Seguindo») e chame `resultado` com o que viu. Não envie nem refaça.

**Aquecer: seguir, curtir, ver os stories, comentar**
1. Abra o perfil (link na ação).
2. **"ANTES DE SEGUIR"** (lead das fontes): confira que o perfil é do negócio indicado, a data do último post (até 30
   dias) e os seguidores (de 300 a 50 mil). Se falhar: não siga nem curta; `etapa` com o `lead_id` da ação, etapa
   "descartado" e a nota ("parado há N dias", "N seguidores" ou "perfil de outro negócio"). Parado ou fora da faixa
   volta ao estoque em 60 dias. Chame `proxima` de novo (a vaga do dia é reposta).
3. **Seguir:** botão "Seguir" ("Seguindo" já está ok). **Curtir:** 1 ou 2 posts recentes. **Stories:** se a foto tiver
   o anel colorido, veja-os, sem reagir.
4. **Comentário** (ação sem texto): só num post de até 7 dias com algo escrito para comentar. `comentar` (acao_id,
   texto, base) ANTES do `resultado`; publique só com **COMENTÁRIO APROVADO** e depois chame `comentado` (ok,
   detalhe). "NÃO COMENTE" ou reprovado duas vezes: só siga e curta.
5. **Publicar:** abra o link do post (`https://www.instagram.com/p/<código>/`), clique em "Adicione um comentário…",
   digite o texto EXATO, **Publicar** e confira que ele aparece.
6. `resultado` ok=true se SEGUIU, mesmo que o comentário falhe; no detalhe, o que saiu e o que não saiu.

**Mandar no Direct** (primeira mensagem, lembrete, seguimento, resposta, parceiro)
1. Abra sempre pelo perfil: https://www.instagram.com/<@>/ → **Mensagem** (abre a conversa que existe ou uma nova).
   Botão "Mensagem" parecendo desativado: a página costuma estar carregando; espere 5 s, leia de novo e clique mesmo
   assim; se não abrir, recarregue UMA vez.
2. **Leia a conversa antes de digitar.** Não envie, e chame `resultado` ok=false com o que viu, se: a última mensagem é
   da pessoa (trate pela seção 6; resposta automática não conta); há uma conversa anterior que a ação não previa; é
   lembrete ou seguimento e a nossa mensagem anterior não aparece; ou o Instagram não deixa mandar (conta que só
   recebe de quem ela segue, solicitação ainda não aceita). Não tente de novo hoje.
3. **Não digite à mão.** Clique no campo, aperte **Control+A** e depois **Backspace** (ações press do browser) para
   apagar rascunho de tentativa anterior, e rode o script "PARA DIGITAR NO DIRECT" que a `proxima` traz, com
   `browser` "evaluate".
4. Só aperte Enter/Enviar se o script devolver **OK**. "CAMPO NÃO ESTÁ VAZIO": repita o passo 3 (no máximo 2 vezes no
   total). Outra resposta: não envie; `resultado` ok=false.
5. **Confira:** a sua última mensagem aparece UMA vez, igual à aprovada. Saiu duplicada ou cortada: não apague;
   `resultado` ok=true com o detalhe ("saiu duplicada"), e o Matheus decide.
6. `resultado` só DEPOIS de conferir. Depois dele, não toque mais nessa conversa: ação dada como falha nunca é enviada
   depois.

## 6. Ler respostas (toda rodada de execução, antes de agir)

1. **Direct:** o contador de não lidas (ícone de Mensagens) diz SE há algo novo, não DE QUEM, e zera quando alguém lê
   pelo celular; a caixa de entrada não mostra a lista como texto. Por isso:
   - toda rodada: veja o contador e https://www.instagram.com/direct/requests/, e abra (perfil → Mensagem) as conversas
     que o `contexto` lista em "Direct nesta rodada";
   - contador acima de zero sem você achar de quem é, ou o `contexto` pedindo **VARREDURA COMPLETA**: abra cada
     conversa da lista e leia. Depois, `caixa_lida` com varredura: true;
   - é resposta se a ÚLTIMA mensagem da conversa é da pessoa e não é automática (item 3).
2. **Notificações** (https://www.instagram.com/accounts/activity/): "respondeu ao seu comentário", "mencionou você",
   "começou a seguir você", curtidas.
3. **Resposta automática não é resposta** ("Automation powered by Manychat", "já já entraremos em contato",
   "recebemos sua mensagem" segundos depois da nossa): não registre nem responda; anote só na `caixa_lida`.
4. **Para cada @ do registro que falou:**
   - **respondeu ao nosso comentário:** `etapa` com etapa "interagiu" e a `nota` (o que disse). Só se falou de preço,
     custo, lucro ou do sistema: etapa "respondeu", `onde` "comentario" e negocio: true, e responda pelo Direct;
   - **no Direct:** `etapa` pelo que a pessoa disse (playbook, seção 6), `nota` = o que disse, `onde` "direct". O Matheus
     é avisado na hora. Depois proponha a `resposta` pelo playbook (áudio, foto ou figurinha sozinhos: não responda).
5. **`caixa_lida`** com `direct` (quantas conversas com mensagem nova e de quem), `notificacoes` (as primeiras linhas
   copiadas da página), `interagiram` (os @ do registro que seguiram de volta, curtiram ou comentaram) e `varredura`
   (true só depois da varredura completa). Sem ela, a `proxima` não libera nada.

## 7. Pedidos avulsos do Matheus

- **"Acha N leads de Y":** seção 2 até criar N leads que encaixam (respeitando o teto de consultas). Eles entram no
  estoque e a execução aquece pela ordem da nota.
- **"Responde fulano" / "o que ele disse?":** seção 6 para esse @ e depois a resposta pelo playbook.
- **"Como está a prospecção?":** `hoje` (o dia) ou `metricas` (os números).
- **"Me manda o cartão do @x":** `cartao`.
- **"Deixa que eu falo com @x" / "pode voltar a falar com @x":** `assumir` / `devolver`.
- **"Pode voltar a consultar"** (depois de 2 dias de 429): `liberar_consultas`.
- **"Importa esta lista":** salve como importar_AAAAMMDD_origem.json em /a0/usr/prospeccao/ (campos nome, cidade, uf,
  segmento, telefone, instagram, site, evidencia, fonte), chame `importar_lista` e depois `fontes`.

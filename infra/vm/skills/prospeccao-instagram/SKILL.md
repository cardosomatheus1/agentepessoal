---
name: prospeccao-instagram
description: "Como fazer a prospecção da Raiz Connect pela conta @raiz.connect no navegador: achar e avaliar leads, aquecer (seguir, curtir, comentar), mandar mensagens no Direct, ler e registrar respostas, sempre pela ferramenta prospeccao. Vale para as rodadas agendadas e para pedidos avulsos do Matheus."
version: 5.2.0
tags: ["instagram", "prospecção", "prospeccao", "raiz connect", "leads", "direct"]
trigger_patterns:
  - "prospec"
  - "raiz.connect"
  - "raiz connect"
---

# Prospecção da Raiz Connect no navegador

A ferramenta `prospeccao` decide o quê e quando (limites, prazos, quem recebe o quê, pausas) e entrega o texto exato
de cada ação. O playbook (`prospeccao` acao "playbook") tem as regras comerciais, os modelos e os fatos sobre a Raiz:
leia-o inteiro antes do primeiro texto de cada rodada. Esta skill ensina o como: o navegador e a ordem das chamadas.

Todo texto passa por um revisor automático; nada vai ao Matheus para aprovar. Reprovado volta com "REESCREVA" e o
motivo: corrija exatamente isso e mande de novo só esse item (mensagem: `propor`, até 3 versões por perfil e tipo no
dia; comentário: `comentar`, até 2). `editar` troca o texto de uma ação aprovada que ainda não saiu.

## Regras que nunca mudam

- **Quem envia** é sempre **@raiz.connect** (seção 1), nunca a conta pessoal @cardosomatheus1.
- **Só faça no Instagram o que a ferramenta aprovou:** a ação da `proxima` (texto EXATO), o comentário que voltou com
  COMENTÁRIO APROVADO e o "Aceitar" da solicitação de quem vai receber resposta. Ler, rolar, fechar pop-up e conferir
  a conta não precisam de aprovação. Nunca clique em "Excluir", "Bloquear" ou "Denunciar".
- **Bloqueio** (depois de um clique seu, como seguir, curtir, comentar ou enviar, ou em qualquer tela: "Ação
  bloqueada", "Tente novamente mais tarde", "suspeita de automação", código, selfie, "confirme que é você", captcha):
  não resolva, não clique de novo, pare tudo. `resultado` com bloqueio: true (com o `acao_id` se havia ação; sem ele,
  se não havia) e termine com "PRECISA DE VOCÊ: o Instagram bloqueou ou pediu verificação". A prospecção pausa 48 h e
  volta pela metade; um segundo bloqueio em 30 dias só volta quando o Matheus liberar.
- **Limite de consulta** ("http 429" na resposta de um script, sem clique seu): a ferramenta registra sozinha; se ela
  não avisou, chame `limite_consulta`. Até o dia seguinte, nenhum script e nenhum perfil aberto para avaliar (abrir o
  perfil de quem vai receber mensagem continua valendo). **Na dúvida entre bloqueio e limite, é bloqueio.**
- **Leia a página:** abrir uma página não traz o texto dela. Depois de navegar, leia o conteúdo (`browser` content, ou
  `list` com include_content true) e decida só pelo que leu. Clique que falha ("could not find reference"): a página
  mudou; leia de novo e use a referência nova, ou vá pelo endereço (perfil: https://www.instagram.com/<@>/). Nunca
  repita a mesma referência; só desista depois de recarregar a página uma vez. Pop-up ("Ativar notificações", "Salvar
  suas informações de login", cookies): feche com "Agora não".
- **O que conta como visto:** só o que está escrito (legenda, texto na arte, nome e preço do produto, bio, cardápio,
  destaque). O print (`browser` screenshot) serve para ler o texto da arte, as reações e o que está não lido. A
  descrição automática do Instagram ("Pode ser uma imagem de…") não é fato. Em `base`, copie entre aspas o trecho
  escrito (dizendo se é da legenda, da arte ou da bio) e a data do post. **Último post** = o mais recente entre os 4
  primeiros da grade (até 3 podem estar fixados, e o alfinete nem sempre aparece no texto): compare as datas.
- **Contato só pelo Instagram.** Você nunca contata por WhatsApp, e-mail ou telefone. Se a pessoa pedir, peça o número
  (playbook) e registre "demo": quem chama é o Matheus.
- **Nunca apague mensagem** (desfazer envio) sem ordem explícita do Matheus, nem a que saiu duplicada ou cortada
  (registre como está, seção 3). Apagada por ordem dele: `apagada` (acao_id, detalhe).
- **Tentativas têm fim:** digitar (script no Direct, `type` no comentário), no máximo 2 vezes por ação. Não deu:
  `resultado` ok=false (ou `comentado` ok=false) com o que viu, e siga.
- **Esperar:** "ESPERE" diz até que horas. Espere no terminal (code_execution_tool) com o comando que a ferramenta
  mostra (cerca de 3 min por vez; repita) e chame de novo. Se passar do início da próxima rodada, termine.

## As rodadas (uma por vez)

**Execução** (minutos 8 e 38, das 9h08 às 12h38 e das 14h08 às 21h38): 1. a espera sorteada do prompt; 2. conta
certa (seção 1); 3. `contexto`; 4. `playbook` (inteiro, sempre: a etapa e a resposta de cada fala dependem dele);
5. ler respostas e `caixa_lida` (seção 2); 6. `proxima` até 3 ações feitas ou "NADA AGORA" (seção 3); 7. resposta final.
Depois das 20h e no domingo, a `proxima` só entrega respostas a quem escreveu, até 22h.

**Busca** (8h07 e 13h07): 1. a espera sorteada; 2. conta certa; 3. `playbook` e `contexto`; 4. propor o que é devido
(seção 4); 5. repor o estoque (seções 5 e 6); 6. resposta final. Veja a hora (terminal: `date`) antes de cada lote e
termine até 9h03 ou 14h03, antes da execução; o que faltar fica para a busca seguinte.

**Resumo** (20h17): `hoje`; a resposta final é o texto que ele devolver (ou SEM NOVIDADE se vier "NADA HOJE").

**Resposta final da rodada, e nada além dela:** SEM NOVIDADE (as falas registradas já chegam ao Matheus pela
ferramenta, e o que foi feito vai no resumo das 20h17); ou CONSULTA LIMITADA (429); ou "PRECISA DE VOCÊ:" e o que
precisa dele (bloqueio, verificação, conta, erro), em até 3 linhas.

## 1. Conta certa (início de toda rodada)

1. Em https://www.instagram.com/, leia o link "Perfil" do menu lateral: ele tem de apontar para
   https://www.instagram.com/raiz.connect/. Se não der para ler, abra https://www.instagram.com/accounts/edit/ e leia
   o nome de usuário.
2. Outra conta ativa: "Mais" (≡) ou a foto do perfil → **Trocar de conta** → `raiz.connect` (já está adicionada, não
   pede senha). Confira de novo.
3. `raiz.connect` não aparece, ou pede senha ou código: pare com "PRECISA DE VOCÊ: a conta da Raiz saiu do navegador".

## 2. Ler respostas (toda rodada de execução, antes de agir)

1. **Direct:** o contador de não lidas diz SE há algo novo, não DE QUEM, e zera quando alguém lê pelo celular. Por isso:
   - toda rodada, tire print de https://www.instagram.com/direct/inbox/: conversa em negrito ou com ponto azul é não
     lida; abra também essas. Solicitações (https://www.instagram.com/direct/requests/) e notificações: na primeira
     rodada de cada turno (9h08 e 14h08), na última (21h38), na VARREDURA COMPLETA e quando o contador do Direct ou do
     coração estiver acima de zero;
   - abra (perfil → Mensagem) as conversas que o `contexto` lista em "Direct nesta rodada";
   - contador acima de zero que você não explicou, ou o `contexto` pedindo **VARREDURA COMPLETA**: abra uma a uma as
     conversas da lista do `contexto`. Depois, `caixa_lida` com varredura: true.
2. **É fala da pessoa** quando a ÚLTIMA coisa na conversa é dela: mensagem, áudio, figurinha, ou reação (❤️, 👍) à 1ª
   mensagem, ao lembrete ou a uma pergunta nossa. A reação não vira mensagem nova: se o texto da página não mostrar, olhe
   o print embaixo do nosso balão; nota "reagiu com <reação> a: <começo da nossa frase>". Reação a mensagem nossa que
   não perguntava nada (link enviado, agradecimento, despedida): não é fala; não registre.
3. **Resposta automática não é fala** ("Automation powered by Manychat", "já já entraremos em contato", "recebemos sua
   mensagem" segundos depois da nossa): não registre nem responda; anote só na `caixa_lida`. Se ela disser que só
   atendem pelo WhatsApp: não responda; `etapa` "respondeu", nota "pendente: só atende no WhatsApp (<número>)" (quem
   decide se chama é o Matheus).
4. **Notificações** (https://www.instagram.com/accounts/activity/; se a página não mostrar a lista, clique em
   "Notificações", o coração do menu lateral, e leia o painel): "respondeu ao seu comentário", "mencionou você",
   "começou a seguir você", curtidas.
5. **Para cada @ do registro que falou:**
   - **respondeu ao nosso comentário:** `etapa` com etapa "interagiu" e a `nota` (o que disse). Só se falou de preço,
     custo, lucro ou do sistema: etapa "respondeu", `onde` "comentario" e negocio: true, e proponha a `resposta`;
   - **no Direct:** `etapa` pelo que a pessoa disse (playbook › Respostas), `nota` = o que disse (começando por
     "pendente:" quando depende do Matheus), `onde` "direct". O Matheus é avisado na hora. Depois proponha a `resposta`
     (`base` = a fala dela, entre aspas); ela sai pela `proxima`, nesta rodada ou na próxima.
6. **@ fora do registro que escreveu para a Raiz:** `entrou` com `handle`, `nota` (o que escreveu) e negocio: true se
   fala da Raiz, da calculadora, de preço ou do nosso comentário. Com negocio, a pessoa entra no registro e você propõe
   a `resposta` como para qualquer um (pode dizer quem fala). Sem negocio, o Matheus é avisado uma vez só e você não
   responde. Propaganda ou spam: só anote na `caixa_lida`.
7. **`caixa_lida`** com `direct` (quantas conversas com mensagem nova e de quem), `notificacoes` (as primeiras linhas
   copiadas da página), `interagiram` (os @ do registro que seguiram de volta, curtiram ou comentaram) e `varredura`
   (true só depois da varredura completa). Sem ela, a `proxima` não libera nada.

## 3. Executar (rodada de execução, uma ação por vez)

`prospeccao` acao "proxima" com `conta_ativa` = o @ ativo. A ação que ela entrega é só desta rodada. "ESPERE":
espere (regras) e chame de novo. "NADA AGORA" ou 3 ações feitas: termine.

**"CONFIRA ANTES DE QUALQUER ENVIO"**: uma rodada anterior pegou essa ação e não registrou o resultado; ela pode ter
saído. Só olhe a tela (a conversa ou o botão «Seguindo») e chame `resultado` com o que viu. Não envie nem refaça.

**Aquecer**
1. Abra o perfil (link na ação) e leia a bio e os posts.
2. **"ANTES DE SEGUIR"** (lead das fontes): confira que o perfil é do negócio indicado, a data do último post (até 30
   dias; stories no ar, com o anel colorido, também contam) e os seguidores (de 300 a 50 mil). Se falhar, não siga
   nem curta: `etapa` com o `lead_id` da ação, etapa "descartado" e a nota ("parado há N dias", "N seguidores" ou
   "perfil de outro negócio"). Parado ou fora da faixa volta ao estoque em 60 dias.
3. **Seguir:** "Seguir" ou "Seguir de volta" (a pessoa já segue a Raiz: diga no detalhe); "Seguindo" já está ok.
   "Solicitado" ou perfil privado: não siga; `etapa` descartado, nota "perfil privado". Perfil que não existe mais,
   mudou de @ ou nos bloqueou: `etapa` descartado, nota "perfil sumiu". Todo descarte já encerra a ação (sem
   `resultado`): chame `proxima` de novo. Depois de seguir: veja os stories, se houver anel colorido (sem reagir), e
   curta 1 post que você leu.
4. **Comentário:** só se a ação disser **PODE COMENTAR** (lead quente) e houver post de até 7 dias com algo escrito
   sobre o qual você tenha algo próprio a dizer. `comentar` (acao_id, texto, base) ANTES do `resultado`; publique só
   com **COMENTÁRIO APROVADO** e depois chame `comentado` (ok, detalhe). "NÃO COMENTE" ou reprovado duas vezes: siga
   sem comentário. Para publicar: abra o link do post (`https://www.instagram.com/p/<código>/`), clique em "Adicione um
   comentário…", digite o texto EXATO com a ação `type` do browser, **Publicar** e confira que ele aparece.
5. `resultado` ok=true se SEGUIU, mesmo que o comentário falhe; no detalhe, o que saiu e o que não saiu.

**Mandar no Direct** (primeira mensagem, lembrete, seguimento, resposta, parceiro)
1. Abra sempre pelo perfil: https://www.instagram.com/<@>/ → **Mensagem** (abre a conversa que existe ou uma nova).
   Botão "Mensagem" parecendo desativado: espere 5 s, leia de novo e clique mesmo assim; se não abrir, recarregue UMA
   vez. Conversa em Solicitações ("Aceitar", "Excluir", "Bloquear"): se a ação é resposta, clique em **Aceitar** e siga.
2. **Leia a conversa antes de digitar.** Resposta automática (seção 2) não conta como fala. Não envie, chame
   `resultado` ok=false com o que viu e siga, se:
   - é primeira mensagem, lembrete, seguimento ou parceiro e a última coisa na conversa é da pessoa: trate pela seção 2;
   - é **resposta** e já há mensagem nossa depois da fala que ela responde (o Matheus pode ter respondido pelo
     celular): detalhe "já respondida"; não proponha nada;
   - é **resposta** e a pessoa escreveu de novo: registre a fala nova (seção 2) e proponha UMA resposta que cubra tudo
     o que ela escreveu desde a nossa última mensagem (ela sai pela `proxima`, hoje mesmo);
   - há conversa que a ação não previa; é lembrete ou seguimento e a nossa anterior não aparece; ou o Instagram não
     deixa mandar (conta que só recebe de quem ela segue).
   A ação que falhou nunca é refeita; uma resposta nova, aprovada depois, sai normalmente.
3. **Não digite à mão.** Clique no campo, aperte **Control+A** e depois **Backspace** (ações press do browser) para
   apagar rascunho de tentativa anterior, e rode o script "PARA DIGITAR NO DIRECT" que a `proxima` traz, com
   `browser` "evaluate".
4. Só aperte Enter/Enviar se o script devolver **OK**. "CAMPO NÃO ESTÁ VAZIO": repita o passo 3 (no máximo 2 vezes no
   total). Outra resposta: não envie; `resultado` ok=false.
5. **Confira:** a sua última mensagem aparece UMA vez, igual à aprovada. Saiu duplicada ou cortada: não apague;
   `resultado` ok=true com o detalhe ("saiu duplicada"), e o Matheus decide.
6. `resultado` só DEPOIS de conferir. Depois dele, não toque mais nessa conversa nesta ação.

## 4. Propor (rodada de busca; respostas, na execução)

`prospeccao` acao "propor" com a lista de {lead_id, tipo, texto, base}, **em lotes de até 5**, à medida que você lê
os perfis (o que já foi proposto não se perde se a rodada cair). O `lead_id` pode ser o id ou o @. O `contexto` lista
quem "deve receber" cada tipo agora e os "Textos de hoje"; os textos seguem o playbook › Modelos.

- **dm_abertura:** abra o perfil, leia a bio e os posts recentes e escreva na variante que o `contexto` indica para
  aquele lead. Deixe `variante` em branco: a ferramenta sorteia, para a comparação A × B valer.
- **dm_lembrete** (só aparece para quem segue a Raiz ou interagiu) e **seguimento** (o `contexto` diz o motivo: link
  sem resposta ou só com agradecimento, "agora não" há 30 dias, ou "vou passar pro dono"): pelo playbook. Em `base`, o
  que há de novo no perfil, se houver.
- **aquecer:** não proponha. A ferramenta tira do estoque sozinha.
- **resposta:** na rodada de execução, logo depois de registrar a fala (seção 2), com `base` = a fala entre aspas.

## 5. Achar leads (rodada de busca)

O `contexto` mostra o estoque de leads prontos por fonte e quanto falta em cada parte. Nada aqui usa a nossa conta:
busca e avaliação por script com a @raiz.connect ficam desligadas, a não ser que o Matheus ligue (a ferramenta avisa).
Não navegue em hashtag ou Explorar para achar leads.

1. **Planilha e catálogo:** `fontes` (`limite` 20), de novo até a ferramenta dizer que a parte encheu ou a fila acabou.
2. **Parte do Instagram:** `fontes_instagram` (Apify), de novo até a parte encher ou a ferramenta avisar a verba do
   mês. Sem Apify: siga com o estoque que há.
3. **Conferir o estoque** (leads achados fora do Instagram): `conferir_estoque` (Apify ou API oficial), no máximo 3
   vezes por rodada. "Nada a conferir" ou "a conferência fica para a visita": pare esta parte.
4. **Scripts com a conta:** só se a ferramenta disser que estão ligados; ela traz o passo a passo.

## 6. Avaliar (você coleta evidência; a nota é da ferramenta)

1. Para @ que o Matheus mandar: `avaliar_api` (API oficial). A ferramenta registra os que encaixam, recusa os que não
   encaixam e devolve em "conferir" só os que não dizem cidade ou segmento.
2. Para cada um de "conferir": abra o perfil, descubra o que falta e use `registrar` (copie os dados do item e complete
   o que faltava) ou `rejeitar`.
3. Curso, professor, influenciador, consultor, contador ou fornecedor: `registrar` com canal "parceiro", sem
   exclusões. A mensagem de parceiro só sai quando o Matheus pedir.

## 7. Pedidos avulsos do Matheus

- **"Acha N leads de Y":** seção 5 até criar N leads que encaixam. Eles entram no estoque e a execução aquece pela
  ordem da nota.
- **"Responde fulano" / "o que ele disse?":** seção 2 para esse @ e depois a resposta pelo playbook. **"Responde @x:
  <texto ou fato>"** (ele ditou): `propor` a `resposta` com isso, `base` "o Matheus disse: …".
- **"Manda para os parceiros":** `propor` tipo "parceiro" para os parceiros registrados, pelo modelo do playbook.
- **"Como está a prospecção?":** `hoje` (o dia) ou `metricas` (os números).
- **"Me manda o cartão do @x":** `cartao`.
- **"Deixa que eu falo com @x" / "pode voltar a falar com @x":** `assumir` / `devolver`.
- **"Pode voltar"** depois de um segundo bloqueio: `liberar_bloqueio`. **"Pode voltar a consultar"** (depois de 2 dias
  de 429): `liberar_consultas`. **"Liga/desliga os scripts":** `scripts_conta` com texto "ligar" ou "desligar".
- **"Importa esta lista":** salve como importar_AAAAMMDD_origem.json em /a0/usr/prospeccao/ (campos nome, cidade, uf,
  segmento, telefone, instagram, site, evidencia, fonte), chame `importar_lista` e depois `fontes`.

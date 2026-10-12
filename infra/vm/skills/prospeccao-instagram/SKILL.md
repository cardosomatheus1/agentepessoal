---
name: prospeccao-instagram
description: "Como fazer a prospecção da Raiz Connect pela conta @raiz.connect no navegador: achar e avaliar leads, aquecer (seguir, curtir, comentar), mandar mensagens no Direct, ler e registrar respostas, sempre pela ferramenta prospeccao. Vale para as rodadas agendadas e para pedidos avulsos do Matheus."
version: 4.0.0
tags: ["instagram", "prospecção", "prospeccao", "raiz connect", "leads", "direct", "comentário"]
trigger_patterns:
  - "prospec"
  - "raiz.connect"
  - "aquecer"
  - "lembrete"
---

# Prospecção da Raiz Connect no navegador

Três fontes, cada uma com o seu assunto (não procure regra fora do lugar dela):
- **a ferramenta `prospeccao`** decide o quê e quando: limites, prazos, quem deve receber o quê, revisor, pausas;
- **o playbook** (`prospeccao` acao "playbook") tem as regras comerciais e os modelos de texto. Leia-o inteiro antes
  de escrever qualquer mensagem: ele muda e é por ele que o revisor confere;
- **esta skill** ensina o como: o navegador e a ordem das chamadas.

Nada vai ao celular do Matheus para aprovar. Todo texto passa pelo revisor; reprovado volta com "REESCREVA" e o
motivo: corrija exatamente isso e proponha de novo (até 3 versões por perfil e tipo no dia).

## Regras que nunca mudam

- **Quem envia** é sempre **@raiz.connect**, nunca a conta pessoal @cardosomatheus1.
- **Só execute o que `proxima` entregar**, com o texto EXATO. Nada fora dela, nada a mais.
- **Bloqueio ou verificação** ("tente mais tarde", "ação bloqueada", "suspeita de automação", código, selfie,
  "confirme que é você", captcha): não resolva e pare tudo. Chame `resultado` com bloqueio: true (com o `acao_id` se
  havia ação em andamento; sem ele, se apareceu lendo o Direct) e termine com "PRECISA DE VOCÊ: o Instagram pediu
  verificação". A prospecção pausa 48 h.
- **"http 429"** numa busca, avaliação ou conferência é o aviso de limite da nossa conta: chame `limite_consulta` na
  hora. Nenhuma consulta pelo Instagram até o dia seguinte; **não abra perfis um a um para compensar**. Termine com o
  que não usa o Instagram e escreva no fim "CONSULTA LIMITADA (429)".
- **Leia a página:** abrir uma página não traz o texto dela. Depois de navegar, leia o conteúdo (`browser` content,
  ou `list` com include_content true) e decida só pelo que leu.
- **Nunca apague mensagem** (desfazer envio) sem ordem explícita do Matheus. Se uma foi apagada por ordem dele,
  registre com `apagada` (acao_id, detalhe).
- **Contato só pelo Instagram.** Nunca por WhatsApp, e-mail ou telefone, mesmo que a fonte traga esses dados.
- **Tentativas têm fim:** script de digitar, no máximo 2 vezes por ação; texto no revisor, no máximo 3 versões.
  Depois disso, registre a falha e siga.

## As rodadas

| Rodada | Quando (Bahia) | Roteiro |
|---|---|---|
| 🎯 buscar | 9h23 e 14h23 | seção 4 (propor o que é devido) e seções 2 e 3 (repor o estoque) |
| 🎯 executar | 8 e 38 de cada hora, das 9h às 19h | seção 1, seção 6 + `conferido`, seção 5 (`proxima` até 3 ações feitas ou "NADA AGORA") |
| 🎯 resumo do dia | 20h17 | `prospeccao` acao "hoje" |

**Fim de rodada:** responda exatamente **SEM NOVIDADE** (as respostas de pessoas já chegam ao Matheus pela
ferramenta, e o que foi feito vai no resumo das 20h17). Só se houve bloqueio, verificação ou erro que impediu a
rodada: "PRECISA DE VOCÊ:" e 1 a 3 linhas só sobre isso. Depois de um 429: "CONSULTA LIMITADA (429)".

## 1. Conta certa

1. Abra https://www.instagram.com/accounts/edit/. O campo de nome de usuário mostra a conta ATIVA.
2. Se não for `raiz.connect`: em https://www.instagram.com/, abra "Mais" (≡) ou a foto do perfil → **Trocar de
   conta** → `raiz.connect` (já está adicionada, não pede senha). Confira de novo em /accounts/edit/.
3. Se `raiz.connect` não aparecer, ou pedir senha ou código: pare com "PRECISA DE VOCÊ: a conta da Raiz saiu do
   navegador".

## 2. Achar leads (rodada de busca)

O `contexto` mostra o estoque de leads prontos (alvo 100), dividido por fonte, e quanto falta em cada parte.
**Prefira sempre o que não usa a nossa conta**; script no navegador é o último recurso, com teto diário (a ferramenta
conta e avisa).

1. **Planilha e catálogo:** `fontes` (`limite` 20), de novo até a ferramenta dizer que a parte encheu ou a fila
   acabou. Ela acha o Instagram de cada empresa sozinha e registra com nota.
2. **Parte do Instagram:** `fontes_instagram` (Apify: busca e confere perfis sem usar a nossa conta), de novo até a
   parte encher ou a ferramenta avisar a verba do mês.
3. **Sem Apify, e só se a ferramenta deixar:** `buscar_script` com até 3 buscas de segmento e cidade (ex.:
   "marmita fit bh", "confeitaria recife") → rode o script com `browser` action "evaluate" numa aba em
   https://www.instagram.com/ → passe o JSON inteiro para `perfis_script` (`achados`) e siga a seção 3. Sem @ novos,
   troque os termos. Não abra post por post para descobrir o autor.
4. **Conferir o estoque** (leads achados fora do Instagram): `conferir_estoque` (usa a API oficial ou o Apify quando
   há; senão devolve um script: rode com "evaluate" e passe o texto para `conferidos`). No máximo 3 vezes por rodada.
   "Nada a conferir", pausa ou teto: pare esta parte.

## 3. Avaliar (você coleta evidência; a nota é da ferramenta)

1. Tente `avaliar_api` com `achados`. Sem a API, rode o script de `perfis_script` com "evaluate" (5 perfis por vez) e
   passe o JSON inteiro para `avaliar_perfis`. Ela registra os que encaixam, recusa os que não encaixam e devolve em
   "conferir" só os que não dizem cidade ou segmento.
2. Para os de "conferir": abra o perfil, descubra o que falta e use `registrar` (com o item como base) ou `rejeitar`.
3. Posts fixados (alfinete) aparecem primeiro e podem ser antigos: o "mais recente" é o primeiro NÃO fixado; confira
   a data abrindo o post.

## 4. Propor (rodada de busca)

Tudo numa só chamada: `prospeccao` acao "propor" com a lista de {lead_id, tipo, texto, variante, base}. O `lead_id`
pode ser o id ou o @. Em `base`, o que você viu e onde (post e data), ou "achado em fontes". O `contexto` lista quem
"deve receber" cada tipo agora; os textos seguem os modelos do playbook (seção 7).

- **aquecer:** leads novos, maiores notas primeiro. Leads das fontes ainda não tiveram os posts vistos: proponha sem
  texto (o comentário é escrito na visita, seção 5).
- **dm_abertura:** abra o perfil, veja os 3 posts mais recentes NÃO fixados e escreva pela variante A ou B, citando
  UMA coisa concreta e verdadeira que você viu agora.
- **dm_lembrete:** só aparece para quem segue a Raiz ou interagiu; sem link (ofereça mandar).
- **seguimento:** uma vez, 2 dias depois do link, para quem não escreveu mais; sem link.
- **resposta:** a rodada de execução propõe (seção 6), logo depois de registrar a fala.

## 5. Executar (rodada de execução, uma ação por vez)

Depois da seção 6 e do `conferido`: `prospeccao` acao "proxima" com `conta_ativa` = o @ ativo agora. A ação que ela
entrega é só desta rodada. "ESPERE": aguarde até o horário dito e chame de novo. "NADA AGORA" ou 3 ações feitas:
termine.

**"CONFIRA ANTES DE QUALQUER ENVIO"**: uma rodada anterior pegou essa ação e não registrou o resultado; ela pode ter
saído. Só olhe a tela (a conversa ou o botão «Seguindo») e chame `resultado` com o que viu. Não envie nem refaça.

**Aquecer: seguir, curtir e comentar**
1. Abra o perfil (link na ação).
2. **"ANTES DE SEGUIR"** (lead das fontes): confira que o perfil é mesmo do negócio indicado, a data do primeiro post
   NÃO fixado (até 30 dias) e os seguidores (de 300 a 50 mil). Se falhar: não siga nem curta; chame `etapa` com o
   `lead_id` da ação, etapa "descartado" e a nota ("parado há N dias", "perfil de outro negócio" ou "N seguidores").
   Isso encerra a visita; chame `proxima` de novo (a vaga do dia é reposta).
3. **Seguir:** botão "Seguir" ("Seguindo" já está ok). **Curtir:** 1 ou 2 posts recentes.
4. **Comentário escrito na visita** (ação sem texto): abra o primeiro post NÃO fixado e leia do que trata. Se houver
   algo genuíno a dizer (seção 7 do playbook), chame `comentar` (acao_id, texto, base = o post e a data) ANTES do
   `resultado`. Só publique com **COMENTÁRIO APROVADO** e depois chame `comentado` (ok, detalhe). "REESCREVA": uma
   nova versão pelo motivo. Reprovado duas vezes ou "NÃO COMENTE": só siga e curta.
5. **Publicar o comentário:** abra o link do post (`https://www.instagram.com/p/<código>/`), clique em "Adicione um
   comentário…", digite o texto EXATO, **Publicar** e confira que ele aparece.
6. `resultado` ok=true se SEGUIU, mesmo que o comentário falhe; no detalhe, o que saiu e o que não saiu.

**Mandar no Direct** (primeira mensagem, lembrete, seguimento, resposta, parceiro)
1. Abra sempre pelo perfil: https://www.instagram.com/<@>/ → **Mensagem** (abre a conversa existente ou uma nova).
   Botão "Mensagem" parecendo desativado: a página costuma estar carregando; espere 5 s, leia de novo e clique mesmo
   assim; se não abrir, recarregue UMA vez.
2. **Leia a conversa antes de digitar.** Não envie e chame `resultado` ok=false com o que viu se: a última mensagem é
   da pessoa (trate pela seção 6); há uma conversa anterior que a ação não previa; é lembrete ou seguimento e a nossa
   mensagem anterior não aparece; ou o Instagram não deixa mandar (conta que só recebe de quem ela segue, solicitação
   ainda não aceita). Não tente de novo hoje.
3. **Não digite à mão.** Clique no campo e aperte **Control+A** e depois **Backspace** (ações press do browser): isso
   apaga rascunho de tentativa anterior. Depois rode o script "PARA DIGITAR NO DIRECT" que a `proxima` traz, com
   `browser` "evaluate".
4. Só aperte Enter/Enviar se o script devolver **OK**. "CAMPO NÃO ESTÁ VAZIO": repita o passo 3 (no máximo 2 vezes
   no total). Outra resposta: não envie; `resultado` ok=false.
5. **Confira:** a sua última mensagem aparece UMA vez, igual à aprovada.
6. `resultado` só DEPOIS de conferir. Depois do `resultado`, não toque mais nessa conversa: ação dada como falha nunca
   é enviada depois.

## 6. Ler respostas (toda rodada de execução, antes de agir)

1. **Direct:**
   - toda rodada: veja o número de não lidas no ícone de Mensagens e https://www.instagram.com/direct/requests/;
     abra (perfil → Mensagem) só as conversas com mensagem nova ou com notificação;
   - quando o `contexto` disser **VARREDURA COMPLETA**: abra cada conversa listada e leia; se a ÚLTIMA mensagem é da
     pessoa, é resposta. Depois, `conferido` com varredura: true;
   - a caixa de entrada (/direct/inbox/) não mostra a lista como texto: nunca conclua "sem resposta" por ela.
2. **Notificações** (https://www.instagram.com/accounts/activity/): "respondeu ao seu comentário", "mencionou você",
   "começou a seguir você", curtidas.
3. **Resposta automática não é resposta** ("Automation powered by Manychat", "já já entraremos em contato",
   "recebemos sua mensagem" segundos depois da nossa): não registre nem responda; anote só no `conferido`.
4. **Para cada @ do registro que falou:**
   - **resposta ao nosso comentário:** `etapa` com etapa "respondeu", `onde` "comentario" e a `nota` (o que disse). A
     ferramenta registra como **interação** (prioridade na 1ª mensagem, sem resposta no Direct). Só se a pessoa
     falou de preço, custo, lucro ou do sistema, passe também negocio: true;
   - **no Direct:** `etapa` pelo que a pessoa disse ("respondeu", "lead", "demo" ou "descartado", playbook seção 7),
     `nota` = o que disse, `onde` "direct". O Matheus é avisado na hora. Depois proponha a `resposta` pelo playbook;
     áudio, foto ou figurinha: etapa "respondeu", nota "mandou áudio", e não proponha resposta.
5. **`conferido`** com `direct` (quantas conversas com mensagem nova e de quem), `notificacoes` (as primeiras linhas
   copiadas da página), `interagiram` (os @ do registro que seguiram de volta, curtiram ou comentaram) e `varredura`
   (true só depois da varredura completa). Sem `conferido`, `proxima` não libera nada.

## 7. Caminho do lead

novo → (aquecer) → aquecido → (1ª mensagem, 2+ dias) → abordado → (lembrete, 3+ dias, só quem interagiu) → lembrado →
(5 dias) → sem_resposta. Quem não interagiu não recebe lembrete: fecha sem resposta no mesmo prazo.
Falou de negócio ou no Direct: respondeu → lead → demo → teste → cliente. Disse não: descartado.

## 8. Pedidos avulsos do Matheus

- **"Acha N leads de Y":** seção 2 até criar N leads que encaixam (respeitando o teto de consultas); depois proponha
  «aquecer» para eles (se a cota do dia acabou, ficam para amanhã).
- **"Responde fulano" / "o que ele disse?":** seção 6 para esse @ e depois a resposta pelo playbook.
- **"Como está a prospecção?":** `hoje` (o dia) ou `metricas` (os números).
- **"Me manda o cartão do @x":** `cartao`.
- **"Deixa que eu falo com @x" / "pode voltar a falar com @x":** `assumir` / `devolver`.
- **"Pode voltar a consultar"** (depois de 2 dias de 429): `liberar_consultas`.
- **"Importa esta lista":** salve como .json com nome novo em /a0/usr/prospeccao/ (ex.:
  importar_AAAAMMDD_origem.json; campos nome, cidade, uf, segmento, telefone, instagram, site, evidencia, fonte) e
  chame `importar_lista` com `arquivo`; depois `fontes` transforma a lista em leads.

---
name: prospeccao-instagram
description: "Prospectar clientes da Raiz Connect no Instagram pela conta @raiz.connect: achar e avaliar perfis, aquecer (seguir, curtir, comentar), mandar e responder mensagens no Direct, ler notificações e respostas, com a ferramenta prospeccao. Vale para as rodadas agendadas e para pedidos avulsos do Matheus."
version: 1.0.0
tags: ["instagram", "prospecção", "prospeccao", "raiz connect", "leads", "direct", "dm", "comentário"]
trigger_patterns:
  - "prospec"
  - "instagram"
  - "raiz.connect"
  - "lead"
  - "direct"
  - "marmitaria"
  - "confeitaria"
---

# Prospecção no Instagram — Raiz Connect

Quem decide O QUÊ é a ferramenta `prospeccao` (limites, nota do lead, sequência, revisor, aprovações). Esta skill
ensina o COMO no Instagram. Leia o playbook (`prospeccao` acao "playbook") antes de escrever qualquer texto.

## Regras que nunca mudam

- Quem ENVIA (a conta ativa) é sempre **@raiz.connect**, nunca a pessoal @cardosomatheus1. O DESTINATÁRIO é o @ da
  ação aprovada — pode ser qualquer lead do registro, inclusive o perfil pessoal do Matheus quando ele pede um teste.
  Toda ação passa antes por "a conta certa" (seção 1).
- Só executa o que a ferramenta entregar em `proxima`, com o texto EXATO. Nada fora dela, nada a mais.
- Respostas a quem escreveu e mensagens a parceiros: sempre com o ✅ do Matheus (a ferramenta manda pro celular).
- Bloqueio, limite, "tente mais tarde", verificação ou "suspeita de automação": PARE e informe com
  `resultado` (bloqueio: true). Captcha: nunca resolva — pare e diga "PRECISA DE VOCÊ".
- Abrir uma página NÃO traz o texto dela: depois de navegar, leia o conteúdo (`browser` content, ou `list` com
  include_content true). Decida só pelo que leu.

## 1. Conferir e trocar a conta

1. Abra https://www.instagram.com/accounts/edit/ — o campo de nome de usuário mostra a conta ATIVA.
2. Se não for `raiz.connect`: https://www.instagram.com/ → "Mais" (≡) ou a foto do perfil → **Trocar de conta** →
   `raiz.connect` (já está adicionada; não pede senha). Confira de novo em /accounts/edit/.
3. Se `raiz.connect` não aparecer na troca, ou pedir senha/código: pare — "PRECISA DE VOCÊ: a conta da Raiz saiu
   do navegador".

## 2. Achar perfis (rápido: por script)

1. `prospeccao` acao "buscar_script" com `termos` = até 3 buscas da região e do segmento (ex.: "marmita salvador",
   "marmitaria salvador", "marmita fit salvador", "congelados salvador", "quentinha salvador").
2. Rode o script com `browser` action "evaluate" numa aba em https://www.instagram.com/ → JSON com os @ achados.
3. Passe esse JSON para `perfis_script` (`achados` = o texto): a ferramenta tira os conhecidos e rejeitados e devolve
   o script de avaliação (seção 3).
4. Não abra posts um por um para descobrir o autor. Se a busca não trouxer @ novos, troque os termos.
   Só se o script falhar (erro http), use a busca da tela: https://www.instagram.com/explore/search/keyword/?q=<termo>.

## 3. Avaliar perfis

**Primeiro tente a API oficial:** `prospeccao` acao "avaliar_api" com `achados` = o JSON da seção 2. Ela avalia todos
pela API da Meta (sem navegador, sem o limite 429) e já registra/recusa. Só se ela disser que a API não está
configurada, use o script do navegador abaixo.

### Pelo navegador (plano B: vários de uma vez)

1. Da seção 2 você já recebeu o script de avaliação (ou chame `perfis_script` com `leads` = até 15 @).
2. Os @ já conhecidos e rejeitados ficam de fora automaticamente.
3. Numa aba aberta em https://www.instagram.com/ (conta @raiz.connect), rode o script com `browser` action
   "evaluate" (`script` = o texto). Leva ~2 s por perfil e devolve um JSON com seguidores, bio, link, categoria e os
   últimos posts (data e se é fixado).
4. `prospeccao` acao "avaliar_perfis" com `dados` = esse JSON inteiro. A ferramenta registra com nota os que
   encaixam, recusa os que não encaixam (parado, privado, grande/pequeno demais, franquia, curso…) e devolve em
   "conferir" só os que não dizem cidade ou segmento na bio.
5. Só para os de "conferir": abra o perfil, descubra o que falta e registre com `registrar` (usando o item como
   base) ou `rejeitar`.
6. Não abra um por um os perfis que a ferramenta já resolveu.

Os scripts têm de terminar em 30 s: a busca usa até 3 termos e a avaliação 5 perfis por vez (a ferramenta já corta).
**"http 429" = o Instagram limitou as consultas: NÃO insista.** Pare os scripts de perfil por 10 minutos; se precisar
seguir, avalie abrindo os perfis um a um (método antigo): segmento, cidade, seguidores, data do primeiro post NÃO fixado, canais, sinais,
cardápio, link de pedido, exclusões e do que trata o último post.

## 4. Executar as ações liberadas

Antes da primeira: confira as respostas (seção 5) e registre `conferido`. Depois `proxima` com
`conta_ativa` = o @ ativo agora. Para cada ação:

- **Aquecer:** abra o perfil; **Seguir** (se o botão já diz "Seguindo", ok); curta 1–2 posts recentes (o ícone vira
  "Descurtir"/"Unlike"). Comentário, se houver texto: pegue o link do primeiro post NÃO fixado
  (`https://www.instagram.com/p/<código>/`), abra esse link, clique em "Adicione um comentário…", digite o texto
  exato e clique em **Publicar**; confira que o comentário aparece na lista. `ok=true` se seguiu, mesmo que o
  comentário falhe — diga no detalhe o que saiu e o que não saiu.
- **Primeira mensagem / parceiro:** perfil → **Mensagem** → texto exato → enviar; confira que aparece enviada.
- **Lembrete / resposta:** abra a conversa no Direct (https://www.instagram.com/direct/inbox/); se não houver
  conversa (a pessoa respondeu num comentário), perfil → **Mensagem**. Texto exato → enviar → conferir.
- Depois de cada uma: `resultado` (acao_id, ok, detalhe = o que apareceu na tela). Espere 3 minutos antes da
  próxima. No máximo 3 ações por rodada.

## 5. Ler respostas (sempre antes de executar)

1. **Direct:** https://www.instagram.com/direct/inbox/ — conversas com mensagem nova (inclusive "Solicitações").
2. **Notificações:** https://www.instagram.com/accounts/activity/ (ou o coração "Notificações" no menu) — procure
   "respondeu ao seu comentário", "mencionou você", "replied to your comment", "mentioned you". Curtida não é
   resposta.
3. Para cada @ do registro que respondeu: `etapa` ("respondeu" | "lead" | "descartado") com `nota` = o que disse e
   `onde` ("direct" | "comentario") — o Matheus é avisado na hora, uma vez por resposta. Proponha a `resposta`
   (curta, humana; se a conversa chegou em preço/custo, ofereça a calculadora ou fazer a conta com a receita;
   se mandou receita, faça o cálculo de verdade).
4. Registre `conferido` com `direct` (quantas conversas novas e de quem), `notificacoes` (as primeiras linhas
   copiadas da página) e `interagiram` (os @ do registro que seguiram de volta, curtiram ou comentaram).

## Pedidos avulsos do Matheus

- "Prospecta N X / acha N leads de Y": N é o número de leads que ENCAIXAM (criados pela ferramenta), não de perfis
  abertos. Siga as seções 2 e 3 trocando de termo até criar N leads ou examinar 30 perfis; registre os que não
  encaixam como rejeitados; proponha `aquecer` para os criados (se a cota do dia acabou, eles ficam para amanhã).
- "Responde fulano / o que ele disse?": seção 5 para esse @; proponha a resposta (vai pro ✅ dele).
- "Como está a prospecção?": `prospeccao` acao "hoje" (dia) ou "metricas" (semana).

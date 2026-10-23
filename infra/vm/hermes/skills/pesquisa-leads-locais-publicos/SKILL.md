---
name: pesquisa-leads-locais-publicos
description: "Achar N negócios locais (marmitarias, comida congelada e similares) numa cidade com Instagram ativo, usando só páginas públicas, e gravar um CSV com nome, @, bairro, o que vendem e o link de origem."
version: 1.0.1
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-23
tags: ["aprendizado"]
trigger_patterns:
  - "leads em Salvador"
  - "achar negócios"
  - "marmita"
  - "comida congelada"
  - "instagram ativo"
  - "só páginas públicas"
  - "leads_salvador.csv"
  - "lista de leads csv"
---

# Lista de leads locais a partir de páginas públicas (CSV)

Vale para pedidos como "ache N negócios de X na cidade Y com Instagram ativo, só em páginas públicas, e grave um CSV". É só pesquisa e leitura: não envia mensagem, não segue, não curte, não comenta. Para aquecer ou enviar depois, use prospeccao-instagram. Para redigir a primeira mensagem, use prospeccao-rascunho-primeiras-mensagens.

## Fluxo
1. **Registre os passos no `todo_list`** (buscar candidatos, verificar cada um, gravar CSV, conferir) e crie a pasta de saída pedida.
2. **Levante candidatos por três caminhos.** Junte mais candidatos do que o pedido, porque vários caem na verificação.
   - Google Maps (`browser_navigate` em `google.com/maps/search/<termo>+<cidade>`): dá nome, bairro/rua, categoria e se está aberto ou fechado. Pegue o bairro daqui ou do site do negócio.
   - `web_search` com termo simples, ex.: `marmita congelada <cidade> instagram`. Não use OR nem aspas aninhadas, que trazem lixo (YouTube, Wikipedia, fóruns). Leia só os resultados do domínio do negócio ou do Instagram.
   - Dentro de um perfil já aberto, os blocos **"Followed by"** e **"Similar accounts"**, e o link do site na bio, mostram outros @ do mesmo nicho. É a fonte mais rica de candidatos.
3. **Verifique cada candidato abrindo o perfil** (`browser_navigate` em `instagram.com/<handle>/`, depois `browser_snapshot` com full=true). Registre só o que o snapshot mostrou:
   - O @ exato da página aberta. Se a página abriu em outro @ ou deu "this page isn't available", o candidato não vale e o @ não pode ser chutado.
   - Nome, seguidores, nº de posts, bio (o que vendem, cidade, bairro, site).
   - **"Ativo" = post recente.** Os snapshots das grades não trazem datas. Abra o post mais recente e leia a data; sem isso, não escreva "ativo". Poucos posts e poucos seguidores (ex.: 4 posts, 27 seguidores) são sinal de perfil novo ou abandonado: marque como fraco, não como ativo.
   - Confirme que é da cidade pedida (bio, Maps, site). Perfil de outra cidade com nome parecido sai da lista.
4. **Bairro:** tire da bio, do Maps ou do site do negócio. Se não achar nas duas primeiras tentativas, deixe "não confirmado" e escreva só a cidade. Não deduza bairro.
5. **Se faltar candidato confirmado, continue buscando** (outro termo, mais um perfil "Similar accounts") antes de fechar. Se mesmo assim não chegar ao número pedido, entregue só os confirmados e diga quantos faltam. Nunca complete a lista com @ não abertos.
6. **Grave o CSV com Python (`csv`) no `execute_code`** ou com heredoc no `terminal`, com vírgulas dentro de campo entre aspas. Colunas: `nome,instagram,bairro,o_que_vendem,link_fonte,verificacao`.
   - `link_fonte` é a página onde o dado foi lido, e o @ da coluna `instagram` tem que bater com ela.
   - `verificacao` diz o que foi visto (ex.: "perfil aberto, último post <data>, bairro pelo Maps" ou "perfil aberto, sem data de post").
7. **Releia o arquivo** (`wc -l`, `cat` no `terminal`) e compare cada @ e cada link com o que foi aberto.
8. **Resposta curta:** quantos entraram, quantos foram confirmados por completo (@ aberto, ativo, bairro), o que foi decidido sozinho, o caminho do arquivo.

## Armadilhas
- **Só diga "conferi cada perfil" se abriu cada um.** Uma linha com @ montado a partir do nome do negócio, sem abrir o perfil, é dado inventado e derruba a confiança na lista inteira. Handles tentados que não existem (ex.: variações com "gastronomia") não entram.
- **Não declare o que o snapshot não mostrou:** "perfil verificado", "ativo" e "mais de 10 anos" só valem se estiverem na página aberta.
- **Não use a sessão do Instagram para nada além de ver páginas públicas.** O navegador pode estar logado na conta da própria marca. Não siga, não curta, não abra mensagens, não clique em "Message" nem em "Follow". Diga na resposta que o perfil foi lido pela sessão do navegador, em vez de afirmar que não houve login.
- **A busca interna do Instagram (`/explore/search/keyword/?q=`) volta vazia** sem interação. Vá direto ao handle, ou ao Maps e ao site para descobri-lo.
- **Muitos "bairro não especificado" é sinal de que a pesquisa parou cedo.** Faça ao menos uma passada no Maps e no site para os candidatos sem bairro antes de gravar.
- **Não use resultados de página adulta, fórum ou nicho alheio** que apareçam na busca como fonte; descarte e refaça a busca com outro termo.
- Se o pedido proíbe perguntar, decida e registre a decisão na resposta e, se couber, na coluna `verificacao`.

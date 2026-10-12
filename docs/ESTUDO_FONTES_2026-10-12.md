# Estudo das fontes de leads — 12/10/2026

Avalia cada forma de achar leads para a prospecção da Raiz Connect: o que dá, quanto custa, quanto rendeu (ou deve
render), o risco e o veredito.

Base do estudo:

- os números reais da prospecção até hoje;
- a planilha completa do Grok (4.342 empresas), analisada linha a linha;
- uma pesquisa de preços e regras feita hoje nas páginas oficiais (Apify, Meta, Tavily, Receita Federal e outras).

> Lembrete da regra: o contato é **só pelo Instagram** (seguir, curtir, comentar e mandar a DM pela @raiz.connect).
> WhatsApp não é usado para abordar. Por isso só serve fonte que leve ao **@ de um perfil ativo**.

---

## Resumo em 1 minuto

- **O que os números mostram (28 dias):**
  - **Leads achados no próprio Instagram:** 14 leads, 13 aquecidos, **nenhum descartado** na visita e as **2
    respostas** que tivemos (Zen e Anna).
  - **Leads da planilha do Grok:** 77 leads, 15 visitados, **73% descartados** na visita (parado 6, privado ou outro
    negócio 3, grande demais 2) e nenhuma resposta ainda.
  - **Catálogo de CNPJ (GuiaPJ):** de 100 empresas examinadas, só **2** viraram lead.
- **Por quê:** a planilha foi montada para **WhatsApp**. Todas as 4.342 empresas têm WhatsApp, mas só **192 (4%)**
  têm o @ e **531 (12%)** têm site. A busca acha o perfil de metade delas, e muitos estão parados.
- **Decisão (já no ar):**
  - as fontes foram **divididas**: o estoque de 100 é repartido entre planilha (60), Instagram (30) e catálogo (10);
  - as visitas **alternam** as fontes, e o resumo mostra o rendimento de cada uma;
  - a planilha inteira foi importada, com prioridade A+ → C;
  - o @ é procurado primeiro **no site da empresa**, que é de graça;
  - os perfis passam por uma **pré-checagem** (ativo, tamanho e se é privado) **antes da visita**.
- **Próximo passo de maior efeito: Apify**, por cerca de **US$ 19 por mês**.
  - **Descoberta:** acha perfis direto no Instagram por palavra + cidade (ex.: "marmitaria campinas"), já com
    seguidores e posts. Não usa a nossa conta, então a @raiz.connect não corre risco.
  - **Conferência:** confere os perfis da planilha em lote, sem gastar visita.
- **Grátis e oficial:** a API da Meta (Business Discovery) confere atividade e seguidores sem custo. Falta só um token
  com 3 permissões; o código para usá-la já existe.

---

## 1. O que cada fonte rendeu até hoje

| Fonte | Leads | Visitados | Descartados na visita | Aquecidos | Responderam | Custo |
|---|---|---|---|---|---|---|
| Instagram (busca do agente) | 14 | 13 | 0 | 13 | **2** | grátis (mas leva 429 se exagerar) |
| Planilha do Grok | 77 | 15 | **11 (73%)** | 4 | 0 | grátis; a busca do @ gasta Tavily |
| Catálogo (GuiaPJ) | 2 | 0 | — | 0 | 0 | grátis; a busca do @ gasta Tavily |

**Achar o @ das empresas da planilha** (as 256 importadas em 11/10, da Bahia):

- 154 procuradas;
- **87 perfis achados (56%)**;
- 67 sem Instagram.

**Por que os perfis da planilha caíram na visita:**

- parado há mais de 30 dias: 6;
- privado, indisponível ou outro negócio: 3;
- grande demais (72 mil e 704 mil seguidores): 2.

> Ainda é pouco para comparar respostas: nenhuma primeira DM saiu até hoje de manhã. A comparação justa vem com pelo
> menos 15 abordados por fonte (o relatório de segunda já mostra o funil por fonte).

---

## 2. A planilha do Grok (4.342 empresas)

**O que tem:**

- **Segmentos:** marmitas e alimentação 3.434; salgados 479; confeitaria 429.
- **Prioridade:**
  - A+ 267 e A 406 (673 no total);
  - B 715;
  - C 2.954.
- **Estados:** BA 687, PE 380, GO 336, CE 305, RS 304, SP 297, MG 264, ES 255… o Brasil todo.
- **Contato:**
  - WhatsApp em todas (911 confirmados, 3.431 "celular público");
  - @ do Instagram em **192**;
  - site em **531**.
- **Já contatadas pelo WhatsApp** (teste de 17/09): 10. Ficaram de fora, para não abordar duas vezes.

**Como o Grok achou as empresas** (os "métodos" dele):

| Método | Empresas | Qualidade (prioridade) |
|---|---|---|
| Solutudo (guia de empresas por categoria e cidade) | 3.118 (72%) | 87% são C |
| GuiaPJ / Receita Federal (CNPJ com celular) | 455 | 36% são A+ ou A; 40% B |
| Site oficial da empresa | 343 | **73% são A+ ou A**; 73 já com @ |
| Ueni (sites de pequenos negócios) | 96 | B e C |
| Outros (Casa dos Dados, MestreGeo, Telelistas, Apontador, RestaurantGuru, Prefiro Delivery, jornais, LinkedIn…) | ~330 | variado |

**Como passamos a consumir a planilha** (no ar desde hoje):

1. Primeiro as empresas que **já têm @** (192), porque não gastam busca.
2. Depois as que têm **site**: o agente lê a página e pega o link do Instagram. É de graça e preciso. Links do próprio
   construtor do site (Ueni, Wix, iFood…) são ignorados.
3. Depois as outras, pela prioridade (A+, A, B, C), com a busca paga (Tavily, teto de 100 consultas por dia).
4. Todo perfil achado passa pela **pré-checagem** antes da vez dele. O que estiver parado, grande ou pequeno demais,
   ou privado, sai do estoque sem gastar visita. Na visita, o agente só confere se é o negócio certo.

**O que esperar:** com a busca a ~2 consultas por empresa e o teto de 100 por dia, são ~50 empresas por dia. As 4.342
levariam meses e, pelo que vimos, uns 3 em cada 4 perfis achados cairiam na conferência. A planilha vale como
**volume de fundo**, priorizada (A+ e A primeiro), e não como a fonte principal.

---

## 3. Cada fonte avaliada

| Fonte | O que dá | Custo (out/2026) | Rendimento | Risco | Veredito |
|---|---|---|---|---|---|
| **Busca no Instagram pelo agente** (navegador logado) | perfis ativos, com posts e seguidores | grátis | o melhor até agora (0 descartes, 2 respostas) | o Instagram limita (429) se exagerar | **Manter** na parte do Instagram, em volume pequeno |
| **Apify — Instagram Search Scraper** | perfis por palavra + cidade (até 250 por busca), com seguidores, categoria e os 12 últimos posts | US$ 2,70 por mil (grátis) · US$ 2,30 (Starter) | deve ser parecido com a busca do agente (mesma origem) | **não usa a nossa conta**: zero risco para a @raiz.connect | **Adotar** como descoberta principal da parte do Instagram |
| **Apify — Instagram Profile Scraper** | dados de um @ conhecido: seguidores, privado, posts com data e "fixado" | US$ 2,60 por mil (grátis) · US$ 2,30 (Starter) | resolve a conferência da planilha | idem (sem login) | **Adotar** para a conferência quando a API da Meta não responder |
| **API da Meta (Business Discovery)** | seguidores, nº de posts e datas dos posts de contas comerciais | **grátis**, ~200 consultas por hora | resolve a conferência de contas comerciais (não de contas pessoais) | oficial (zero risco) | **Adotar** como conferência principal; o código já existe e falta o token |
| Apify — Instagram Hashtag Scraper | posts de uma hashtag (#marmitascampinas), sem seguidores | US$ 2,60 por mil | bom para achar nomes; precisa conferir depois | sem login | Complemento |
| Apify — Google Maps Scraper | negócios do Maps por cidade; o @ só quando o site é o Instagram (+ US$ 2 por mil para ler o site) | US$ 4 por mil (grátis) · US$ 3 (Starter) | produtor caseiro muitas vezes nem está no Maps | sem login | Só para completar cidades fracas |
| **Site da empresa** (nosso, novo) | o @ linkado no site | grátis | 531 empresas da planilha têm site | nenhum | **No ar** |
| Planilha do Grok | 4.342 empresas com WhatsApp; 192 com @ | já feita | 56% acham o @; 73% caíam na visita (agora há conferência antes) | nenhum | **No ar**, como volume de fundo, A+ e A primeiro |
| Tavily (busca na internet) | acha o @ por nome + cidade | 1.000 grátis por mês; depois US$ 0,008 por consulta (~US$ 16/mês no nosso ritmo) | ~56% | nenhum | Manter enquanto houver planilha; **Serper sai pela metade** (US$ 1 por mil) |
| Catálogo GuiaPJ / Receita | empresas por CNAE e cidade, com telefone | grátis | 2% viram lead | nenhum | Manter só nos 10% do estoque |
| Dados abertos da Receita (base inteira) | todas as empresas por CNAE e cidade, com telefone e e-mail; **sem Instagram** | grátis (5,4 GB por mês) | precisaria da busca para cada uma | nenhum | Não vale agora: rende como o catálogo |
| Casa dos Dados | o mesmo que a Receita, com filtros | ~R$ 0,01 por CNPJ | idem | nenhum | Não |
| Google Places (API oficial) | lugares do Maps; **sem redes sociais**; proíbe guardar a lista | US$ 32–35 por mil | baixo | contrato | Não |
| iFood, Rappi, 99Food | lojas de delivery | — | sem Instagram na listagem | **os termos proíbem raspar** (o da Rappi é explícito) | Não (no máximo, olhar à mão) |
| Solutudo (direto) | o que o Grok já trouxe | — | raramente tem Instagram | bloqueia robôs | Não (já temos os dados pela planilha) |

---

## 4. Divisão recomendada e o caminho de cada lead

```
descoberta ──► achar o @ ──► pré-checagem ──► estoque (por fonte) ──► visita (seguir, curtir, comentar) ──► DM
 Instagram      já vem         API Meta             planilha 60          a vez alterna as fontes         D+2
 planilha       site           ou Apify             instagram 30         (quem interagiu passa na frente)
 catálogo       busca          ou script            catálogo 10
```

- **Hoje:**
  - planilha 60, Instagram 30, catálogo 10;
  - a parte do Instagram é enchida pela busca do agente;
  - a pré-checagem usa o script do navegador, 5 perfis por vez, no máximo 15 por rodada.
- **Com o Apify:**
  - a parte do Instagram passa a vir do Search Scraper, cerca de 30 perfis novos e já conferidos por dia, sem tocar a
    nossa conta;
  - sugestão de divisão: **planilha 40, Instagram 50, catálogo 10**.
- **Ajuste semanal:** toda segunda, o relatório mostra o funil por fonte. A parte de cada fonte acompanha quem mais
  responde por perfil aquecido, mas só com pelo menos 15 abordados por fonte, para não decidir no acaso.

---

## 5. Custos

**Hoje:**

- Tavily: 100 consultas por dia. Se o plano for o grátis (1.000 por mês), o teto esgota em 10 dias e precisa baixar.
  No pague-pelo-uso, sai cerca de US$ 16 por mês.

**Proposto:**

- **Apify Starter, US$ 19 por mês.** Cobre ~3.000 perfis descobertos e ~1.500 conferências (US$ 7 a 15 de uso).
  Antes, um **piloto no plano grátis** (US$ 5 de crédito): 20 buscas palavra × cidade, por volta de US$ 1. Ele mede
  quantos perfis encaixam e quantos passam na conferência.
- **API da Meta:** grátis.
- **Se a busca por nome continuar:** Serper (~US$ 8 por mês) ou Brave (~US$ 10) saem mais baratos que a Tavily.

---

## 6. Riscos e cuidados

- **Conta da Raiz:**
  - o Apify roda **sem login**, na infraestrutura deles, e nunca usa a @raiz.connect;
  - a API da Meta é o caminho oficial;
  - o script do navegador usa a nossa sessão. Por isso tem pouco volume e pausa sozinho se o Instagram limitar.
- **DM:** a API oficial do Instagram não deixa começar conversa. A primeira mensagem continua feita na tela, em ritmo
  de pessoa (como hoje).
- **Termos da Meta:** proíbem coleta automática sem permissão. O risco de contrato fica com quem raspa (o Apify), e a
  Business Discovery é o caminho permitido.
- **LGPD:** a base é o **interesse legítimo** (dados públicos de negócio, para oferecer algo útil ao próprio negócio).
  O mínimo:
  - quem disser não, nunca mais é contatado (já é regra no código);
  - lista de quem não quer contato;
  - apagar leads descartados depois de um prazo;
  - um texto curto de avaliação do interesse legítimo (eu escrevo).

---

## 7. Feito hoje (no ar, testado)

- **Fontes divididas:**
  - estoque por fonte, configurável;
  - vez alternada entre as fontes;
  - funil por fonte no contexto, no relatório da semana e no resumo do dia.
- **Planilha completa importada:** 4.086 novas e 256 atualizadas com a prioridade. As 10 já contatadas ficaram de fora.
- **Busca do @:** no site da empresa antes da busca paga. O teto da Tavily não trava o que não precisa dela.
- **Pré-checagem do estoque** antes da visita: hoje pelo script do navegador; aceita os dados da API da Meta e do Apify
  no mesmo formato.
- **Correções do dia:**
  - rodadas em dobro;
  - rodada automática pausada pelo detector de repetição (agora é retomada, ou cancelada se repetir);
  - rodada "rodando" depois de reiniciar (volta na hora);
  - descarte na visita pelo id da ação.

---

## 8. Próximos passos (e o que preciso de você)

1. **Apify (decisão sua):**
   - crie um **token novo** em apify.com → Settings → API & Integrations. O antigo, do repositório erp-saas, está
     exposto: não use;
   - mande no Telegram: `/senha APIFY_TOKEN <token>`;
   - eu faço o piloto (~US$ 1 no plano grátis) e, se render, ligo a descoberta e a conferência.
   - Depois disso, o plano Starter (US$ 19 por mês).
2. **API da Meta (Business Discovery):**
   - precisa da @raiz.connect ligada a uma Página do Facebook e de um token com `instagram_basic`,
     `instagram_manage_insights` e `pages_read_engagement`;
   - são uns 10 minutos no Explorador da Graph API;
   - o agente já tem a ação `token_meta`, que lê o token da tela e guarda no cofre sem mostrar.
3. **Tavily:** qual é o plano? Se for o grátis, baixo o teto para 30 por dia. Se for pague-pelo-uso, mantenho ou troco
   pelo Serper.
4. **Divisão do estoque:** fica 60/30/10 até o Apify entrar. Depois, 40/50/10.

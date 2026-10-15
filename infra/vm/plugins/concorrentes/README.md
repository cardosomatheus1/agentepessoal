# concorrentes

Vigia de concorrentes (14/10, a partir da skill `competitor-news-monitor` e do `feed.py` do Hermes Agent, MIT).

- **Lista** (`/a0/usr/concorrentes/lista.json`; até a primeira mudança vale a `SEMENTE` de `helpers/concorrentes.py`):
  cada concorrente com as fontes `site`, `precos`, `blog`, `rss` e `imprensa` (busca do Google Notícias em RSS, sem
  chave). O agente edita pela ferramenta `concorrentes` (adicionar, fonte, tirar_fonte, remover); cada mudança vai para
  `diario.jsonl` e o removido fica em `removidos`.
- **Coleta** (`acao "coletar"`): acha o feed da página (`<link rel=alternate>` e, em blog/rss, os caminhos comuns) e lê
  RSS, Atom ou JSON Feed; blog sem feed vira a lista de links dos posts; página de preços vira o conjunto de valores
  em R$ (ou a assinatura do texto, se não tiver preço legível).
- **Comparação**: com o que cada fonte mostrou na última leitura boa (`estado.json`). A primeira leitura é a base
  (nada dela é "novo"); item com mais de 30 dias nunca é novo.
- **Fato**: o mesmo link ou títulos com a maioria das palavras em comum viram um fato só, com todas as fontes.
- **Sem cobertura**: fonte que falhou não mexe no estado e aparece como "sem cobertura", nunca como "sem notícia".
- Cada rodada fica em `rodadas.jsonl`. A rotina semanal é `infra/vm/rotinas/qt0dNXtu.json` (🔭 Concorrentes — semana,
  quarta 8h23).

## Grupos (15/10)

Cada concorrente tem `grupo`: `direto` (app ou sistema de custo, ficha técnica e preço para quem produz comida),
`gestao` (gestão de food service pequeno que o mesmo cliente poderia usar no lugar: Saipos, Consumer, Goomer, Anota AI,
Cardápio Web, Kyte…) e `conteudo` (perfis, mentorias e cursos que ensinam precificação, custo e gestão a confeiteira,
marmiteiro, salgadeiro: disputam a atenção do mesmo dono de negócio). A régua é o que a Raiz vende (`RAIZ`: sistema de
custo, preço e estoque, "Lucro na Mão em 30 Dias", R$ 197/mês).

## Instagram (15/10)

- Fonte `instagram` (um por concorrente): o @ vira `https://www.instagram.com/<@>/`, sempre em minúsculas (a Business
  Discovery não acha "UseSaipos", só "usesaipos"). Na `SEMENTE`, cada @ foi conferido pela Business Discovery em 15/10
  (campo `conferido`, com os seguidores do dia); quem não tem @ achado diz por quê (campo `instagram`).
- Coleta: **uma chamada por perfil por coleta** (Business Discovery da Graph API, com o acesso da @raiz.connect, que o
  plugin `conteudo` tira do cofre), com `IG_PAUSA` (3 s) entre as chamadas. Se a Meta responder "limite", a coleta para
  de chamar e os perfis que faltam ficam "sem cobertura".
- Retrato: seguidores, total de posts e os últimos 30 posts (formato, curtidas, comentários, views dos reels, data,
  link e o gancho), em `/a0/usr/concorrentes/instagram/<id>.jsonl`, um por linha.
- Análise (conta, sem IA), por perfil, nos 7 e 30 dias antes do retrato: posts por semana, mistura de formatos (reels,
  carrossel, foto), engajamento médio ((curtidas + comentários) ÷ seguidores; post com curtidas ocultas fica fora da
  média), views médias por reel, os 3 melhores posts pelo engajamento e os seguidores ganhos desde o retrato anterior.
  Se os 30 posts couberem na janela, a contagem é um mínimo e o ritmo vem do período que eles cobrem.
- No conjunto (só perfis com 1.000+ seguidores e retrato atual, para conta minúscula não distorcer): o formato que mais
  rende (engajamento do formato ÷ média do próprio perfil, na média dos perfis), os 3 posts da semana com mais
  engajamento, os 5 reels com mais views por seguidor, quem postou mais, quem mais cresceu e com que frequência posta,
  e as medianas por grupo.
- Perfil que falhou (@ errado ou conta pessoal dá "Invalid user id", sem acesso, limite) é "sem cobertura" e não entra
  no conjunto daquela rodada; o retrato velho aparece marcado como antigo.
- A legenda é dado de terceiros: só a 1ª linha é guardada, limpa (sem marcação, aspas ou caracteres invisíveis) e
  cortada em 120 letras, e aparece sempre entre «». Nunca vira instrução.
- **Stories não:** a Meta não libera os stories de outras contas pela API. Não usamos navegador logado nem raspagem
  para isso; o relatório diz que stories ficam sem cobertura.
- Ferramenta: `acao "instagram"` devolve a análise já guardada, sem chamar a Meta (opcional `id` ou `grupo`); serve para
  responder na hora.

## Lista

Lista (pesquisa de 14 e 15/10/2026, URLs em `pesquisa` de cada um), 27 concorrentes, 25 com Instagram:
- direto: ChefPro, Lucro na Confeitaria, Gestão Viver de Confeitaria, Precifica (PediPedi, sem Instagram), DocePreço
  (sem Instagram), Confe.it, Meslo, BakePro, Bakerly, Menu Control, Precific, Preço na Medida;
- gestao: Saipos, Consumer, Goomer, Anota AI, Cardápio Web, Kyte, OlaClick, SisFood, NoxMob;
- conteudo: Vivi Costa, Bella Andrade (Donas de Confeitaria), Richard e Ísis (Jade Doces Finos), Chef Gabi Paludo
  (Marmitaria Lucrativa), Bruna Londono (M100K), Chef Claudia Salgados.

Se a VM já tiver `lista.json` (gravado pelo agente antes desta versão), o operador roda uma vez, depois de implantar,
`atualizar_semente()` com `AUTOR["quem"] = "operador: <motivo>"`: entram os concorrentes e fontes que faltam, o grupo e o
Instagram; nada do que o agente adicionou ou removeu é desfeito. Sem `lista.json`, a semente nova já vale.

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
- Cada rodada fica em `rodadas.jsonl`. A rotina semanal está em `infra/vm/rotinas/concorrentes-semana.json` (ainda
  não criada na VM).

Lista inicial (pesquisa de 14/10/2026, URLs em `pesquisa` de cada um): Saipos, ChefPro, Lucro na Confeitaria, Gestão
Viver de Confeitaria, Precifica (PediPedi) e DocePreço.

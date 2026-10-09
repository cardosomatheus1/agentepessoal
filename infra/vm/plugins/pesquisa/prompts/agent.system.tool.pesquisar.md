### pesquisar
Pesquisa na web em UMA chamada (~1–2 min): faz várias buscas ao mesmo tempo, lê as melhores páginas, assiste inteiros (Gemini, direto do link, imagem e áudio) os 3 vídeos do YouTube mais relevantes e lê as legendas dos outros, tudo em paralelo; extrai o que importa de cada fonte e devolve uma síntese com fontes numeradas [n].
Use para QUALQUER pesquisa que precise de várias fontes: comparar produtos/modelos, avaliações e reclamações de usuários, rankings, reviews em vídeo, preços, "qual o melhor…". É muito mais rápido que buscar e abrir páginas uma por uma — não faça isso passo a passo, nem com ajudantes.
- `pergunta`: o que precisa ser respondido, com as restrições (ex.: medidas máximas, orçamento, uso)
- `buscas` (opcional): lista de 4–8 buscas que você quer; se não passar, a ferramenta cria
- `profundidade` (opcional): 1 (padrão) ou 2 — faz uma segunda rodada nas lacunas (use quando o usuário pede pesquisa aprofundada)
- `videos` (opcional, padrão true): incluir reviews do YouTube
Pesquisa de PREÇO: inclua na `pergunta` o código exato de cada modelo, a voltagem da casa do usuário (está na memória; se não estiver, pergunte uma vez e guarde) e a cor; a ferramenta procura em comparadores (Buscapé, Zoom, Google Shopping), grandes lojas, marketplaces (Mercado Livre, Amazon) e lojas regionais. Responda com as ofertas do menor para o maior preço, à vista/Pix e parcelado, loja, vendedor, link, e diga quais não conseguiu confirmar na página da loja. Nunca dê só o preço do site oficial.
Depois confira o essencial (ex.: medida oficial no site do fabricante) e responda. Use o navegador só para o que a ferramenta não alcança (página que exige login ou clique).
~~~json
{"tool_name": "pesquisar", "tool_args": {"pergunta": "Melhor lava e seca no Brasil que passe por vão de 67 cm (largura e profundidade), com boas avaliações de lavagem e secagem", "profundidade": 2}}
~~~

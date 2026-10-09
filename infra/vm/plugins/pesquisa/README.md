# pesquisa

Ferramenta `pesquisar`: uma chamada faz 5–8 buscas no SearXNG local ao mesmo tempo, lê até 14 páginas
e as legendas de até 4 vídeos do YouTube em paralelo, extrai de cada fonte o que importa (Luna, em
paralelo) e escreve uma síntese com fontes numeradas. `profundidade: 2` faz uma segunda rodada nas lacunas.

Motivo: uma pergunta sobre lava e seca levou 207 chamadas ao modelo e ~18 min com busca e leitura
passo a passo. Notas por fonte e a síntese ficam em `/a0/usr/workdir/pesquisas/<data>/`.

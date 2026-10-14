# pesquisa

Ferramenta `pesquisar`: uma chamada faz 5–8 buscas no SearXNG local ao mesmo tempo, lê até 14 páginas
e as legendas de até 4 vídeos do YouTube em paralelo, extrai de cada fonte o que importa (Luna, em
paralelo) e escreve uma síntese com fontes numeradas. `profundidade: 2` faz uma segunda rodada nas lacunas.

Motivo: uma pergunta sobre lava e seca levou 207 chamadas ao modelo e ~18 min com busca e leitura
passo a passo. Notas por fonte e a síntese ficam em `/a0/usr/workdir/pesquisas/<data>/`.

**Página bloqueada** (14/10): quando o site responde erro (403, 429…) ou uma parede tipo "Just a moment...", a fonte
não some: `helpers/recuperar_pagina.py` (portado do Hermes Agent, MIT) procura uma cópia no Wayback Machine, no
archive.today e no Jina Reader (sem chave; `JINA = False` desliga). A cópia só vale se for de verdade (tamanho mínimo,
sem redirecionamento falso, da mesma página, sem título de parede) e entra na síntese marcada como "cópia arquivada de
<data>" (preço e estoque dela não valem como atuais).

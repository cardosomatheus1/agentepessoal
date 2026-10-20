# Segundo Cérebro (Matheus)

Site só de leitura que mostra a **Pasta** do Segundo Cérebro do Matheus (ADR 0001): assuntos (onde parou), pendências,
decisões, notas do dia, reuniões, contexto (validado ou pendente), perfil, projetos e documentos, com a área de cada item,
os links entre eles e o mapa de conexões. A Pasta é a única fonte e só o agente escreve nela; o site não edita.

- Página: `/segundo-cerebro` (link "Segundo Cérebro" na barra lateral do chat)
- API: `GET /api/segundo-cerebro` (sem parâmetros de consulta)
- Implantar / reverter: `docs/SEGUNDO_CEREBRO_DEPLOY.md`

## Como se entra (contrato de sessão)

No ar, a página fica atrás do Agent Zero, no mesmo endereço do agente. Quem decide é o gateway do plugin
`infra/vm/plugins/segundo_cerebro` (um `before_request` do Flask do Agent Zero). Ele só deixa passar a sessão que já
existe do Agent Zero quando **as três** condições valem:

| Campo da sessão | Tem que ser |
|---|---|
| `authentication` | igual a `helpers.login.get_credentials_hash()`, e esse hash não pode ser vazio |
| `usuario` | `matheus` (gravado pelo plugin `login_usuarios`) |
| `user_id` | `matheus` |

| Situação | Resposta |
|---|---|
| sem sessão, sessão velha (senha mestre trocada) ou Agent Zero sem login configurado | 401 (a página mostra "Entrar" → `/login?next=/segundo-cerebro`) |
| sessão de outra pessoa (ou login mestre sem `usuario`) | 403 (a página mostra "Sair" → `/logout`) |
| cabeçalho de identidade (`x-user`, `x-login`, `x-tenant`, `x-forwarded-user`, `remote-user`…) ou consulta (`?user=`, `?usuario=`, `?tenant=`…) | 403, mesmo com a sessão do Matheus |
| outra consulta na API | 400 |
| método diferente de GET/HEAD (página e assets) ou GET (API) | 405 com `Allow` |
| GET com corpo | 413 |
| Next fora do ar, travado ou sem versão instalada | 503 |
| outro caminho sob `/segundo-cerebro/`, `/api/segundo-cerebro/` ou `/_next/` | 404, sem chegar ao Next |

Só estes caminhos são servidos: `/segundo-cerebro`, `/segundo-cerebro/`, `/api/segundo-cerebro` e
`/_next/static/<arquivo .js/.css/.woff2/...>` (sem `..`, `%`, `\` ou `//`). As outras rotas do Agent Zero não mudam.
Toda resposta do gateway sai com `Cache-Control: private, no-store`, `Vary: Cookie`,
`Content-Security-Policy: frame-ancestors 'self'`, `X-Content-Type-Options: nosniff`.

Nada do que o navegador manda vai para o Next: cookies, `Authorization`, `x-*` e todos os outros cabeçalhos são
descartados (só um `Accept` válido passa). A página não tem campo de chave e não guarda nada: usa o cookie de sessão
do próprio site.

## Por dentro (servidor)

- O Next roda como `node server.js` (build `output: "standalone"`), iniciado pelo gateway no primeiro acesso válido,
  só em `127.0.0.1`, numa porta efêmera. Se o `/proc` mostrar a porta aberta em outro endereço, ele é derrubado.
- A cada início o gateway sorteia um bearer interno que fica só na memória do processo do Agent Zero. O filho recebe
  apenas o SHA-256 (`SECOND_BRAIN_TOKEN_SHA256`). O bearer vai só no pedido da API ao Next e nunca chega ao navegador
  nem ao disco.
- O ambiente do filho é montado do zero: `PATH`, `HOME`, `NODE_ENV`, `HOSTNAME=127.0.0.1`, `PORT`,
  `NEXT_TELEMETRY_DISABLED`, `SECOND_BRAIN_TOKEN_SHA256` e `SECOND_BRAIN_DATA_ROOT=/a0/usr`. Nada de chave da AWS
  ou outro segredo do Agent Zero.
- Tempo limite de 15 s por pedido; resposta acima de 8 MB vira 502. Se a API recusar o bearer interno, a resposta
  é 502, não 401. Se um início falhar, novas tentativas esperam 30 s. Ao encerrar, o filho recebe SIGTERM e depois
  SIGKILL.

## O que lê (a Pasta)

Só a Pasta, em `SECOND_BRAIN_DATA_ROOT/segundo_cerebro/pasta` (`/a0/usr/segundo_cerebro/pasta`), no formato de
`infra/vm/plugins/cerebro/helpers/pasta.py`. As nove fontes antigas (`memoria/decisoes`, `memoria/usuarios`, `fios/`,
o contexto de um chat, rotinas, projetos do Agent Zero e documentos avulsos) não são mais lidas.

| Fonte (`id`) | Onde, na Pasta | Como lê | Vira |
|---|---|---|---|
| `regras` | `CLAUDE.md` | arquivo fixo | `rules.regras` (itens numerados de "## Regras") |
| `contexto` | `Contexto/{organizacao,marca,estrategia,cliente-ideal,pessoas-chave,perfil}.md` | seis arquivos fixos | `contexts[]` com `estado` `validado` ou `pendente` (tem `[PENDENTE DE VALIDAÇÃO]`), `aprovado`, `validadoEm`, seções |
| `perfil` | `Contexto/perfil.md` | arquivo fixo | `profile[]`: só as linhas `- ` depois da marca da ferramenta `ficha`; sem a marca e com o marcador = `pendente`; sem os dois = `formato_antigo` |
| `decisoes` | `Decisoes/*.md` | varredura (abaixo) | `decisions[]` (mesmo formato de antes: `estado`, `valido_ate`, `vigente`, `substitui`…) |
| `pendencias` | `Pendencias/*.md` | varredura | `threads[]` (pendências; "em aberto" = aberto ou adiado vencido) |
| `assuntos` | `Assuntos/*.md` | varredura | `subjects[]` com `onde_parou`, `estado` (andamento/parado/encerrado), `emAndamento`, `historico` |
| `reunioes` | `Reunioes/*.md` | varredura | `meetings[]` (mais recente primeiro) |
| `notas` | `Notas-do-dia/AAAA-MM-DD.md` | varredura; outro nome fica fora (`nome_fora_do_padrao`) | `daily[]` (mais recente primeiro) |
| `documentos` | `Documentos/*.md` | varredura | `documents[]` |
| `projetos` | `Projetos/*.md` | varredura (subpastas de projeto não são lidas) | `projects[]` |

Nunca lido nem mostrado: `Arquivo-morto/` (nem item, nem link: `[[Arquivo-morto/…]]` num texto vira "(no
Arquivo-morto)" e só conta na lacuna), `indice.md`, arquivos que começam com `.`, o `.git` da Pasta.

**Formato de item** (Decisões, Pendências, Assuntos): cabeçalho entre `---` com uma linha `chave: <valor JSON>` por
campo (os dados) e corpo Markdown gerado a partir deles. `status` e `tags` são derivados e ignorados. Qualquer desvio
(sem cabeçalho, sem fim, linha sem `: `, valor que não é JSON) torna o item **ilegível**: a coleção inteira fica
`indisponivel` com código `ilegivel` e um aviso com o nome do arquivo (os itens legíveis continuam visíveis, mas a lista
não está completa, como no helper, que recusa ler a coleção). Notas livres (Reuniões, Notas do dia, Documentos,
Projetos, Contexto) têm cabeçalho opcional; uma nota ilegível deixa a fonte `parcial`.

**Área**: todo item traz `area` (do campo `area`; sem ele, `geral`); `areas` lista as que existem. A página tem um
filtro de área global (listas, contagens, mapa e consulta); a consulta aceita `area`. Contexto e perfil valem para
todas as áreas.

**Ligações** (`links[]`): só o que está gravado. `liga` (`["decisao:35", "pendencia:ab12cd", "assunto:x1y2z3"]`),
`[[Pasta/arquivo]]` (também `[[x|apelido]]`, `[[x#seção]]`) em qualquer arquivo lido e, nas pendências antigas, o texto
de `ligacoes` (quando é o id de outra pendência). Cada ligação tem `de`/`para` (`tipo:id`), `vias`, `resolvido` e a
evidência (fonte, item, campo, arquivo). `liga` e o link que o corpo repete viram uma ligação só; destino fora da
Pasta vira referência textual (nunca inventado); `liga` quebrada vira diagnóstico. `index` mapeia `Pasta/arquivo` →
`tipo:id` para a página seguir um link.

**Segurança (igual à de antes)**: dono fixo `matheus`; nenhum caminho vem do pedido (consulta na URL = 400); só
leitura. A única varredura é a de uma subpasta fixa: sem recursão, só `*.md` regulares, entrada que é link simbólico é
recusada (e anotada), no máximo 1000 arquivos por subpasta (`truncada`), 1 MB por arquivo (`grande`), 24 MB por carga.
Link simbólico em qualquer nível da raiz até o arquivo é recusado (`O_NOFOLLOW`). Ausente ≠ vazia: pasta que falta é
`indisponivel/ausente` com aviso, nunca lista vazia fingindo sucesso. Segredos e dados pessoais reconhecíveis (Bearer,
chaves, `senha: …`, e-mail, CPF/CNPJ, telefone, cartão) são trocados antes de sair. Cada item tem proveniência
(`fonte`, arquivo na Pasta, `arquivoAtualizadoEm`, dono). Sem a marca `.migrado` a página avisa que a Pasta ainda não
é a fonte do agente. A API do Next continua exigindo o bearer (`checkBearer`): sem gateway, ela recusa.

## Mapa de conexões (Sigma.js + Graphology)

- Desenho em canvas WebGL2 com `sigma` 4; `sigma` e `sigma/rendering` só carregam no navegador (`import()` dentro de
  um `useEffect`). Nó = item da Pasta (decisão, pendência, assunto, contexto, reunião, nota do dia, documento,
  projeto, fato do perfil) ou fonte; aresta = `links[]` (relações `liga`, `wiki`, `ligacao_texto`, `link_sem_destino`),
  `substitui` das decisões, `fontes` citadas nas pendências e a proveniência. Nada é inferido; agrupar por fonte, área,
  metadado ou tipo só muda a posição.
- Posições: ForceAtlas2 síncrono (`graphology-layout-forceatlas2`), semeado pelo layout radial e com número fixo de
  passos: mesma entrada, mesmas posições. Calculado uma vez por carga de dados, sobre o grafo inteiro; filtro, busca,
  seleção e hover não movem nós (filtro só redesenha o recorte).
- Hover/seleção destacam o nó e os vizinhos diretos (reducers, sem refazer o layout). Rótulos: `lib/label-layout.mjs`
  escolhe, em pixels de tela e com a largura real do texto, quais rótulos cabem sem se sobrepor e sem sair da borda
  (vira para a esquerda se faltar espaço à direita); o nó em foco sempre tem rótulo, vizinhos e fontes têm prioridade
  mas não são forçados; no mobile (< 640 px) há menos rótulos e mais folga. Refeito a cada zoom/pan/resize/foco.
- Zoom 40–400% (botões, roda, pinça, duplo toque), arrastar com mouse ou um dedo, "Ajustar mapa à tela", teclado no
  mapa (setas, +/−, 0, Esc). "Ir para" escolhe nó sem mouse; a **Lista** continua como alternativa HTML completa.
- Sem WebGL2 (ou contexto perdido): aviso e botão para a Lista. Ao trocar de recorte, ir para a Lista ou sair da
  página, o renderer é destruído (`kill`) com os ouvintes e o `ResizeObserver`.
- `data-renderer="pronto"` e `data-nodes`/`data-edges` no palco, e `__mapaViewport(id)` no elemento, existem para os
  testes de navegador (só leitura).

## Rodar localmente (sem gateway)

```bash
node node_modules/next/dist/bin/next dev -H 127.0.0.1
```

Sem o gateway a página mostra "Entrar" (a API responde 401). Para ver dados, use o caminho real (plugin + sessão) ou o
E2E, que põe um gateway falso na frente.

## Testes

```bash
node --test tests/*.test.mjs                                                    # 58 testes, Pasta fictícia
PLAYWRIGHT_MODULE=/caminho/playwright PLAYWRIGHT_CHROMIUM_EXECUTABLE=/caminho/chrome \
  node tests/second-brain.e2e.mjs                                               # opcional, depois do build
```

Usam só uma Pasta fictícia num diretório temporário (`tests/fixture-brain.mjs`, no formato do `pasta.py`, com
sentinelas no Arquivo-morto, numa subpasta de projeto e nos registros antigos, que nunca podem aparecer).
`second-brain-real-format.test.mjs` grava a Pasta com o próprio `pasta.py` (precisa de `python3`; sem ele, pula) e
confere que o site lê o que o agente escreve. O E2E sobe o Next em loopback e um gateway falso que faz o papel da
sessão. Ele confere que o navegador nunca manda `Authorization`, que sair passa por `/logout`, que a sessão expirada
mostra só o link de login, que outra pessoa não vê dados, e as seções da Pasta (onde parou, contexto pendente,
notas do dia, reuniões, área, link `[[…]]` navegável). `tests/connection-map.e2e.mjs` testa o mapa simples antigo,
que a página não mostra mais.

## Limites

- `/icon.svg` e `/manifest.webmanifest` (do layout raiz) não estão na lista de caminhos do gateway: no ar, o ícone da
  aba vem do Agent Zero ou falta.
- Só o Matheus. Não há outra identidade nem seleção de pessoa.
- Mapa: precisa de WebGL2 (sem ele, só a Lista). Rótulos longos aparecem encurtados no canvas e só os que
  cabem sem colisão são desenhados; o texto inteiro está nos detalhes, no "Ir para" e na Lista.

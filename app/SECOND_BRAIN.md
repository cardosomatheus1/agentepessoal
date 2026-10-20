# Segundo Cérebro (Matheus)

Painel só de leitura com decisões, próximos passos (fios), fatos de perfil e ligações do Matheus.

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

## O que lê

Só três arquivos fixos, abaixo de `SECOND_BRAIN_DATA_ROOT` (`/a0/usr`):

| Fonte | Arquivo | O que vira |
|---|---|---|
| Decisões | `memoria/decisoes/matheus.json` | `decisoes[]` (respeita `estado` e `valido_ate`) |
| Perfil | `memoria/usuarios/matheus.md` | só as linhas `- ...` |
| Fios | `fios/matheus.json` | `fios[]`; o grafo usa só `ligacoes` gravadas |

Nada de varrer pasta, de caminho vindo do usuário ou de outra pessoa. Link simbólico e arquivo acima de 1 MB são
recusados. Arquivo ausente ou inválido vira "fonte indisponível" com aviso (nunca lista vazia fingindo sucesso).
Nada é gravado. Segredos reconhecíveis (Bearer, chaves de API, `senha: ...`) são trocados por `[removido]`.
A API do Next continua exigindo o bearer (`checkBearer`, testes em `tests/second-brain.test.mjs`): sem gateway, ela
recusa.

## Mapa de conexões (Sigma.js + Graphology)

- Desenho em canvas WebGL2 com `sigma` 4; `sigma` e `sigma/rendering` só carregam no navegador (`import()` dentro de
  um `useEffect`). O grafo (`graphology`) tem exatamente as ligações gravadas: a aresta `e<i>` é a ligação `i` do
  recorte, com duplicadas (em curva) e auto-ligações (laço) preservadas. Nada é inferido.
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
node --test tests/second-brain.test.mjs tests/second-brain-boundaries.test.mjs \
  tests/second-brain-real-format.test.mjs tests/connection-map.test.mjs          # 26 testes, dados fictícios
PLAYWRIGHT_MODULE=/caminho/playwright PLAYWRIGHT_CHROMIUM_EXECUTABLE=/caminho/chrome \
  node tests/connection-map.e2e.mjs                                             # opcional, depois do build
```

Usam só dados fictícios num diretório temporário (inclui uma "Fernanda" sentinela que nunca pode aparecer). O E2E
sobe o Next em loopback e um gateway falso que faz o papel da sessão. Ele confere que o navegador nunca manda
`Authorization`, que sair passa por `/logout`, que a sessão expirada mostra só o link de login e que outra pessoa não
vê dados.

## Limites

- `/icon.svg` e `/manifest.webmanifest` (do layout raiz) não estão na lista de caminhos do gateway: no ar, o ícone da
  aba vem do Agent Zero ou falta.
- Só o Matheus. Não há outra identidade nem seleção de pessoa.
- Mapa: precisa de WebGL2 (sem ele, só a Lista). Rótulos longos aparecem encurtados no canvas e só os que
  cabem sem colisão são desenhados; o texto inteiro está nos detalhes, no "Ir para" e na Lista.

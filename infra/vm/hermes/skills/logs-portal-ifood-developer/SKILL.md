---
name: logs-portal-ifood-developer
description: "Consultar e capturar logs HTTP da API no portal iFood Developer (Logs da API): filtros de app, path, método e data, leitura da lista, salvamento em JSON e conferência. Use também em portais de desenvolvedor parecidos, com filtros mascarados."
version: 1.0.1
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-21
tags: ["aprendizado"]
trigger_patterns:
  - "logs da API"
  - "logs HTTP"
  - "iFood Developer"
  - "developer.ifood.com.br"
  - "logs_catalog"
  - "captura de logs"
  - "homologação iFood logs"
  - "HTTP Requests"
---

# Logs da API no portal iFood Developer

Use esta skill para coletar ou conferir logs HTTP (HTTP Requests) de um app de teste no portal e guardar em JSON como evidência de homologação. Para login e para a página de erro "Parece que algo deu errado", veja a skill login-sites-navegador. Para memória da máquina, veja manutencao-maquina.

## Fluxo
1. Abra `https://developer.ifood.com.br/pt-BR/developer/logs/api` com `browser_navigate`, ou reaproveite a página se já estiver nela. Se aparecer "Parece que algo deu errado", navegue de novo e espere o `browser_snapshot` mostrar o formulário **HTTP Requests** antes de mexer. Se o Matheus acabou de logar pelo "Resolver aqui", só recarregue a página.
2. Leia a tela com `browser_snapshot` e use as refs do ÚLTIMO snapshot. As refs mudam quando aparece "Limpar campo" ou quando o calendário abre.
3. **Confira o app primeiro.** O seletor de app lista os apps da conta (ex.: Teste (C), Teste (D), Raiz Connect). Ele pode mudar sozinho quando você mexe em outros campos. Releia o texto do seletor antes de cada Buscar e depois de qualquer clique perto dele.
4. **Path:** use `browser_type` na ref do campo com o texto completo, incluindo o `*` final (ex.: `/catalog/v2.0/*`). Releia o `value=` no próximo `browser_snapshot`: o campo pode mostrar o valor cortado ou grudado em outro texto.
5. **Datas (Início/Fim, dd/MM/yyyy):** os campos são mascarados e abrem um calendário por cima. Digite com `browser_type` pela ref, um campo por vez, e releia o `value=` de cada um. Se aparecer algo como `21/10/0002` ou `21/10/0020`, limpe o campo e digite de novo, ou recarregue a página e refaça tudo. Feche o calendário com `browser_press` "Escape" antes de continuar.
6. **Nunca clique por coordenada** nessa tela. Um clique com o calendário aberto cai no campo errado e corrompe Path e datas. Use sempre a ref. Se o `browser_snapshot` não trouxer ref, clique pelo DOM com `browser_console` e confira o `browser_snapshot` logo depois.
7. **Método (select):** se o clique não troca a opção, abra o seletor e clique no item pelo DOM com `browser_console`. A expression deve disparar `pointerdown`, `mousedown`, `pointerup`, `mouseup` e `click`. Para catálogo, busque o path sem filtrar método. Para merchant, filtre por método (PUT/POST/DELETE) e faça também a busca da listagem sem método.
8. **Buscar** só fica habilitado quando os campos estão válidos. Se continuar `disabled`, algum campo está inválido: releia os valores em vez de clicar de novo no mesmo botão. Depois de buscar, confirme que a lista mudou: devem aparecer linhas do path pedido ou "Não encontramos nenhum resultado".
9. **Ler a lista:** cada linha traz horário, app slug, método, path, código e tempo. O horário aparece em relógio de 12 h sem AM/PM (às 16:22 UTC a lista mostrou `04:22`). Compare com a hora atual antes de dizer que os logs são "de madrugada" ou que estão fora da janela pedida. Eventos `events:polling` (204) enchem a lista: filtre pelo path para não confundir polling com a captura de verdade.
10. **Salvar:** a tela traz muitas linhas. Pegue o blob com `browser_console` em fatias (ex.: `slice(0,12000)` e `slice(12000)`). Junte as fatias, valide com Python (`json.loads`) via `execute_code` e grave em `/a0/usr/workdir/ifood_homologacao/logs/<nome>.json`. Nunca sobrescreva um arquivo já validado: grave com nome novo.
11. **Validar antes de afirmar:** informe o total de registros, quantos têm o path pedido, o menor e o maior timestamp e os IDs únicos. Confira se o conteúdo cobre a janela pedida: uma captura só com polling não é evidência de catálogo. Se a página avisar que os eventos são truncados após 10.000 entradas, anote isso e use "buscar eventos da próxima janela".

## Armadilhas
- **Resultado vazio que contradiz arquivos já salvos para a mesma data e o mesmo app** quer dizer que o filtro está errado (app, data corrompida ou fuso), não que faltam dados. Recarregue a página e refaça os filtros do zero, conferindo cada campo, em vez de concluir "sem logs".
- **Não peça autorização para recarregar, reabrir ou usar uma aba nova**: isso faz parte da tarefa. Tente, e só pare por captcha, login ou decisão que é do Matheus.
- Chame as ferramentas `browser_*` com os argumentos direto (`ref`, `text`, `expression`). Não embrulhe os argumentos em outro `tool_args`.
- Delegar com `delegate_task` a mesma busca na mesma tela quebrada não resolve. Corrija os campos antes de delegar e peça ao ajudante que devolva os valores dos campos junto com o resultado.
- Não cite número (ex.: total de registros) que não esteja em arquivo ou na tela. Se uma contagem anterior não aparece em nenhum arquivo, diga isso.
- Ao terminar, deixe o seletor de app como estava.

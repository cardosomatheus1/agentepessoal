# painel

Painel vivo (14/10, a partir da skill `live-dashboard` do Hermes Agent, MIT): uma página **só de leitura** no web UI
(menu lateral → **Painel**) com:

- o funil da prospecção: propostas esperando o ✅, leads, demos e testes (`prospeccao.carregar`, `metricas`, `painel`);
- o desempenho dos posts dos últimos 7 dias e a agenda dos próximos 7 (`conteudo.desempenho` e
  `conteudo.agenda_proxima`; só no painel do Matheus, dono da @raiz.connect);
- a hora de cada leitura.

A página nunca lê as fontes: o job leve (`extensions/python/job_loop/_47_painel.py`) lê o que venceu (funil e agenda a
cada 10 min, desempenho a cada 3 h, porque chama a Meta) e salva `/a0/usr/painel/<login>.json`; a página mostra esse
arquivo e se atualiza sozinha a cada 30 s. Fonte que falha mantém o último valor bom, marcado **desatualizado** (o
erro e a hora da falha aparecem ao passar o mouse), e é tentada de novo em 15 min. A página não tem botão nem campo, e
a API (`api/painel.py`) só devolve o que está salvo, seja qual for o pedido.

**22/10 — painéis vivos sob pedido (do Claude Duet).** Quando você pede um painel de algo que muda ("monta um painel das
vendas"), o agente cria um painel vivo (ferramenta `painel_vivo`): uma receita (de onde ler, só leitura; quais números;
que conclusões) e uma rotina "📊 Painel: …" que o atualiza todo dia antes do resumo da manhã. Ele aparece nesta mesma
página, com cada número dizendo a fonte, até 5 conclusões do que fazer e a hora da leitura (sem atualizar há mais de
26 h: **desatualizado**). Dados em `/a0/usr/painel/vivos/<login>/<id>.json`; apagar só a seu pedido.

### prospeccao
Prospecção de clientes da Raiz Connect, um a um. Aquecer, primeira mensagem e lembrete estão pré-aprovados pelo Matheus dentro dos limites do dia (um revisor confere cada texto); respostas e parceiros vão para o ✅ dele. Siga o playbook (`acao` "playbook") à risca.
- "playbook": as regras (cliente ideal, região, oferta, tom, sequência, modelos, limites, proibições)
- "contexto": cotas que ainda cabem hoje, leads que devem receber o próximo passo agora, @ já conhecidos (não registre de novo) e como está indo
- "registrar": `leads` = lista de {canal ("instagram" ou "parceiro"), handle (@), url, nome, segmento, cidade, seguidores, motivo (por que encaixa, com o que você VIU no perfil), sinal (dor/sinal forte, se houver), ultimo_post (AAAA-MM-DD do primeiro post NÃO fixado), canais [ifood|encomenda|delivery|whatsapp|loja|catalogo], sinais [reajuste|insumo|expansao|contratacao|cardapio_precos|kits|promocao|reclamacao_custo], cardapio (bool), link_pedido (bool), exclusoes [rede|franquia|pessoal|privado|concorrente|curso|influencer], post_recente (do que trata)} — a ferramenta calcula a nota (0–100, mínimo 55) e recusa o que não encaixa
- "rejeitar": `leads` = lista de {handle, motivo curto} dos perfis que você examinou e NÃO encaixam (não voltam por 60 dias)
- "propor": `acoes` = lista de {lead_id, tipo (aquecer | dm_abertura | dm_lembrete | resposta | parceiro), texto, variante ("A"/"B" para dm_abertura)} — aquecer/dm_abertura/dm_lembrete aprovadas pelo revisor ficam prontas para executar; o resto vai ao celular do Matheus com ✅ / ✏️ / ❌; a ferramenta recusa o que fere o playbook (link, texto repetido, cedo demais, limite do dia) e diz o motivo
- "conferido": `direct` (quantas conversas com mensagem nova e de quem) e `notificacoes` (as primeiras linhas da página de notificações, copiadas) — obrigatório antes de "proxima" em cada rodada de execução
- "proxima": `conta_ativa` (o @ que está ATIVO no Instagram agora — confira no menu do perfil antes) → a próxima ação APROVADA que pode ser executada, com o texto exato e como fazer (ou "NADA AGORA"); recusa se a conta ativa não for a da Raiz
- "resultado": `acao_id`, `ok` (true/false), `detalhe` (o que apareceu na tela), `bloqueio` (true se o Instagram bloqueou/limitou — pausa 48 h)
- "etapa": `lead_id`, `etapa` (respondeu | lead | demo | teste | cliente | descartado), `nota` (o que a pessoa disse), `onde` ("direct" ou "comentario") — respondeu/lead/demo avisam o Matheus na hora (uma vez por resposta)
- "editar": `acao_id`, `texto` — nova versão (volta para aprovação)
- "hoje": o resumo do dia para o celular (ou "NADA HOJE")
- "metricas": `dias` — números por variante, segmento, cidade e faixa de nota
~~~json
{"tool_name": "prospeccao", "tool_args": {"acao": "registrar", "leads": [{"canal": "instagram", "handle": "marmitasdaana", "url": "https://www.instagram.com/marmitasdaana/", "nome": "Marmitas da Ana", "segmento": "marmitaria", "cidade": "Salvador", "seguidores": "3.2k", "motivo": "marmitas fit por encomenda, cardápio semanal com preços, post de ontem", "sinal": "reajustou preços na semana passada", "ultimo_post": "2026-10-09", "canais": ["encomenda", "whatsapp", "ifood"], "sinais": ["reajuste", "kits"], "cardapio": true, "link_pedido": true, "exclusoes": [], "post_recente": "kit de 10 marmitas de frango com batata-doce"}]}}
~~~

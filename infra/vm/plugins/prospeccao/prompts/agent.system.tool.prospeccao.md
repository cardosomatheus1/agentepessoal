### prospeccao
Prospecção de clientes da Raiz Connect, um a um, com aprovação do Matheus em cada contato. Siga o playbook (`acao` "playbook") à risca.
- "playbook": as regras (cliente ideal, região, oferta, tom, sequência, modelos, limites, proibições)
- "contexto": cotas que ainda cabem hoje, leads que devem receber o próximo passo agora, @ já conhecidos (não registre de novo) e como está indo
- "registrar": `leads` = lista de {canal ("instagram" ou "parceiro"), handle (@), url, nome, segmento, cidade, seguidores, motivo (por que encaixa, com o que você VIU no perfil), sinal (dor/sinal forte, se houver)}
- "rejeitar": `leads` = lista de {handle, motivo curto} dos perfis que você examinou e NÃO encaixam (não voltam por 60 dias)
- "propor": `acoes` = lista de {lead_id, tipo (aquecer | dm_abertura | dm_lembrete | resposta | parceiro), texto, variante ("A"/"B" para dm_abertura)} — vão ao celular do Matheus com ✅ / ✏️ / ❌; a ferramenta recusa o que fere o playbook (link, texto repetido, cedo demais, limite do dia) e diz o motivo
- "proxima": `conta_ativa` (o @ que está ATIVO no Instagram agora — confira no menu do perfil antes) → a próxima ação APROVADA que pode ser executada, com o texto exato e como fazer (ou "NADA AGORA"); recusa se a conta ativa não for a da Raiz
- "resultado": `acao_id`, `ok` (true/false), `detalhe` (o que apareceu na tela), `bloqueio` (true se o Instagram bloqueou/limitou — pausa 48 h)
- "etapa": `lead_id`, `etapa` (respondeu | lead | demo | teste | cliente | descartado), `nota` (o que a pessoa disse) — respondeu/lead/demo avisam o Matheus na hora
- "editar": `acao_id`, `texto` — nova versão (volta para aprovação)
- "metricas": `dias` — números por variante, segmento e cidade
~~~json
{"tool_name": "prospeccao", "tool_args": {"acao": "registrar", "leads": [{"canal": "instagram", "handle": "marmitasdaana", "url": "https://www.instagram.com/marmitasdaana/", "nome": "Marmitas da Ana", "segmento": "marmitaria", "cidade": "Salvador", "seguidores": "3.2k", "motivo": "marmitas fit por encomenda, cardápio semanal com preços, post de ontem", "sinal": "reajustou preços na semana passada"}]}}
~~~

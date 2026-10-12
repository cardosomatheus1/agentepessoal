### prospeccao
Prospecção de clientes da Raiz Connect, um a um, pela conta @raiz.connect. Tudo está pré-aprovado pelo Matheus dentro dos limites do dia e um revisor automático confere cada texto. Reprovado volta com "REESCREVA" e o motivo: corrija e mande de novo só esse item. Regras comerciais e modelos: acao "playbook"; o como no navegador: skill `prospeccao-instagram`.
- "playbook": as regras comerciais e os modelos (leia inteiro antes de escrever qualquer texto)
- "contexto": cotas de hoje, quem deve receber o quê agora (com a variante de cada 1ª mensagem), as conversas do Direct a abrir, o estoque por fonte, @ já conhecidos e rejeitados
- "registrar": `leads` = lista de {canal ("instagram" ou "parceiro"), handle, url, nome, segmento, cidade, seguidores, motivo (o que você VIU que faz encaixar), sinal, ultimo_post (AAAA-MM-DD), canais [ifood|encomenda|delivery|whatsapp|loja|catalogo|direct], sinais [reajuste|insumo|expansao|contratacao|cardapio_precos|kits|promocao|reclamacao_custo|responde_comentarios], cardapio (bool), link_pedido (bool), exclusoes [rede|franquia|pessoal (perfil de quem não vende nada)|privado|concorrente|curso|influencer], post_recente} → a ferramenta calcula a nota e recusa o que não encaixa. Parceiro vai sem exclusões e sem nota
- "rejeitar": `leads` = lista de {handle, motivo curto} dos perfis examinados que NÃO encaixam (não voltam por 60 dias)
- "fontes": `limite` (até 40) → repõe a parte do estoque da planilha e do catálogo e diz quanto falta de cada fonte
- "fontes_instagram": `buscas` (quantas buscas, um número; padrão 3: as palavras a ferramenta escolhe), `por_termo` (padrão 20) → enche a parte do Instagram pelo Apify, sem usar a nossa conta (verba do mês controlada)
- "conferir_estoque" → confere atividade, seguidores e privado dos leads achados fora do Instagram (pelo Apify ou pela API quando há; senão devolve um script)
- "estoque_conferido": `dados` = o texto que o script do conferir_estoque devolveu → tira do estoque o que não serve e guarda os números reais
- "buscar_script": `termos` = lista de buscas (ex.: "marmita fit bh") → script para `browser` evaluate que devolve os @ achados
- "avaliar_api": `achados` = o JSON do buscar_script (ou `leads`) → avalia pela API oficial da Meta, sem navegador (tente sempre antes do perfis_script)
- "perfis_script": `achados` (ou `leads` = lista de @) → script para `browser` evaluate com os dados de até 5 perfis por vez (a ferramenta diz quais @ passar na chamada seguinte e para no teto do dia)
- "avaliar_perfis": `dados` = o texto do script → registra com nota, recusa o que não encaixa e devolve só os que precisam de uma olhada à mão
- "limite_consulta": `detalhe` → você viu "http 429" num script e a ferramenta ainda não avisou: nenhuma consulta pelo Instagram até o dia seguinte (dois dias seguidos: até o Matheus liberar)
- "liberar_consultas": o Matheus libera as consultas de novo depois de dois dias de 429
- "propor": `acoes` = lista de {lead_id (@ ou id), tipo (dm_abertura | dm_lembrete | seguimento | resposta | parceiro), texto, base (o trecho copiado entre aspas e a data do post, ou "achado em fontes")}; deixe `variante` em branco (a ferramenta sorteia A ou B e o contexto diz qual escrever) → as aprovadas ficam prontas; as recusadas voltam com o motivo
- "comentar": `acao_id` (o aquecer em execução), `texto` (até 220 caracteres, sem venda e sem citar a Raiz), `base` (o trecho escrito do post, copiado entre aspas, e a data; só post de até 7 dias) → só publique se vier COMENTÁRIO APROVADO
- "comentado": `acao_id`, `ok`, `detalhe` → registra se o comentário aprovado saiu
- "editar": `acao_id`, `texto` → nova versão de uma ação ainda não executada (volta ao revisor)
- "caixa_lida": `direct` (quantas conversas com mensagem nova e de quem), `notificacoes` (as primeiras linhas copiadas da página de notificações), `interagiram` (os @ do registro que seguiram de volta, curtiram ou comentaram), `varredura` (true só depois de abrir todas as conversas, quando o contexto pedir VARREDURA COMPLETA) → obrigatória antes da "proxima" em cada rodada de execução
- "proxima": `conta_ativa` (o @ ativo agora; skill, seção 1) → a próxima ação aprovada, com o texto exato e como fazer; ou "ESPERE" (espere e chame de novo), "NADA AGORA" (termine) ou "CONFIRA ANTES DE QUALQUER ENVIO" (só olhe a tela e registre)
- "resultado": `acao_id`, `ok`, `detalhe` (o que apareceu na tela), `bloqueio` (true se o Instagram bloqueou ou pediu verificação: pausa de 48 h; sem `acao_id` quando apareceu fora de uma ação)
- "etapa": `lead_id`, `etapa` (interagiu | respondeu | lead | demo | teste | cliente | descartado), `nota` (o que a pessoa disse, ou o motivo), `onde` ("direct" ou "comentario"), `negocio` (true se, num comentário, a pessoa falou de preço, custo, lucro ou do sistema) → "interagiu" (ou resposta a comentário sem negócio) só dá prioridade na 1ª mensagem; respondeu, lead e demo avisam o Matheus na hora (uma vez por fala); "descartado" na visita por perfil parado ou fora da faixa de seguidores volta ao estoque em 60 dias
- "cartao": `lead_id` → manda ao celular do Matheus o cartão de 1 página do lead (sai sozinho quando o lead vira lead ou demo)
- "assumir" / "devolver": `lead_id` → o Matheus conversa pessoalmente com esse perfil (as rodadas param para ele) / devolve ao agente
- "apagada": `acao_id`, `detalhe` → uma mensagem nossa foi apagada por ordem do Matheus: ela deixa de contar
- "importar_lista": `arquivo` (.json com nome novo em /a0/usr/prospeccao/) → põe a lista de empresas na fila; depois "fontes" transforma em leads
- "variante": `texto` "A" ou "B" fixa a variante da 1ª mensagem (só com o OK do Matheus); vazio volta ao sorteio
- "token_meta": lê o token da Meta da aba aberta e guarda no cofre (o valor nunca passa por você)
- "hoje": o resumo do dia (ou "NADA HOJE")
- "metricas": `dias` → números por variante, segmento, cidade, faixa de nota e fonte
~~~json
{"tool_name": "prospeccao", "tool_args": {"acao": "registrar", "leads": [{"canal": "instagram", "handle": "marmitasdaana", "url": "https://www.instagram.com/marmitasdaana/", "nome": "Marmitas da Ana", "segmento": "marmitaria", "cidade": "Salvador", "seguidores": "3.2k", "motivo": "marmitas fit por encomenda, cardápio semanal com preços, post de ontem", "sinal": "reajustou preços na semana passada", "ultimo_post": "2026-10-09", "canais": ["encomenda", "whatsapp", "ifood"], "sinais": ["reajuste", "kits"], "cardapio": true, "link_pedido": true, "exclusoes": [], "post_recente": "kit de 10 marmitas de frango com batata-doce"}]}}
~~~

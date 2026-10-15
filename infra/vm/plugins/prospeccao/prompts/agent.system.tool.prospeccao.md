### prospeccao
Prospecção de clientes da Raiz Connect, um a um, pela conta @raiz.connect. Tudo está pré-aprovado pelo Matheus dentro dos limites do dia e um revisor automático confere cada texto. Reprovado volta com "REESCREVA" e o motivo: corrija e mande de novo só esse item. Regras comerciais e modelos: acao "playbook"; o como no navegador: skill `prospeccao-instagram`.
- "playbook": as regras comerciais e os modelos (leia inteiro antes de escrever qualquer texto)
- "contexto": cotas de hoje, quem deve receber o quê agora (com a variante de cada 1ª mensagem), as conversas do Direct a abrir, o estoque por fonte, @ já conhecidos e rejeitados
- "registrar": `leads` = lista de {canal ("instagram" ou "parceiro"), handle, url, nome, segmento, cidade, seguidores, motivo (o que você VIU que faz encaixar), sinal, ultimo_post (AAAA-MM-DD), canais [ifood|encomenda|delivery|whatsapp|loja|catalogo|direct], sinais [reajuste|insumo|expansao|contratacao|cardapio_precos|kits|promocao|reclamacao_custo|responde_comentarios], cardapio (bool), link_pedido (bool), stories (bool: stories no ar na visita, contam como ativo), exclusoes [rede|franquia|pessoal (perfil de quem não vende nada)|privado|concorrente], post_recente} → a ferramenta calcula a nota e recusa o que não encaixa. Curso, professor, influenciador, consultor, contador e fornecedor vão com canal "parceiro", sem exclusões e sem nota
- "rejeitar": `leads` = lista de {handle, motivo curto} dos perfis examinados que NÃO encaixam (não voltam por 60 dias)
- "fontes": `limite` (até 40) → repõe a parte do estoque da planilha e do catálogo e diz quanto falta de cada fonte
- "fontes_instagram": `buscas` (quantas buscas, um número; padrão 3: as palavras a ferramenta escolhe), `por_termo` (padrão 20) → enche a parte do Instagram pelo Apify, sem usar a nossa conta (verba do mês controlada)
- "conferir_estoque" → confere atividade, seguidores e privado dos leads achados fora do Instagram (pelo Apify ou pela API; sem eles, a conferência fica para a visita, ou vem um script se o Matheus ligou os scripts)
- "estoque_conferido": `dados` = o texto que o script do conferir_estoque devolveu → tira do estoque o que não serve e guarda os números reais
- "buscar_script": `termos` = lista de buscas (ex.: "marmita fit bh") → script para `browser` evaluate que devolve os @ achados (só com os scripts ligados)
- "avaliar_api": `achados` = o JSON do buscar_script (ou `leads`) → avalia pela API oficial da Meta, sem navegador (tente sempre antes do perfis_script)
- "perfis_script": `achados` (ou `leads` = lista de @) → script para `browser` evaluate com os dados de até 5 perfis por vez (só com os scripts ligados; a ferramenta diz quais @ passar na chamada seguinte e para no teto do dia)
- "avaliar_perfis": `dados` = o texto do script → registra com nota, recusa o que não encaixa e devolve só os que precisam de uma olhada à mão
- "limite_consulta": `detalhe` → você viu "http 429" num script e a ferramenta ainda não avisou: nenhuma consulta pelo Instagram até o dia seguinte (dois dias seguidos: até o Matheus liberar)
- "liberar_consultas": o Matheus libera as consultas de novo depois de dois dias de 429
- "liberar_bloqueio": o Matheus libera a prospecção depois de um segundo bloqueio em 30 dias (volta pela metade por 7 dias)
- "scripts_conta": `texto` "ligar" ou "desligar" → busca e avaliação por script com a @raiz.connect (desligadas por padrão para proteger a conta; só com ordem do Matheus)
- "propor": `acoes` = lista de até 5 {lead_id (@ ou id), tipo (dm_abertura | dm_lembrete | seguimento | resposta | parceiro), texto, base (o trecho copiado entre aspas e a data do post; numa resposta, a fala da pessoa entre aspas)}; deixe `variante` em branco (a ferramenta sorteia A ou B e o contexto diz qual escrever) → as aprovadas ficam prontas; as recusadas voltam com o motivo
- "comentar": `acao_id` (o aquecer em execução, ou um aquecido atrasado da lista "sem_comentario"), `texto` (pelo playbook), `base` (o trecho escrito do post, entre aspas, e a data) → só publique se vier COMENTÁRIO APROVADO
- "comentado": `acao_id`, `ok`, `detalhe` → registra se o comentário aprovado saiu
- "pular_comentario": `acao_id`, `detalhe` → aquecido atrasado sem post recente com algo escrito: sai da lista de atrasados
- "editar": `acao_id`, `texto` → nova versão de uma ação ainda não executada (volta ao revisor)
- "caixa_lida": `direct` (quantas conversas com mensagem nova e de quem), `notificacoes` (as primeiras linhas copiadas da página de notificações), `interagiram` (os @ do registro que seguiram de volta, curtiram ou comentaram), `varredura` (true quando o `ler_direct` disser que a varredura ficou registrada) → obrigatória antes da "proxima" em cada rodada de execução
- "ler_direct": com https://www.instagram.com/direct/inbox/ aberto no navegador, chame SEM `dados` → a ferramenta lê a lista de conversas na própria aba, registra as respostas e a varredura e diz o que abrir ("direct_script" só explica isso)
- "falha": `texto` = o problema da rodada que não é do Matheus (página que não carrega, conversa que não abre, script que falha, clique errado) → vai ao operador; a rodada segue e termina SEM NOVIDADE se nada mais mudou
- "proxima": `conta_ativa` (o @ ativo agora; skill, seção 1) → a próxima ação aprovada, com o texto exato e como fazer; ou "ESPERE" (espere e chame de novo), "NADA AGORA" (termine) ou "CONFIRA ANTES DE QUALQUER ENVIO" (só olhe a tela e registre)
- "resultado": `acao_id`, `ok`, `detalhe` (o que apareceu na tela), `bloqueio` (true se o Instagram bloqueou ou pediu verificação: a prospecção pausa; sem `acao_id` quando apareceu fora de uma ação)
- "etapa": `lead_id`, `etapa` (interagiu | respondeu | lead | demo | teste | cliente | descartado), `nota` (o que a pessoa disse, ou o motivo; comece por "pendente:" quando a resposta depende do Matheus), `onde` ("direct" ou "comentario"), `negocio` (true se, num comentário, a pessoa falou de preço, custo, lucro ou do sistema) → "interagiu" só dá prioridade na 1ª mensagem; lead, demo e nota "pendente:" avisam o Matheus na hora (uma vez por fala); o resto vai no resumo das 20h17; descarte na visita por perfil parado ou fora da faixa volta ao estoque em 60 dias
- "entrou": `handle`, `nota` (o que a pessoa escreveu), `negocio` (true se fala da Raiz, da calculadora, de preço ou do nosso comentário) → alguém fora do registro escreveu para a @raiz.connect: com negocio, entra no registro como resposta e você propõe a `resposta`; sem negocio, o Matheus é avisado uma vez só e você não responde
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

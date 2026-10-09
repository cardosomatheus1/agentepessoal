# Radar — pesquisa proativa e monitores

Como o "proactive research" do Dots: uma tarefa agendada ("🔎 Radar", 08:40, 11:40, 14:40, 17:40 e 20:40
America/Bahia) lê pelo conector `google` os e-mails novos e a agenda das próximas 48 h, **só leitura**, e manda
ao celular apenas o que pede ação (conta a vencer, alguém esperando resposta, conflito de agenda, prazo) como
sugestão — "posso rascunhar?", nunca enviando nada. Sem novidade, fica em silêncio; o que vence hoje/amanhã
chega na hora mesmo no horário de silêncio (`PRECISA DE VOCÊ:`).

Monitores ("me avise quando chegar e-mail do contador", "se mudar a reunião de sexta") são guardados com a
ferramenta `monitor` em `/a0/usr/radar/<login>.json` e checados em cada rodada do radar. Rodadas espaçadas
(não a cada minuto) para a VM poder hibernar entre elas; push em tempo real do Gmail exigiria Pub/Sub com
faturamento no Google Cloud, que fica de fora.

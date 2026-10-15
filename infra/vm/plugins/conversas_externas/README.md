# Conversas com lojas e clínicas

Pedido de 15/10 (Ilia): "ache uma loja e use meu WhatsApp pra perguntar se tem a peça", "procure clínicas e pergunte
horários", com a conversa seguindo, não só a primeira mensagem.

- **WhatsApp da própria pessoa**: o WhatsApp Web dela no perfil de navegador dela (`navegador_por_pessoa`), numa
  conversa dedicada ("WhatsApp de <nome> (conversas com lojas)") que é a única dona da aba. Conectar: ferramenta
  `conversa_externa` acao `conectar` com o número dela → código de 8 letras que ela digita no celular (Aparelhos
  conectados > Conectar com número de telefone). Sem QR.
- **Pergunta e informa** (decisão do Matheus): preço, estoque, horário. Marcar, reservar, aceitar preço, pagar ou
  passar dado pessoal só com `confirmado` (as palavras da pessoa); a ferramenta recusa sem isso. A 1ª mensagem diz
  que é o assistente da pessoa.
- **Protege o número**: 8 contatos novos por dia, 20 mensagens por dia por conversa, só das 7h às 21h.
- **Vigia sem modelo** (`job_loop/_48_vigiar_conversas.py`): lê cada conversa aberta (4 min nas 2 primeiras horas,
  15 min até 24 h, 1 h até 3 dias); só quando a loja escreve algo novo a conversa da pessoa recebe "[Conversa
  externa …]" e o agente responde. 3 dias sem resposta: encerra e avisa. Mantém a VM acordada 6 h depois da última
  mensagem.
- Estado: `/a0/usr/conversas_externas/<login>.json`, só pelas funções de `helpers/externas.py`.

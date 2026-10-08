# Consultar o Sol

O agente roda no GPT-6 Luna (barato e rápido). Quando está em dúvida — instrução ambígua, ação
difícil de desfazer, entrega que alguém vai avaliar, ou 2 tentativas sem avanço — ele chama
`consultar_sol`, que manda **só o caso** ao GPT-6.1 Sol: a pergunta e o resumo do agente, o
`contexto.md` da conversa, a última mensagem do usuário e até 8 imagens. O Sol responde com
recomendação (siga / siga com ajuste / pare e pergunte), o porquê e os passos.

O Sol só aconselha: pagamento, termos legais, contas reais, apagar dados e envios para terceiros
continuam dependendo do usuário. Cada consulta fica em `chats/<id>/conselhos_sol.md`.

Custo medido: uma revisão de texto = ~600 tokens de entrada e ~400 de saída no Sol (~US$ 0,005).

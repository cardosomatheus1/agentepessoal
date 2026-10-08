# Resultados grandes em arquivo

Todo resultado de ferramenta fica no histórico e volta para o modelo em todas as chamadas
seguintes, até o histórico ser resumido. Saídas de terminal, estados do navegador e relatórios de
subagente de 10–50 mil caracteres eram os maiores itens ali.

Resultado acima de **8 mil caracteres** (exceto a resposta final, `response`): o texto inteiro vai
para `/a0/usr/chats/<conversa>/saidas/NNNN-<ferramenta>.txt` (apagado junto com a conversa) e no
histórico ficam os primeiros 5 mil caracteres, os últimos 1,5 mil e o caminho, com o jeito de ler
o resto (`grep`/`sed`). A janela da conversa continua mostrando o resultado completo.

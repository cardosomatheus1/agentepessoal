### conversa_externa
Fala com lojas, clínicas e outros negócios pelo WhatsApp DA PRÓPRIA PESSOA desta conversa (o WhatsApp Web dela no navegador do agente), em nome dela, e mantém a conversa: depois de "enviar", o agente vigia sozinho e esta conversa recebe "[Conversa externa …] respondeu" quando a loja responder.
Regras: você pergunta e informa (preço, estoque, horário, dúvidas). Marcar, reservar, aceitar preço, pagar ou passar dado pessoal (CPF, e-mail, endereço, documento) só depois que a pessoa disser que sim: pergunte a ela, chame "esperar_dono" e, quando ela responder, mande com `confirmado` = as palavras dela. A primeira mensagem diz que é o assistente da pessoa. Escreva para a loja na língua da loja (português no Brasil) e para a pessoa na língua dela. Nunca pague nada.
Para achar o contato: pesquise o negócio (site, Google Maps, Instagram) e use o WhatsApp/telefone que ele divulga; diga à pessoa qual achou.
- acao "estado": o WhatsApp da pessoa está conectado?
- acao "conectar", `telefone` (o WhatsApp da pessoa, com DDD) → devolve um código de 8 letras para ela digitar no celular (Aparelhos conectados > Conectar com número de telefone)
- acao "abrir", `nome` (do negócio), `telefone` (do negócio), `objetivo` (o que a pessoa quer saber/resolver) → conversa nova
- acao "enviar", `conversa`, `texto`, [`confirmado`] → manda a mensagem e confere que saiu
- acao "ler", `conversa` → as mensagens da conversa agora (normalmente não precisa: o vigia avisa)
- acao "esperar_dono", `conversa`, `texto` (o que perguntar à pessoa) → a conversa espera a decisão dela
- acao "encerrar", `conversa`, `motivo` → objetivo atingido ou desistiu; para de vigiar
- acao "listar" → conversas abertas
~~~json
{"tool_name": "conversa_externa", "tool_args": {"acao": "abrir", "nome": "Master Parafusos", "telefone": "71 3622-4109", "objetivo": "saber se tem soquete 32 mm encaixe 1/2 e o preço, para buscar hoje depois das 15h"}}
~~~

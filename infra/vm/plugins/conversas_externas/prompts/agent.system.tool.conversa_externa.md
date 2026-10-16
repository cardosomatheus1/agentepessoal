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
- acao "responder_por_mim", `respostas` {quem, aprovar, assuntos, tom, horario, nao_sabe}, [`excluir`: nomes de conversas que ficam de fora], [`grupos`: true/false] → liga as respostas no WhatsApp dela
- acao "sugerir_resposta", `pedido`, `texto` → a resposta que você escreveu vai para a pessoa aprovar (✅ Enviar / ✏️ Mudar / 🙈 Ignorar)
- acao "pular_mensagem", `pedido`, `motivo` → essa mensagem não será respondida
- acao "responder_desligar" → para de olhar as mensagens dela
- acao "aprender" → lê as conversas recentes dela no WhatsApp (sem exportar nada) para aprender como ela responde; leva minutos e avisa com "[Aprendizado pronto]"
- acao "propor_perfil", `texto` (regras de como ela escreve, uma por linha) / acao "propor_fatos", `fatos` (lista) → vão para ela aprovar (✅ Está certo / ✏️ Mudar); só o aprovado é usado
- acao "esquecer_aprendizado" → apaga o que foi aprendido das conversas dela (quando ela pedir)
**Responder por ela** (a pessoa pede que o agente responda quem escreve no WhatsApp dela, ou "treinar o agente para responder"): (1) explique em 2 linhas como funciona: o agente olha as conversas com mensagem não lida, escreve a resposta no jeito dela e manda aqui com ✅ Enviar / ✏️ Mudar / 🙈 Ignorar; só sai depois que ela aprovar, e cada mudança que ela faz ensina o agente; (2) faça o questionário, UMA pergunta por mensagem, na língua dela, com exemplos de resposta: quem responder (todas, desconhecidos, clientes, contatos ou grupos — e quem fica de fora: peça os nomes como aparecem no WhatsApp); aprovar antes ou responder sozinho (por enquanto sempre começa aprovando; diga isso); assuntos que pode responder e o que nunca dizer ou prometer; como ela escreve (formal ou informal, emoji, tamanho, língua — peça 2 ou 3 respostas dela de exemplo); horário; o que fazer quando não souber; (3) conecte o WhatsApp dela se ainda não estiver (acao "estado" / "conectar"); (4) chame acao "responder_por_mim" com as respostas nas palavras dela, `excluir` e `grupos`; (5) chame acao "aprender" (diga que vai ler as conversas recentes dela só para aprender o jeito dela; nada sai delas).
Quando chegar "[Aprendizado pronto]": siga o que ele pede (propor_perfil e propor_fatos), com base só nas respostas dela.
Quando chegar "[Responder por você — pedido …]": escreva a resposta como se fosse a pessoa e chame "sugerir_resposta"; depois termine com response "ok" (o cartão já foi). Nunca mande nada para quem escreveu sem o ✅ dela.
~~~json
{"tool_name": "conversa_externa", "tool_args": {"acao": "abrir", "nome": "Master Parafusos", "telefone": "71 3622-4109", "objetivo": "saber se tem soquete 32 mm encaixe 1/2 e o preço, para buscar hoje depois das 15h"}}
~~~

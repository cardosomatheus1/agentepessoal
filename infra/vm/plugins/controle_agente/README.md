# Controle do agente

Corrige os controles do chat do Agent Zero para uso pessoal:

| Controle | Antes | Agora |
|---|---|---|
| Mandar mensagem com o agente trabalhando | ia para a fila e só era lida no fim da tarefa inteira | chega na hora; o agente lê no próximo passo (≈1 s durante comandos) |
| Mensagem enviada bem no fim da tarefa | ficava parada até a próxima mensagem | vira um novo turno assim que a tarefa termina |
| Pausar | só parava o "pensamento"; scripts em execução (jogo, adb) continuavam | congela também os comandos que o agente deixou rodando; Retomar descongela |
| Parar / Destravar (nudge) / apagar chat | scripts em execução continuavam | os comandos do agente são encerrados (Ctrl+C e, 2 s depois, kill) |

A fila continua disponível (botão de enviar fila / Enter vazio), mas não é mais o caminho padrão.

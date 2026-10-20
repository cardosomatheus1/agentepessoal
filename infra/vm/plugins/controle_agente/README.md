# Controle do agente

Corrige os controles do chat do Agent Zero para uso pessoal:

| Controle | Antes | Agora |
|---|---|---|
| Mandar mensagem com o agente trabalhando | ia para a fila e só era lida no fim da tarefa inteira | chega na hora; o agente lê no próximo passo (≈1 s durante comandos) |
| Mensagem enviada bem no fim da tarefa | ficava parada até a próxima mensagem | vira um novo turno assim que a tarefa termina |
| Pausar | só parava o "pensamento"; scripts em execução (jogo, adb) continuavam | congela também os comandos que o agente deixou rodando; Retomar descongela |
| Parar / Destravar (nudge) / apagar chat | scripts em execução continuavam | os comandos do agente são encerrados (Ctrl+C e, 2 s depois, kill) |

| Mesma ferramenta falhando com argumentos diferentes | o detector de loop só pegava a mesma ação com o mesmo resultado | na 3ª falha seguida da ferramenta o agente recebe um aviso para mudar de abordagem (a tarefa continua) |
| Ajudante (subagente) trabalhando sem parar | 175 passos sem resposta (11/10) | teto de 40 passos por tarefa, com aviso no 32º; no teto ele para e devolve o que tem a quem chamou. O agente principal (A0) não tem teto; ajudante de rodada da prospecção, 150 |
| Agente principal delegando sem falar com a pessoa | ~33 ajudantes em 4 h sem resposta nem `notify_user` (18/10) | a partir da 3ª delegação seguida sem `response`/`notify_user`, o resultado do ajudante vem com aviso para responder à pessoa e dizer o que está pronto e o que falta, e para não relançar o mesmo trabalho parcial (só aviso; a tarefa continua) |
| Resultado igual a um anterior (512+ caracteres) | entrava inteiro de novo no histórico | entra como "igual ao resultado do passo N"; a janela do chat continua mostrando tudo. Só o item novo muda, então o começo do prompt continua igual e o cache (`cache_prompt`) não se perde |
| Rodada agendada que não fecha | rodadas sem novidade de até 120 passos (13-19/10) | o agente principal de uma rodada recebe, no passo 30 (120 na prospecção) e a cada 10 depois, um aviso para fechar com a resposta final; nunca é parado à força (a resposta final é o que chega ao celular) |

As regras "o que nunca sem a pessoa" (modo objetivo) e "parar na 2ª repetição" ficam nas "Regras que valem sempre"
do `prompt_enxuto` (20/10); aqui só se aponta para elas.

A fila continua disponível (botão de enviar fila / Enter vazio), mas não é mais o caminho padrão.

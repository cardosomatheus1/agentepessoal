# Agenda confiável

O agendador do Agent Zero confere a cada 60 s se o horário de uma tarefa caiu "no último minuto", mas
o laço dorme 60 s **depois** de cada conferência, então os horários escorregam alguns segundos por volta.
Quando a conferência passa de um minuto cheio (ex.: 23:01:01 para uma tarefa das 23:00), a rodada é
pulada sem aviso — aconteceu com o vigia do Claude Code às 23:00 de 08/10.

Esta extensão roda no mesmo laço (`job_loop`): para cada tarefa agendada parada, se o último horário
previsto passou há mais de 90 s e há menos de 15 min e a tarefa não rodou desde então, roda agora
(uma vez por horário) e registra no log.

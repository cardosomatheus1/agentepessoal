### reuniao
Agenda o briefing (30 min antes) e a pergunta do pós-reunião (10 min depois do fim) de uma reunião da agenda dele; as rodadas acordam a máquina sozinhas. Use para reuniões de verdade (com outras pessoas ou com pauta), não para lembretes pessoais nem eventos de dia inteiro. Se o horário mudou, chame de novo com o mesmo `evento_id`.
- `acao`: "agendar" | "listar" | "pos_registrado"
- "agendar": `evento_id` (id do evento no Google Agenda), `titulo`, `inicio` e `fim` (ISO com fuso, ex. 2026-10-12T14:00:00-03:00), `participantes` (nomes/e-mails), `local` (endereço ou link)
- "pos_registrado": `evento_id` — depois de transformar a resposta dele sobre a reunião em fios/lembretes
~~~json
{"tool_name": "reuniao", "tool_args": {"acao": "agendar", "evento_id": "7k3...", "titulo": "Alinhamento NEXOS", "inicio": "2026-10-12T14:00:00-03:00", "fim": "2026-10-12T15:00:00-03:00", "participantes": "João (joao@x.com)", "local": "Google Meet"}}
~~~

### tarefa_limite
Fim e histórico das tarefas agendadas. Toda tarefa nova expira sozinha em 30 dias, salvo se o usuário quiser permanente; intervalo mínimo entre rodadas: 10 min.
- `uuid`: id da tarefa; `acao`: "ver" (fim + últimas rodadas) | "terminar_em" (com `termina_em`: "7d" ou "2026-10-31") | "permanente"
Ao criar uma tarefa, diga ao usuário quando ela termina; use "permanente" só se ele pedir algo contínuo (ex.: "todo dia", "sempre").
~~~json
{"tool_name": "tarefa_limite", "tool_args": {"uuid": "AbC123", "acao": "terminar_em", "termina_em": "7d"}}
~~~

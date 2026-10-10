### contas
Contas, boletos, faturas e renovações com vencimento. Os lembretes saem sozinhos no celular (3 dias antes, na véspera e no dia) com "✅ Já paguei", "⏰ Amanhã" e "🙈 Não é minha". Você só registra e avisa: nunca paga nem mexe em meios de pagamento.
- `acao`: "salvar" | "listar" | "paga" | "ignorar"
- "salvar": `descricao` (quem cobra e o quê), `vencimento` (AAAA-MM-DD), `valor` (ex. "189,90"; vazio se não souber), `moeda` (BRL padrão), `fonte` (de onde veio: e-mail de quem/assunto) — a mesma conta vista de novo é atualizada, não duplicada
- "paga" / "ignorar": `id`
~~~json
{"tool_name": "contas", "tool_args": {"acao": "salvar", "descricao": "Fatura Vivo Fibra (outubro)", "vencimento": "2026-10-15", "valor": "129,90", "fonte": "e-mail da Vivo, 'Sua fatura chegou'"}}
~~~

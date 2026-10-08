# Cache do prompt

O Bedrock guarda em cache cada prompt enviado e cobra só 1/10 do preço pela parte de um prompt
novo que **começa exatamente com um prompt anterior inteiro** (testado: mesmo começo com final
diferente não aproveita nada; o prompt anterior + mensagens novas no fim aproveita tudo).

O Agent Zero montava cada chamada como `instruções + histórico + [EXTRAS]`, com o bloco de extras
(hora, navegadores abertos e página, memórias e soluções lembradas, skills) refeito a cada passo.
Como o fim mudava sempre, nenhuma chamada saía do cache — e cada uma ainda pagava a gravação dele.

| Arquivo | O que faz |
|---|---|
| `message_loop_prompts_after/_98_extras_no_historico.py` | grava os extras no histórico como uma mensagem normal, só com o que mudou desde o passo anterior, e esvazia o bloco do fim |
| `_functions/agent/Agent/prepare_prompt/end/_50_tirar_extras_vazio.py` | tira o bloco vazio que sobra no fim e atualiza o texto lembrado para o replay nativo (raciocínio e chamadas de ferramenta) continuar valendo |

Assim cada chamada começa com a anterior inteira. O cache só se perde quando o histórico é
resumido (a partir de ~50 mil tokens, `ctx_history` 0.25) ou quando as instruções mudam.

Para medir: `/var/lib/agentepessoal/uso.jsonl` (gravado pelo proxy) traz `entrada`, `cache` e
`cache_gravado` de cada chamada.

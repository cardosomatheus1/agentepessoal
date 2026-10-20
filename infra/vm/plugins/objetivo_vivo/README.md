# Objetivo vivo da conversa

Queixa do Matheus (20/10): o agente perde contexto, responde outra coisa, dá passos pequenos e precisa de 20 comandos.

No fim do contexto de cada conversa com uma pessoa (celular e app; Matheus e convidados) vai um bloco curto:

```
## Objetivo vivo desta conversa
Pedido atual dele, literal: «Monta a planilha dos 30 leads e manda pro meu e-mail»
Passos combinados (1 de 3 feitos):
1. [x] achar os 30 leads no CRM
2. [ ] montar a planilha
3. [ ] mandar para o e-mail dele
Termine o pedido inteiro antes da resposta final (aviso de andamento com `notify_user` não encerra a tarefa). Só pare para o que é do Matheus decidir: dinheiro, envio a terceiros, apagar, captcha, credencial.
```

- **Pedido atual:** a última mensagem dele que pede algo, literal (até 400 caracteres), sem os acréscimos do celular
  (citação, leitura das abreviações, conversa paralela, aviso de reinício).
- **"continua", "e aí?", "oq tá fazendo?"** são pedido de estado, e "pode", "sim", "faz" são confirmação: não trocam o
  objetivo nem os passos. Mensagem de máquina ("[Conversa externa …]", botões, gatilhos) também não. A regra de
  responder o estado já está no `whatsapp/_60_conversa_whatsapp.py`; o bloco só a repete nas conversas do app.
- **Pedido novo** troca o objetivo e zera os passos; se o anterior tinha passos abertos, ele aparece como "pedido
  anterior (vale só se o atual o continua)".
- **Passos:** o agente registra e marca com a ferramenta `passos` (`passos`: a lista, "[x]"/"[ ]"; `feitos`: números).
- **Regra:** a de parar só no que é da pessoa decidir aponta para as "Regras que valem sempre" (`prompt_enxuto`).
- **Cache:** o bloco vai como extra persistente (`loop_data.extras_persistent`), que o `cache_prompt` grava no
  histórico só quando muda, e de novo quando fica mais de 12 mensagens para trás (`REPETIR`). Só acrescenta no fim:
  o começo do prompt não muda. Sem hora nem sorteio: o mesmo estado dá o mesmo texto.
- **Onde não entra:** rotinas (`scheduler/tasks.json`), conversas de gatilho, contexto de tarefa e ajudantes.
- O `msg_id` do pedido atual é o que o `resumo_seguro` usa para nunca resumir a tarefa em andamento.

| Arquivo | O que faz |
|---|---|
| `helpers/objetivo.py` | lê a mensagem (pedido × estado × confirmação), guarda o estado e monta o bloco |
| `extensions/python/_functions/agent/Agent/hist_add_user_message/end/_30_objetivo_vivo.py` | atualiza o objetivo a cada mensagem dele |
| `extensions/python/message_loop_prompts_after/_30_objetivo_vivo.py` | põe o bloco nos extras persistentes |
| `tools/passos.py` | a ferramenta `passos` |

Estado: dado da conversa `objetivo_vivo` (vai junto no `chat.json`). Ideias: Cline "Focus Chain" (lista lembrada a
cada poucas mensagens e mantida depois da compactação), lista de tarefas do Claude Code, `/goal` do Hermes e do OpenClaw.

Testes: `tests/suite.py`.

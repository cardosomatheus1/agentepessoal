# Aprender com o trabalho

Depois de uma tarefa longa (8 ou mais passos de ferramenta) ou de uma correção do Matheus ("não era isso", "já falei",
"de novo", "sem nexo"…), um modelo (Sonnet 5.5) relê a tarefa e **cria ou melhora uma skill**. Assim, na próxima vez,
o agente já começa sabendo fazer aquele tipo de tarefa do jeito dele.

É a revisão de skills do Hermes Agent (MIT, NousResearch, `agent/background_review.py`), com o mesmo prompt traduzido:
- skills de classe de tarefa, com regras e não narrativas;
- correção dele é sinal de primeira classe;
- "nada a salvar" vale, mas não é o padrão;
- nunca guardar falha de ambiente, "a ferramenta X não funciona" nem tentativas que não deram certo.

| Arquivo | O que faz |
|---|---|
| `extensions/python/monologue_end/_64_aprender.py` | no fim de um turno numa conversa do Matheus (celular ou app), decide se revisa e roda a revisão numa thread; avisa no celular |
| `helpers/aprender.py` | quando revisar, prompt, pedido (skills existentes + a tarefa), conferência e gravação |

**Onde não roda:** rodadas agendadas, conversas de gatilho, ajudantes e conversas de outras pessoas. As skills valem
para todas as conversas do agente, então só o Matheus ensina. No máximo uma revisão a cada 30 minutos por conversa.

**O que ele pode escrever:**
- Só reescreve skills com `origem: aprendizado` no cabeçalho, ou seja, as que ele mesmo criou.
- Skill do repositório (prospecção, celular…) ou feita à mão nunca é tocada: a proposta vai para
  `/a0/usr/aprendizado/sugestoes.md`, para entrar no repositório com commit e teste.
- Antes de reescrever, a versão anterior vai para `/a0/usr/aprendizado/historico/`.
- Recusa nome fora do padrão (`a-z0-9-`), conteúdo maior que 8.000 caracteres e qualquer coisa que pareça chave ou
  token.
- Toda revisão entra em `/a0/usr/aprendizado/diario.jsonl`, inclusive "nada" e "recusada".

**Aviso:** uma linha no celular quando cria ou melhora uma skill (`📚 Aprendi uma skill nova: …` /
`📚 Melhorei a skill …`).

**Desligar sem implantar:** criar `/a0/usr/aprendizado/desligado`.

**22/10 — limpeza de skills (dos vídeos do Claude Duet: skill acumulada precisa de higiene).** Cada skill carregada é
contada (`extensions/python/tool_execute_after/_65_uso_skill.py` → `/a0/usr/aprendizado/uso.json`). Uma vez por dia
(`extensions/python/job_loop/_66_arquivar_skills.py`), as skills que **este plugin escreveu** e que ninguém carregou nem
reescreveu em 30 dias vão inteiras para `/a0/usr/aprendizado/arquivo/<nome>-<data>/` (saem da lista do agente) e você
recebe uma linha no celular. Nada é arquivado antes de 30 dias de contagem; skill do repositório ou feita à mão nunca.

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

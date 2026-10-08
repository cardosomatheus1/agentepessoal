# rotinas

Rotinas reutilizáveis, como as skills do Grok Bot, em cima das skills do Agent Zero (`/a0/usr/skills`).

- **`salvar_rotina`**: uma tarefa que deu certo vira `SKILL.md` com *quando usar*, *entradas e acessos*
  (senhas só como `§§secret(NOME)`), *passos*, *como verificar*, *o que entregar* e *o que precisa de
  aprovação*. Aparece no menu `/` e é carregada quando o pedido combina. Salva sozinha quando você pede
  "sempre/toda vez/rotina"; senão o agente oferece em uma linha.
- **Correções**: quando você corrige o jeito de fazer, a correção vai para a seção *Correções do usuário*
  da rotina (vale acima dos passos e sobrevive quando a rotina é salva de novo). Sem rotina, vai para a
  memória.
- **`me_mostre`** ("me mostre uma vez"): grava o Navegador da conversa a cada mudança de tela (até 20
  min) enquanto você faz a tarefa; ao terminar, o agente estuda as telas (`analisar_imagens`), pergunta só
  o ambíguo e salva a rotina.

As rotinas são do agente (todos os logins veem); a tag traz o login de quem salvou.

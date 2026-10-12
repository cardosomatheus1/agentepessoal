# Rotinas agendadas do agente (cópia versionada)

Um arquivo por rotina (`<uuid>.json`: nome, horário, estado, `system_prompt` e `prompt`), tirado do agendador da VM.
As rodadas da prospecção ficam em `infra/vm/plugins/prospeccao/rodadas.py`. Rotinas desligadas e nunca guardadas ficam
de fora (as de acompanhar o Claude Code, obsoletas).

- `python3 infra/operador/rotinas.py comparar`: o que difere entre a VM e o git (mudança feita fora do git aparece aqui).
- `python3 infra/operador/rotinas.py exportar`: VM → git (revise o diff e commite). Recusa texto com cara de segredo.
- `A0_SENHA=… python3 infra/operador/rotinas.py aplicar <uuid>`: git → VM (nome, horário, prompt e system_prompt,
  pela API do agendador; o `tasks.json` nunca é editado à mão). Rotina com
  `"state": "disabled"` no git é desligada também (ligar de novo: `tarefa_atualizar.py <uuid> estado idle`).

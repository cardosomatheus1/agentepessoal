# Rotinas agendadas do agente (cópia versionada)

Um arquivo por rotina (`<uuid>.json`: nome, horário, estado, `system_prompt` e `prompt`), tirado do agendador da VM.
As rodadas da prospecção ficam em `infra/vm/plugins/prospeccao/rodadas.py`. Rotinas desligadas e nunca guardadas ficam
de fora (as de acompanhar o Claude Code, obsoletas).

- `python3 infra/operador/rotinas.py comparar`: o que difere entre a VM e o git (mudança feita fora do git aparece aqui).
- `python3 infra/operador/rotinas.py exportar`: VM → git (revise o diff e commite). Recusa texto com cara de segredo.
- `A0_SENHA=… python3 infra/operador/rotinas.py aplicar <uuid>`: git → VM (nome, horário, prompt e system_prompt,
  pela API do agendador; o `tasks.json` nunca é editado à mão). Rotina com
  `"state": "disabled"` no git é desligada também (ligar de novo: `tarefa_atualizar.py <uuid> estado idle`).

O portão (pular a rodada quando a fonte barata não mudou) é configurado por rotina em
`infra/vm/plugins/rotinas/portao.json` (vai para a VM com `implantar.py rotinas`), não no JSON da rotina: o
agendador não guarda campos extras.

Arquivo sem `uuid` é rotina nova, ainda não criada na VM: `A0_SENHA=... python3 infra/operador/rotinas.py criar <arquivo>` cria pela API do
agendador e depois `exportar` grava como `<uuid>.json` (o arquivo sem uuid sai). Ex.: `qt0dNXtu` (🔭 Concorrentes — semana).

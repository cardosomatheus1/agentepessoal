# CLAUDE.md — agente pessoal do Matheus

Todo Claude que trabalhar neste repositório (qualquer conta, qualquer sessão) segue estas regras. Elas existem
porque erros bobos aconteceram quando duas sessões mexeram na mesma coisa sem regra (11/10).

## Antes de qualquer coisa
1. `git pull` no branch de trabalho (`ccr-bcbe3101-9u4klv`): outra sessão pode ter mudado algo.
2. Leia `docs/HANDOFF_CONTA_NOVA.md` (como operar) e `docs/ARQUITETURA_PROSPECCAO.md` (se for mexer na
   prospecção).

## Regras que não se quebram
- **Implantar na VM só por `python3 infra/operador/implantar.py <plugin> [--skill <skill>]`.** Ele só leva o que
  está commitado e no GitHub, recusa se a VM roda versão de outra sessão que você não tem, e testa numa cópia antes
  de trocar a viva. Nada de copiar plugin à mão, por tar, para `/opt/a0/usr/plugins`.
- **Dados vivos (`/opt/a0/usr/prospeccao/*.json`, `scheduler/tasks.json` etc.) nunca se editam à mão.** Correção
  passa pelas funções do helper (que validam e registram no diário), com `AUTOR["quem"] = "operador: <motivo>"`.
  Se a função certa não existe, crie-a com teste, commite e implante.
- **Estado de ação da prospecção só muda por `_mudar()`** (tabela `TRANSICOES`). Transição proibida dá erro: não
  contorne; corrija a causa.
- **Toda mudança de comportamento vem com teste** na suíte do plugin, e a suíte inteira passa antes do commit.
- **Ação destrutiva fora daqui** (apagar mensagem, desfazer envio, apagar arquivo do usuário) só com ordem explícita
  do Matheus para aquele caso.
- **Uma frente, uma sessão:** antes de mexer num plugin, confira no `git log` se outra sessão mexeu nele nas últimas
  horas; se sim, combine pelo Matheus em vez de trabalhar em paralelo.
- Segredos só no cofre/SSM; nunca no chat, em arquivo ou no git. Sem identificador de modelo em commit. PR só se ele
  pedir.

## Como o Matheus trabalha
Português, curto, sem jargão. Ele quer coisa feita e testada de verdade, não plano. Pergunte só o que é decisão
dele.

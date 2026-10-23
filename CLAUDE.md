# CLAUDE.md — agente pessoal do Matheus

Todo Claude que trabalhar neste repositório (qualquer conta, qualquer sessão) segue estas regras. Elas existem
porque erros bobos aconteceram quando duas sessões mexeram na mesma coisa sem regra (11/10).

## O agente é o Hermes (desde 23/10)
O agente do Matheus roda no **Hermes** (`docs/MIGRACAO_HERMES.md`): container `hermes` na VM, os nossos plugins de
`infra/vm/plugins/` rodam nele pela ponte (`infra/vm/hermes/plugins/agentepessoal`), rotinas no cron dele
(`infra/vm/hermes/rotinas/`), portal (Segundo Cérebro, Painel, Tarefas, Cofre, Navegador) em `infra/vm/portal`. O Agent
Zero (A0, container `agent-zero`) está **parado só para a volta** até 30/10: não ligue (as rotinas rodariam duas vezes);
voltar só com ordem do Matheus, por `python3 infra/operador/virada.py voltar --motivo "..."`. Ferramentas do operador
que falavam com o A0 param com aviso de legado (`infra/operador/legado_a0.py`) e dizem o equivalente no Hermes.

## Antes de qualquer coisa
1. `git pull` no branch de trabalho (`ccr-bcbe3101-9u4klv`): outra sessão pode ter mudado algo.
2. Leia `docs/MIGRACAO_HERMES.md` (como o Hermes está montado e como voltar), `docs/HANDOFF_CONTA_NOVA.md` (como
   operar) e `docs/ARQUITETURA_PROSPECCAO.md` (se for mexer na prospecção).

## Regras que não se quebram
- **Implantar na VM só por `python3 infra/operador/implantar.py`**: `<plugin> [--skill <skill>]` (os plugins que o
  Hermes roda; a suíte do plugin roda numa cópia, num container descartável da imagem do A0, antes de trocar a viva;
  o Hermes relê a ferramenta sozinho), `--hermes` (o Hermes, o portal, os Hermes dos convidados e as rotinas: sobe no
  modo da chave, virada ou ensaio) e `--host <script> [--reiniciar|--unidade]`. Ele só leva o que está commitado e no
  GitHub e recusa se a VM roda versão de outra sessão que você não tem. Nada de copiar à mão, por tar, para
  `/opt/a0/usr/plugins` ou `/opt/hermes`.
- **Dados vivos (`/opt/a0/usr/prospeccao/*.json`, `/opt/hermes/data/cron/jobs.json`, cofres etc.) nunca se editam à
  mão.** Correção passa pelas funções do helper (que validam e registram no diário), com `AUTOR["quem"] = "operador:
  <motivo>"`; rotina muda em `infra/vm/hermes/rotinas/<uuid>.json` (com teste) e vai por `implantar.py --hermes`; ligar
  e pausar rotina é pela API do cron do Hermes (`cron.jobs`), nunca editando o JSON. Os helpers rodam na VM por
  `/opt/agentepessoal/a0py` (no Hermes; no A0 só se ele estiver no ar). Se a função certa não existe, crie-a com teste,
  commite e implante.
- **Convidados isolados** (Matheus, 23/10: "precisa ser isolado, de forma alguma acessar nada meu"; "só o meu perfil
  tem acesso a 100% da máquina"): o Hermes de cada convidado (`hermes-<login>`, `infra/vm/hermes/convidado.sh`) não
  monta nada do agente além do código das ferramentas dele, da pasta do celular, do cofre e da chave dele. Nunca
  monte dados do Matheus num container de convidado.
- **Estado de ação da prospecção só muda por `_mudar()`** (tabela `TRANSICOES`). Transição proibida dá erro: não
  contorne; corrija a causa.
- **Toda mudança de comportamento vem com teste** na suíte do plugin, e a suíte inteira passa antes do commit
  (`python3 infra/operador/rodar_suites_locais.py` roda todas fora da VM; o GitHub roda o mesmo a cada push).
- **Ação destrutiva fora daqui** (apagar mensagem, desfazer envio, apagar arquivo do usuário) só com ordem explícita
  do Matheus para aquele caso.
- **Uma frente, uma sessão:** antes de mexer num plugin, confira no `git log` se outra sessão mexeu nele nas últimas
  horas; se sim, combine pelo Matheus em vez de trabalhar em paralelo.
- **O Segundo Cérebro se atualiza sozinho com o trabalho do operador:** o gancho `Stop` deste repositório
  (`.claude/hooks/cerebro_operador.py`) manda à VM, a cada resposta, as falas do Matheus e o relato do que foi feito; a
  anotação automática registra decisões (com a fala literal dele), frentes e pendências e avisa no celular. Não
  desligue o gancho; escreva no relato final, em português claro, o que foi feito e onde parou. Correção à mão só
  pelos helpers, com `por="operador: <motivo>"`.
- Segredos só no cofre/SSM; nunca no chat, em arquivo ou no git. Sem identificador de modelo em commit. PR só se ele
  pedir.

## Como o Matheus trabalha
Português, curto, sem jargão. Ele quer coisa feita e testada de verdade, não plano. Pergunte só o que é decisão
dele.

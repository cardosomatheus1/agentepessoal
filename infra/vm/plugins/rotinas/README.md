# rotinas

Rotinas reutilizáveis, como as skills do Grok Bot, em cima das skills do Agent Zero (`/a0/usr/skills`).

- **`salvar_rotina`**: uma tarefa que deu certo vira `SKILL.md` com *quando usar*, *entradas e acessos*
  (senhas só como `§§secret(NOME)`), *passos*, *como verificar*, *o que entregar* e *o que precisa de
  aprovação*. Aparece no menu `/` e é carregada quando o pedido combina. Salva sozinha quando você pede
  "sempre/toda vez/rotina"; senão o agente oferece em uma linha.
- **Correções**: quando você corrige o jeito de fazer, a correção vai para a seção *Correções do usuário*
  da rotina, com data e quem gravou (vale acima dos passos e sobrevive quando a rotina é salva de novo). Sem
  rotina, vai para a memória. Correção repetida (mesmo texto, sem contar acento, maiúscula e pontuação) é
  recusada. Para trocar um trecho, o agente lê a rotina (`ler`, que devolve a `versao`) e usa `ajustar`; sem
  ter relido, ou se a rotina mudou depois, nada é trocado. Com 8 correções acumuladas, a ferramenta pede que o
  agente reescreva os passos limpos (`salvar` com `consolidar`; a versão anterior fica em `.versoes/`).
  Toda mudança fica em `<rotina>/.versoes/diario.jsonl`.
- **`helpers/rotinas.py`** é a porta única para mexer nas rotinas (`listar`, `ler`, `corrigir`, `ajustar`,
  `salvar`): a ferramenta e o revisor do fim da conversa usam as mesmas regras.
- **Portão das rotinas agendadas** (`portao.json`, `helpers/portao.py`, gancho em
  `_functions/agent/Agent/monologue`): antes de uma rodada, uma fonte barata, sem IA (ids dos e-mails novos e
  eventos da agenda pelo conector Google, ou um arquivo como o registro de fios), é comparada com o que a
  última rodada viu (`/a0/usr/rotinas/portao/<uuid>.json`). Nada mudou: a rodada é pulada sem chamar o modelo
  (fica "SEM NOVIDADE (portão…)" no histórico). Mudou: a rodada roda e recebe no fim da tarefa só o que mudou.
  Fonte com erro = roda; a primeira rodada de cada dia roda sempre completa; o estado novo só vale quando a
  rodada termina sem erro. Ligado no 🔎 Radar e fios soltos (HL76nfIg: e-mails + agenda) e no 💡 Iniciativa
  (2FIQTI0o: fios em aberto + e-mails + agenda). O Nexos fica sem: a página da Meta só se lê logado no
  navegador, não há fonte barata confiável.
- **`me_mostre`** ("me mostre uma vez"): grava o Navegador da conversa a cada mudança de tela (até 20
  min) enquanto você faz a tarefa; ao terminar, o agente estuda as telas (`analisar_imagens`), pergunta só
  o ambíguo e salva a rotina.

**Autoavaliação das rotinas agendadas (20/10, `helpers/autoavaliacao.py`):** no fim de cada rodada
(`monologue/end/_20_autoavaliar.py`, em segundo plano) um modelo barato dá nota 1–5 e uma linha sobre o resultado
(`/a0/usr/rotinas/autoavaliacao/<uuid>.jsonl`). Se vir uma melhoria, vai UMA mensagem ao Matheus com ✅ Aplicar / ❌ Não
(botão `rta:`, tratado em `whatsapp/api/receber.py`); no máximo uma por rotina a cada 7 dias, nunca repetida, nunca de
rodada com falha de infra (erro, 429, conexão, login) e sem modelo em rodada "SEM NOVIDADE". Aplicar grava pela
`corrigir_agendada` (`/a0/usr/rotinas/agendadas/<uuid>/correcoes.md`, com data e "aprovou a sugestão …"); o prompt da
rotina no agendador não muda: as correções entram no fim da tarefa a cada rodada (`monologue/start/_30_correcoes_agendada.py`).

As rotinas são do agente (todos os logins veem); a tag traz o login de quem salvou.

**Rodada enxuta (20/10, `helpers/rodada.py`, `monologue/start/_20_rodada_enxuta.py`):** a rodada agendada começa só
com a rodada anterior no histórico do modelo (quando ela tem até 12 mil tokens); as mais antigas e os resumos saem.
O chat da prospecção vivia no teto do histórico (~50 mil tokens, "History compression stalled" a cada passo): cada
chamada de uma rodada de 7 passos levava 35-50 mil tokens de rodadas velhas. O que a rodada precisa do passado está
no checkpoint (contexto.md, o estado da ferramenta, o portão). A janela do chat continua com tudo.

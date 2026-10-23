# Migração do agente do Matheus: Agent Zero → Hermes

Pedido (23/10/2026, Matheus): "Eu acho que vamos precisar migrar tudo nosso pro Hermes, pode iniciar, cuidado pra n
deixar nada de fora, nenhuma das nossas rotinas, telegram, segundo cerebro, nossos plugins de insta, gmail e etc" ·
"As skills tbm, lembra de td msm" · "E precisa ver como conectar td ao Hermes".

Base da decisão: teste lado a lado de 23/10 (`infra/operador/lado_a_lado/`), mesmas 10 tarefas, mesmas informações
(Segundo Cérebro inteiro), mesmo modelo (Claude Sonnet 5): os dois terminaram 9/10; o Hermes foi mais rápido em 8.

## Regras da migração

1. **Nada desliga antes de ter substituto provado.** O Agent Zero (A0) continua atendendo até o corte final; cada
   item abaixo só é marcado ✅ depois de rodar no Hermes com dados reais, sem enviar nada a terceiros no teste.
2. **Os dados vivos não mudam de lugar.** `/opt/a0/usr` fica onde está e é montado no Hermes no mesmo caminho
   (`/a0/usr`), então os helpers puros (prospecção, conteúdo, cérebro, fios…) rodam sem mudança e as regras do
   CLAUDE.md (só pelas funções dos helpers, `_mudar()`, testes) continuam valendo.
3. **A entrada de mensagens continua sendo a nossa** (Lambda → SQS → ponte), porque a VM hiberna: o Telegram do
   Hermes por polling não acordaria a máquina. Só o destino da ponte muda (A0 → Hermes), com uma chave para voltar.
4. **Corte em um passo só e reversível:** desliga o agendador do A0, liga os agendamentos do Hermes, vira a ponte.
   O A0 fica parado (não apagado) por 7 dias; voltar = virar a ponte e religar o agendador.
5. Cada peça nova: teste, revisão OpenCode, implantação pelo implantador (que ganha o destino Hermes).

## Como cada coisa se conecta ao Hermes

| O que | Hoje (A0) | No Hermes |
|---|---|---|
| Modelo | proxy `:8787` (Bedrock, uso por dono) | o mesmo proxy: provedor Bedrock/Anthropic apontado para `:8787` (mantém o registro de uso e o cache) |
| Telegram e WhatsApp | Lambda → SQS → `ponte_whatsapp.py` → `POST /api/plugins/whatsapp/receber` | a mesma ponte entrega ao **API server do Hermes** (sessão por pessoa); resposta volta por `/enviar` da ponte. Comandos sem modelo (`/senha`, `/silencio`, `/painel`…) ficam na ponte |
| Botões (aprovar, recusar, Bora/Útil…) | ponte + plugin `aprovacoes`/`iniciativa`/`prospeccao` | ficam na ponte (callbacks chegam pelo mesmo caminho) e caem numa API do nosso plugin Hermes |
| Aprovações antes de ação de risco | hook `tool_execute_before` + cartão | hook `pre_tool_call` do plugin, com o mesmo `revisor.py` e as mesmas regras; espera assíncrona como hoje (Duet 5) |
| Cofre (`§§secret(NOME)`) | hooks de troca e máscara | `pre_tool_call` troca o nome pelo valor, `transform_tool_result` mascara; armazenamento igual (`/a0/usr/segredos`) |
| Gmail, Agenda, Drive, Planilhas | workspace-mcp `127.0.0.1:8765` | o mesmo servidor em `mcp_servers:` do Hermes, só nas conversas do Matheus |
| GitHub MCP | config viva do A0 | `mcp_servers:` |
| Instagram (API da Meta) | `conteudo`, `concorrentes`, `painel` | ferramentas do plugin, mesmos helpers, token no cofre |
| Instagram (navegador logado) | perfil `/opt/a0/usr/navegador/sessions/shared` | Chromium nosso com esse perfil, exposto por CDP; Hermes usa `browser.cdp_url` (login preservado) |
| Segundo Cérebro (Pasta, captura, nota do dia) | plugin `cerebro` | ferramenta `cerebro` + hook de fim de conversa (captura) + tarefas de fundo |
| Site do Segundo Cérebro, Painel, Tarefas | dentro da interface do A0 | site Next próprio atrás de login nosso (o Hermes não tem portão de páginas) |
| Rotinas (16) e rodadas da prospecção | agendador do A0 | agendamentos do Hermes (`cron/jobs.json`), mesmo horário e mesmo pedido |
| Tarefas de fundo sem modelo (publicar post, CRM, nota do dia, IMAP, conferência…) | `job_loop` do A0 | serviço "relógio" do plugin (thread no gateway) chamando os mesmos helpers |
| Acordar a VM antes da tarefa | `proximo_despertar.py` lê `tasks.json` do A0 | lê `cron/jobs.json` do Hermes |
| Skills (27 na VM) | `/a0/usr/skills` | `~/.hermes/skills` (mesmo formato SKILL.md); nomes de ferramentas ajustados |
| Memória | ficha, decisões, busca nas conversas | ficha e regras no prompt (`SOUL.md` + seção do plugin), Pasta como fonte, `session_search` do Hermes + busca antiga |
| Áudio | Whisper do A0 / faster-whisper | STT do Hermes (faster-whisper local) ou a ponte transcreve como hoje |
| Apify, Tavily, Jina, Vertex, TypeSafe, S3, Polly | proxy e cofre | iguais (o plugin chama os mesmos helpers) |

## Lista de conferência (nada fica de fora)

Legenda: **H** = o Hermes já faz (só configurar) · **P** = portar (helper reaproveitado, camada nova) · **N** = não
portar (era conserto do A0; conferir que o Hermes não tem o defeito) · **D** = decisão do Matheus.

Estado em 23/10, fim da fase 7 (✅ feito e conferido ao vivo no ensaio · ⏳ falta, antes da virada · ➖ não porta).

### Plugins (49)
- ✅ prospeccao — ferramenta pela ponte; navegador logado por CDP (a lista do Direct pelo script, sem passar pelo
  modelo); rodadas buscar/executar/resumo no cron do Hermes. ⏳ CRM na planilha (`_46_crm_raiz` usa o MCP do A0)
- ✅ conteudo (publicação na hora pelo relógio; no ensaio nada se publica) · ✅ especialistas · ✅ concorrentes
- ✅ painel e quadro (portal) · ✅ cerebro (ferramenta + relógio: nota do dia, versão, cópia) · ✅ segundo_cerebro
  (portal, mesmo portão) · ✅ memoria_pessoal (ficha e decisões no 1º turno; `decisao`, `ficha`, `lembrar`)
- ✅ fios_soltos · ✅ iniciativa · ✅ auxiliar (contas, rascunho; `reuniao` por cima do cron do Hermes) · ✅ radar
- ✅ aprovacoes (revisor e regras do A0; botões pela ponte) · ✅ cofre (máscara no proxy + ponte; ferramentas que agem)
  · ✅ login_usuarios (convidados só com uso pessoal; o portal usa os mesmos logins) · ✅ whatsapp (chave na ponte,
  ensaio, reenvio pelo relógio). ⏳ e-mail para o agente (`_57`, IMAP → pedido numa sessão do Hermes), gatilhos
  (`/gatilho` da função de controle → Hermes). ✅ áudio e andamento editado no Telegram
- ✅ conectores (H: MCP Google/GitHub do Hermes, container `hermes-mcp`) · ✅ central/livro (+ conferência no relógio)
- ✅ rotinas: portão (script do cron, `wakeAgent`), autoavaliação e correções aprovadas · H: `salvar_rotina` = cronjob_manage
  · ⏳ `me_mostre` (gravar a tela para virar rotina) · ⏳ `canal`, `painel_vivo` (os painéis existentes aparecem no portal)
- ➖ agenda_confiavel (o cron do Hermes tem catch-up e trava própria) · H aprendizado (curador do Hermes)
- H pesquisa (`web_search`/`web_extract` do Hermes; o SearXNG do A0 não faz falta) · ✅ video · ✅ analisar_imagens
- H ler_arquivo (`read_file`) + ✅ `ler` (PDF/Word/planilha) · ✅ consultar_sol · ⏳ objetivo_vivo (`passos` saiu: H
  `todo_list`) · ⏳ celular_rapido/celular_tela (D2: o Android continua; a ferramenta precisa de adb/uiautomator2 na
  imagem e da rede até o `android`) · ⏳ conversas_externas (D3: continua; abre conversa no A0 hoje)
- ⏳ arquivo_grande (entrada por S3 → pasta do Hermes) · ⏳ agent_delegates (D5: `delegar` ao OpenClaw pela caixa)
- ➖ limpeza (o Hermes fecha o próprio navegador) · ⏳ navegador_por_pessoa (convidados sem navegador por ora) · D navegador_visual
- ➖ acoes_paralelas, cache_prompt, controle_agente, estilo_claude, interface_celular, navegador_rapido, prompt_enxuto,
  resultados_grandes, resumo_seguro — as regras de sempre estão no `SOUL.md`; as do celular e da rotina, nos blocos
  dos ganchos (`rotinas_hermes.py`)
- D nexos_ads_campaign3_fixed (descartar)

### Rotinas (23 no A0: 17 ligadas, 6 desligadas)
- ✅ todas no cron do Hermes (`infra/vm/hermes/rotinas/`, mesmo horário e pedido, só as ferramentas trocadas; o teste
  confere os itens essenciais de cada uma), criadas pausadas; ✅ as 17 ligadas rodadas uma vez à mão (`rotina_rodar.py`,
  sem ligar) com saída só para o operador; ✅ desligadas migram desligadas
- ✅ briefing/pós-reunião (`reuniao` agenda únicos no cron do Hermes) · ✅ portão e correções por rotina · ⏳ painéis vivos novos

### Skills (27)
- ✅ as 27 adaptadas às ferramentas do Hermes e semeadas uma vez (o curador cuida); listadas e lidas pelo Hermes.
  ⏳ `celular` e `piloto-rapido` dependem da ferramenta do celular

### Serviços do servidor
- ✅ proxy (máscara do cofre e uso do Hermes) · ✅ ponte (chave A0/Hermes) · ✅ credenciais Meta/voz (ficam)
- ⏳ caixas de convidados e delegados (ficam; `terminal_isolado` pela ponte ✅, `delegar` ⏳)
- ⏳ túnel e URL do agente (`report_url.py` → portal :8650 na virada) · ✅ `proximo_despertar.py` (lê o cron do Hermes)
- ⏳ `saude.py`, `watchdog.sh` (o Hermes conta como atividade pelo proxy ✅), `memguard.sh` (incluir os containers do
  Hermes), `backup.sh` (+ `/opt/hermes`) · ✅ `firewall.sh` (rede hermes, navegador, conectores)
- ⏳ `setup.sh` / `deploy.py` (instalar o Hermes numa VM nova) · D Android e ws-scrcpy · ➖ SearXNG
- ⏳ OpenCode 2 + Ponytail fora do container do A0

### Dados e logins
- ✅ `/opt/a0/usr` montado no Hermes (só leitura até a virada) · ✅ tarefas agendadas convertidas · ➖ `agenda/limites.json`
- ✅ perfis do navegador (cópia do `shared`; na virada, o próprio) · ✅ OAuth do workspace-mcp (cópia no `hermes-mcp`)
- ✅ cofre e `.descricoes` (mesmos arquivos) · ⏳ conversas antigas (no ensaio escondidas: têm tokens colados; na
  virada `lembrar` lê as do A0) · ✅ `/var/lib/agentepessoal/*` (ficam) · ✅ MCP GitHub · ⏳ "Sempre permitir" do A0
  (vazio hoje; o do Hermes fica em `/opt/hermes/data/agentepessoal/aprovacoes_sempre.txt`)

### Operador e CI
- ✅ `implantar.py --hermes` (Hermes + portal) · ✅ `hermes_ao_vivo.py` (travas, cofre, ferramentas, run, destino,
  telegram) · ✅ rotinas: `rotinas_aplicar.py`/`rotina_rodar.py` · ⏳ `mandar_msg.py`/`ver_chat` para o Hermes
- ⏳ `falhas_do_dia.py` · ✅ `revisar_opencode.py` (usado em cada passo) · ✅ hooks do Cérebro · ✅ CI verde (615/615
  e os testes do host) · ⏳ `CLAUDE.md` e `HANDOFF` (fase 9)

### Fora da AWS / feitos à mão
- ⏳ `vigia_google.gs` (o gatilho chega à ponte: muda com ela) · ⏳ conserto noturno (lê os logs do Hermes)
- ✅ snapshot DLM e alarme da VM (continuam) · ✅ app Android e página de controle (continuam)

## Fases

| Fase | O que | Pronto quando |
|---|---|---|
| 0 | Inventário e plano (este documento) | ✅ 23/10 |
| 1 | Hermes base ao lado do A0: container próprio, dados montados, modelo pelo proxy, sem canais | ✅ 23/10 (`implantar.py --hermes`; v0.22.2; respondeu a oferta e a garantia citando `Raiz/oferta.md` e a decisão 22). O uso das chamadas do Hermes entra no `uso.jsonl` desde a fase 2 |
| 2 | Plugin `agentepessoal` para o Hermes: cofre, aprovações, ferramentas dos helpers, regras no prompt, relógio | ✅ 23/10. Ponte com 22 ferramentas, vista bindfs só leitura, imagem própria, cofre (`cofre_hermes.py`). Depois: **máscara no proxy** (`/hermes/bedrock`: todo valor de qualquer cofre vira `§§secret(NOME)` em TODA chamada do Hermes, inclusive resumo da compressão e título, que não passam pelo middleware; ao vivo: um valor de teste colado na conversa → 2 chamadas, 2 mascaradas, resposta só com o nome); **uso** do `invoke` (fluxo event-stream) no `uso.jsonl` com `origem: hermes`, `api: invoke`, dono/conversa/rotina pelos cabeçalhos X-A0-* (`uso_hermes.py`); **convidados** só com uso pessoal (`acesso_hermes.py`: sem terminal, execute_code, arquivos, memória, busca nas conversas, skills, cron, navegador; só os arquivos dele); **aprovações** (`aprovacoes_hermes.py`: mesmo revisor e regras do A0 nos cliques/teclas/JS do navegador e nos conectores que escrevem; nunca = bloqueio, perguntar = portão do Hermes; liberações do Instagram/Meta/99/prospecção, "Nesta tarefa" = `session`, "Sempre" = `always` + lista do revisor; trava de vazamento; terminal fica com o smart do Hermes; ao vivo pelo `/v1/runs`: `approval.request` com `request_id` e escolhas, `deny` resolvido e o agente parou); **relógio** (`relogio_hermes.py`: 7 tarefas do `job_loop`, mesmos arquivos, só com `AGENTEPESSOAL_RELOGIO=1`, um por container); teste instável (614/615) resolvido; CI verde. Fica para a fase 6: a ponte mascarar a senha colada **antes** de mandar ao Hermes (hoje ela não chega ao modelo, mas fica no histórico salvo dele, em `/opt/hermes/data`, root 700) e a memória separada dos convidados (a do Hermes é uma só) |
| 3 | Skills e MCP (Google, GitHub) | ✅ 23/10. As 27 skills adaptadas às ferramentas do Hermes (`infra/vm/hermes/skills`: mesmo conteúdo de negócio, só o "como"; teste recusa nome de ferramenta do A0) e semeadas uma vez em `skills/agentepessoal` (depois são do curador); Hermes listou as 27 e leu a da prospecção. Conectores no container `hermes-mcp` (tokens só lá; o Hermes só tem o endereço): Google com o workspace-mcp do A0 (no ensaio tudo só leitura) e repasse do GitHub; ao vivo leu os 3 últimos e-mails (só remetente/assunto) e listou repositórios. `vision_analyze` do Hermes funciona pelo Bedrock |
| 4 | Navegador com os perfis logados (Instagram, Meta…) | ✅ 23/10. `hermes-navegador`: o Chromium 1228 do A0 com uma **cópia** do perfil `shared` (o A0 segue com o dele), CDP só na rede hermes (repasse 9223, firewall só para ele); o Hermes usa as ferramentas `browser_*` dele (não o Browser Use: cada clique passa pelas aprovações). Ao vivo: logado como @raiz.connect, leu a caixa do Direct e abriu a conversa com Mais Congelados (o único clique liberado no ensaio é abrir conversa/aba do Direct, pelo rótulo lido), nada digitado nem enviado |
| 5 | Rotinas como agendamentos do Hermes (desligados) + acordar a VM | ✅ 23/10. As 23 tarefas do A0 no cron do Hermes, pausadas (`rotinas_aplicar.py` a cada implantação: nova nasce pausada, atualizar não liga), Sonnet; bloco de tarefa agendada, correções aprovadas, portão (script do cron com `wakeAgent`), autoavaliação e resultado ao celular com as regras do A0 (`rotinas_hermes.py`); `reuniao` por cima do cron; ficha e decisões no 1º turno (`contexto_hermes.py`). As 17 ligadas rodaram uma vez à mão (`rotina_rodar.py`, sem ligar): todas terminaram, 0 erro; o que gravaria deu "ensaio: só leitura" (esperado) e o que iria ao celular ficou em `ensaio_celular.jsonl`. O despertar da VM lê o cron do Hermes (só os ativos) |
| 6 | Ponte com chave A0/Hermes; páginas (Segundo Cérebro, Painel, Tarefas, Cofre) com login próprio | ✅ 23/10. Ponte: `/var/lib/agentepessoal/destino.json` (por login; padrão A0; só `teste_hermes` no Hermes), pedido pelo `/v1/runs` na sessão `tg-<login>`, senha colada vira `§§secret` antes de sair da ponte, pedido de ok vira 3 botões que respondem o run, `teste_*` sem celular. Ao vivo pela fila do Telegram (como a função de controle): o Hermes respondeu a decisão da garantia; um `rm -rf` pediu ok → botões → "Recusar" pelo botão → não rodou. Portal (`infra/vm/portal`, 127.0.0.1:8650, mesmos logins): Segundo Cérebro (mesmo portão, Node próprio), Painel, Tarefas e Cofre (mesmos `main.html`), só leitura até a virada; conferido ao vivo. Depois: áudio (`audio_hermes.py`: o mesmo faster-whisper do A0 antes do modelo, só a pasta do celular de quem fala; ao vivo um áudio gerado pela voz da Polly foi transcrito em 6 s e respondido) e andamento editado no Telegram. Falta (⏳, ver lista): Telegram real de teste (precisa do Matheus: um bot de teste), e-mail/gatilhos, celular, delegar, memória separada dos convidados |
| 7 | Ensaio geral: um dia inteiro do Hermes "em sombra" (mesmas rotinas, saída só para o operador) | ⏳ em andamento: `hermes-sombra` desde 23/10 08:06 UTC (05:06 Bahia), cópia dos dados (`/opt/hermes/sombra`), as 17 rotinas ligadas nos horários do A0, relógio ligado (já atualizou o painel e a conferência na cópia), ensaio; para sozinho em 24/10 08:06 UTC. Conferir: `bash /opt/hermes/sombra.sh conferir` (o que rodou, o que falhou, o que teria ido ao celular). A lista de conferência ainda tem ⏳ (acima): não está toda ✅ |
| 8 | Corte (com aviso ao Matheus) | Matheus usa só o Hermes; A0 parado 7 dias |
| 9 | Limpeza: remover o A0, atualizar CLAUDE.md, CI e documentos | nada mais aponta para o A0 |

## Antes da virada (o que falta) e o plano da fase 8

**Precisa do Matheus:** (1) marcar o dia/hora da virada (proposta: um sábado de manhã, depois de uma semana sem ⏳
abaixo); (2) criar um bot de teste no BotFather e mandar o token por `/senha TG_TESTE_TOKEN …` (ou aceitar que o teste
real seja com o bot de sempre, só no login dele, na hora da virada); (3) dizer se os convidados (Ilia, Will) podem
ficar sem navegador e sem rotinas próprias na primeira semana; (4) nada de 2FA/captcha pendente hoje: o perfil do
navegador (Instagram, Google, Meta…) e o OAuth do Google já estão logados.

**Falta construir/conferir (⏳ da lista):** e-mail
para o agente e gatilhos (vigia do Google) entregues ao Hermes, ferramenta do celular (Android), `delegar` ao
OpenClaw, conversas externas pelo WhatsApp Web, memória separada dos convidados (perfis do Hermes ou bloco filtrado),
CRM na planilha, `me_mostre`, OpenCode fora do container do A0, `saude.py`/`memguard.sh`/`backup.sh` com o Hermes,
`setup.sh`/`deploy.py`, `mandar_msg.py` para o Hermes. Conferir o dia de sombra (`sombra.sh conferir`).

**Virada (um passo, reversível, com aviso ao Matheus antes):**
1. `rotinas.py`/agendador do A0: pausar as 17 rotinas ligadas (pelas APIs do agendador; anotar quais).
2. `subir.sh` sem `AGENTEPESSOAL_ENSAIO` e com `AGENTEPESSOAL_RELOGIO=1`; vista dos dados `rw`; escondidos só o que é
   de outros (convidados, delegados); rede: liberar 8789 (ponte, para mandar ao celular) e 8788 (credenciais Meta);
   navegador com o perfil `shared` de verdade (o A0 parado); Google com as permissões do A0; portal sem
   `PORTAL_SO_LEITURA`.
3. Ligar no Hermes as rotinas `ligada_no_a0` (`jobs.resume_job`, como o `sombra.sh`).
4. `destino.json`: `"padrao": "hermes"`; `report_url.py`/túnel apontando para o portal (:8650).
5. Conferir na hora: uma mensagem do Matheus pelo Telegram, um botão de ok, o resumo da manhã no dia seguinte.
6. A0: `docker stop agent-zero` (não apagar) por 7 dias.

**Voltar (minutos):** `destino.json` `"padrao": "a0"`; `docker start agent-zero`; religar as 17 rotinas do A0;
pausar as do Hermes; `subir.sh` de volta ao ensaio (`AGENTEPESSOAL_ENSAIO=1`, vista `ro`). Os dados vivos são os
mesmos dos dois lados (nada a copiar de volta), exceto o que o Hermes gravou enquanto esteve no ar, que fica válido.

## Decisões do Matheus (23/10)
1. Convidados (ilia, will) e o login da Fernanda: **continuam**.
2. Android virtual (celular, tela ao vivo): **continua**.
3. Conversas externas pelo WhatsApp Web: **continuam**.
4. Modelo: **Haiku no dia a dia, Sonnet só nas difíceis** (rotinas e tarefas longas; o roteamento por canal/tarefa do
   Hermes — `channel_overrides`, modelo por agendamento — faz isso).
5. OpenClaw como ajudante: fica como está (não muda nada para ele; a caixa de delegados continua).

## Hermes primeiro (Matheus 23/10: "tomar cuidado p alguma regra nossa, skill, sei la, n atrapalhar algo q o hermes faz bem")
Antes de levar qualquer regra, skill, ferramenta ou gancho nosso: o Hermes já faz isso? Se faz bem, fica o dele e o
nosso não entra (ou entra só o que é nosso de verdade: dados, Raiz, Segundo Cérebro, cofre por pessoa). Os testes
`test_ponte_a0.py` e `test_hermes.py` travam os casos abaixo.

| Assunto | Fica com o Hermes | Fica nosso | Por quê |
|---|---|---|---|
| Busca na web | `web_search`, `web_extract` (testado 23/10) | — (`pesquisar` saiu da ponte) | duas buscas confundem a escolha |
| Subagentes / tarefas em paralelo | `delegate_task` | `delegar` só para o OpenClaw (decisão 5) | o Hermes orquestra melhor |
| Lista de passos da tarefa | `todo_list` | `passos` sai (grava no A0) | — |
| Rotinas e lembretes com hora | `cronjob_manage` (o cron dele) | o que só nós temos (me mostre, autoavaliação, briefing de reunião) volta na fase 5 **por cima** do cron dele | `salvar_rotina`, `me_mostre`, `tarefa_limite`, `criar_gatilho`, `reuniao` gravavam no agendador do A0; `conversa_externa` abre conversa no A0 (volta na fase 6). Travas: o teste segue as chamadas de cada ferramenta e recusa uso direto do agendador/conversas do A0 (TaskScheduler, AgentContext…); as que só gravam arquivos que o A0 lê ficam fora pela lista de nomes |
| Skills | curador do Hermes (melhora e poda as sem uso) | o conteúdo das 27, **adaptado** às ferramentas dele | 19 das 27 citam ferramentas do A0; `external_dirs` é só leitura para o curador. Fase 3: cópia adaptada, semeada uma vez no espaço do Hermes; depois é dele |
| Memória curta / perfil | memória do Hermes (MEMORY/USER) | Segundo Cérebro (decisões, ficha, Pasta) é a fonte | fase 2: o gancho de captura copia para a Pasta o que o Hermes guardar, para não haver duas verdades |
| Compressão do contexto, aprovações de comando, navegador | os dele | só o cofre (§§secret), as regras de sempre e o revisor nas ações de risco | o navegador são as ferramentas `browser_*` dele, não o Browser Use (`browser_exec` faria tudo num passo só, sem o revisor ver cada clique) |
| Ler arquivo | `read_file` (texto) | `ler` (PDF, Word, planilha) | o dele não lê esses formatos |
| Imagem / vídeo | `vision_analyze` (funciona pelo Bedrock, 23/10), `video_analyze` | `analisar_imagens` (lotes) e `assistir_video` (vídeo pelo Pegasus) | as skills mandam `vision_analyze` para uma imagem |
| Persona | `SOUL.md` curto (só regras que valem sempre) | — | regra longa no prompt atrapalha o Haiku |

### Ensaio até a virada
Até a fase 8 o Hermes **vê os dados do A0 só para leitura** (`ro` em `agentepessoal-hermes-dados.service`): lê tudo
(relatórios, fios, decisões, Pasta) e não grava nada em que o A0 aja. Liberar um post, registrar uma iniciativa ou um
rascunho, revisar os temas: pelo Hermes dá "ensaio: só leitura" e continua com o A0 (revisão OpenCode 23/10: um post
liberado pelo Hermes seria publicado pelo A0). O livro de ações (SQLite) não abre só para leitura: fica sem ele no
ensaio. Na fase 7 (dia de sombra) o Hermes roda numa cópia dos dados, gravando nela.
Além disso, `AGENTEPESSOAL_ENSAIO=1` (`subir.sh`): **nada vai ao celular de ninguém e nada se publica
na Meta** pelas ferramentas. E, para que nem um terminal do Hermes aja por fora delas:
- rede própria `hermes` (`firewall.sh`): internet e, do host, só o proxy do modelo (8787); nada do A0, da VPC, do
  serviço de credenciais (8788), da ponte do celular (8789), das caixas nem dos metadados da nuvem;
- aparecem vazios no container: `.env`, `secrets.env`, `settings.json`, `usuarios.json*` (chaves e login do A0),
  `.aws`, `whatsapp` (chave da ponte), `segredos` (cofre), `navegador*` (perfis logados), `mcp` (tokens dos conectores),
  `celular`, `delegados`.
Na virada, rede e escondidos voltam ao que o Hermes precisa de fato (fase 6/8), com a mesma conferência. O
`subir.sh` só sobe o Hermes se os plugins no ar já têm a trava. Cofre vazio no ensaio = nenhuma senha usável por ele
(a fase 4 testa o navegador pelo perfil já logado, sem senha) (botões de fios, iniciativa, rascunho, prospecção…). O que iria fica
em `/opt/hermes/data/agentepessoal/ensaio_celular.jsonl` para o operador conferir, sem fila de reenvio nem marca de
aviso em `/a0/usr` (o A0 mandaria depois, ou seguraria o dele). Na virada (fase 8) a variável sai e a ponte do celular
passa a entregar as respostas dos botões ao Hermes (fase 6). Pendente da fase 4: o navegador do Hermes logado no
Instagram também precisa respeitar o ensaio (Direct da prospecção).

Fases 2–4 acrescentaram (23/10): o navegador só lê (`acesso_hermes.py`: abrir, ler, rolar, voltar, ver; o único clique
é abrir uma conversa/aba da caixa do Direct pelo rótulo lido na página; nada de digitar, teclar, JS ou CDP) e o
terminal/código não fala com o navegador por fora (CDP, devtools, Playwright); o perfil do navegador é uma cópia; o
Google do Hermes só lê; o relógio fica desligado (as tarefas de fundo seguem com o A0). Conferência ao vivo a qualquer
hora: `python3 infra/operador/hermes_ao_vivo.py travas|cofre|ferramentas|perguntar|run`.

Conferido ao vivo em 23/10, de dentro do container: só o proxy do modelo (8787) e a internet abertos (8788, 8789, 8791,
SSH, o A0 e os metadados fechados); `.env`, `settings.json`, `usuarios.json*`, a chave da ponte, o cofre, os perfis do
navegador e `.aws` vazios; gravar em `/a0/usr` dá "Read-only file system"; um `whatsapp_enviar` pedido ao Hermes ficou
só na caixa do ensaio (nada no celular nem na fila de reenvio do A0).

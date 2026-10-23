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

### Plugins (49)
- [ ] prospeccao (P) — o maior ativo; ferramenta + navegador logado + CRM + rodadas
- [ ] conteudo (P) — publicação na hora certa (relógio), semana, stories, crítico/designer
- [ ] especialistas (P) · [ ] concorrentes (P) · [ ] painel (P + página) · [ ] quadro (P + página)
- [ ] cerebro (P) · [ ] segundo_cerebro gateway (P: portão próprio) · [ ] memoria_pessoal (P/H)
- [ ] fios_soltos (P) · [ ] iniciativa (P) · [ ] auxiliar (P) · [ ] radar (P) · [ ] canais (P/H)
- [ ] aprovacoes (P) · [ ] cofre (P) · [ ] login_usuarios (P/D) · [ ] whatsapp (P: destino da ponte, avisos, IMAP, gatilhos)
- [ ] conectores (H) · [ ] central/livro (P) · [ ] rotinas: salvar_rotina, me_mostre, portão, autoavaliação (P/H)
- [ ] agenda_confiavel (P: validade das tarefas) · [ ] aprendizado (H: revisão de skills do Hermes)
- [ ] pesquisa (P: precisa do SearXNG fora do container do A0) · [ ] video (P) · [ ] analisar_imagens (P/H)
- [ ] ler_arquivo (H) · [ ] consultar_sol (P) · [ ] objetivo_vivo (P) · [ ] celular_rapido (P/D) · [ ] celular_tela (D)
- [ ] conversas_externas (P/D) · [ ] arquivo_grande (P: entrada por S3) · [ ] agent_delegates (D: OpenClaw fica?)
- [ ] limpeza (N/P: abas e /tmp) · [ ] navegador_por_pessoa (P) · [ ] navegador_visual (D)
- [ ] acoes_paralelas, cache_prompt, controle_agente, estilo_claude, interface_celular, navegador_rapido,
      prompt_enxuto, resultados_grandes, resumo_seguro (N) — **mas** as regras de `_12_regras_base` e
      `_60_conversa_whatsapp` vão para o prompt do Hermes
- [ ] nexos_ads_campaign3_fixed (D: descartar)

### Rotinas
- [ ] 💡 Iniciativa · [ ] 🗓️ Semana de posts · [ ] 🔎 Radar e fios soltos · [ ] ✍️ Meu estilo de escrita
- [ ] 📣 Raiz fechamento do dia · [ ] PayGo chamado · [ ] 🗓️ Raiz revisão do mês · [ ] 📈 Raiz números da semana
- [ ] 🗓️ Revisão da semana · [ ] Radar semanal de IA · [ ] 📰 Resumo do dia · [ ] 🫂 Te conhecer
- [ ] 🔭 Concorrentes semana · [ ] desligadas: 🧵 Fios soltos, Nexos fase 2, iFood chamado (migram desligadas)
- [ ] 🎯 prospecção: buscar, executar, resumo do dia · [ ] briefing/pós-reunião · [ ] painéis vivos · [ ] portão e correções por rotina

### Skills (27 em `/a0/usr/skills`)
- [ ] as 5 do git (celular, manutencao-maquina, pedidos-knauf-claude, piloto-rapido, prospeccao-instagram)
- [ ] as 22 da VM (análise de métricas, calculadora, conta em redes, consultas rápidas, e-mail Outlook, formulários
      de portais, Direct no navegador, landing, login em sites, logs iFood, bom dia/radar, leitura e rolagem,
      orquestrar, pesquisa de concorrentes, leads locais, posts/carrossel, pedidos avulsos, rascunho de mensagens,
      relatório de concorrentes, respostas do Segundo Cérebro, status de homologação, teste do produto)

### Serviços do servidor
- [ ] proxy de modelo (fica) · [ ] ponte (muda o destino) · [ ] credenciais Meta/voz (fica) · [ ] caixas de convidados e delegados
- [ ] túnel e URL do agente (`report_url.py`: túnel próprio para o Hermes e as páginas)
- [ ] `proximo_despertar.py` · [ ] `saude.py` · [ ] `watchdog.sh` · [ ] `memguard.sh` · [ ] `backup.sh` (+ dados do Hermes)
- [ ] `entrada.sh` · [ ] `firewall.sh` (portas novas) · [ ] `setup.sh` / `deploy.py` (instalação do Hermes)
- [ ] Android virtual e ws-scrcpy (D) · [ ] SearXNG fora do container do A0 · [ ] OpenCode e Claude Code CLI fora do container

### Dados e logins (não podem se perder)
- [ ] `/opt/a0/usr` inteiro montado no Hermes · [ ] `scheduler/tasks.json` convertido · [ ] `agenda/limites.json`
- [ ] perfis do navegador (Instagram, Google, Meta, claude.ai, Hotmail, iFood, 99Food, WhatsApp Web)
- [ ] OAuth do workspace-mcp · [ ] cofre e `.descricoes` · [ ] conversas antigas (exportar para busca)
- [ ] `/var/lib/agentepessoal/*` · [ ] configs vivas (MCP GitHub, presets, regras "Sempre permitir")

### Operador e CI
- [ ] `implantar.py` com destino Hermes · [ ] `rotinas.py` para os agendamentos do Hermes · [ ] `mandar_msg.py`/`ver_chat`
- [ ] `falhas_do_dia.py` (conserto noturno) · [ ] `revisar_opencode.py` · [ ] hooks do Cérebro (`.claude/hooks`)
- [ ] **OpenCode 2 + Ponytail** (revisor obrigatório antes de implantar, decisão #35; usado no conserto noturno): hoje
      vive na camada do container do A0 (`/root/.config/opencode`, Claude Code CLI apontado para `/bedrock`) e some
      com ele. Ganha casa própria (container ou host, versão fixa, mesma config e modelos Claude 5.5 pelo proxy) e o
      `revisar_opencode.py` passa a apontar para lá **antes** de qualquer desligamento do A0.
- [ ] CI (`.github/workflows/testes.yml`) · [ ] `CLAUDE.md` e `docs/HANDOFF_CONTA_NOVA.md`

### Fora da AWS / feitos à mão
- [ ] Apps Script `vigia_google.gs` (aponta para o gatilho) · [ ] conserto noturno (sessão do Claude Code)
- [ ] snapshot DLM e alarme de VM travada (continuam) · [ ] app Android e página de controle (continuam)

## Fases

| Fase | O que | Pronto quando |
|---|---|---|
| 0 | Inventário e plano (este documento) | ✅ 23/10 |
| 1 | Hermes base ao lado do A0: container próprio, dados montados, modelo pelo proxy, sem canais | responde pelo API server com o Segundo Cérebro no contexto ✅ 23/10 (`implantar.py --hermes`; v0.22.2; respondeu a oferta e a garantia citando `Raiz/oferta.md` e a decisão 22). Falta: o proxy registrar o uso das chamadas do Hermes (caminho `invoke` do Bedrock não entra no `uso.jsonl`) |
| 2 | Plugin `agentepessoal` para o Hermes: cofre, aprovações, ferramentas dos helpers, regras no prompt, relógio | suítes dos plugins passando no Hermes; cada ferramenta chamada uma vez. Feito 23/10: ponte com 35 ferramentas (leu os temas e os 22 fios reais sem mexer), vista bindfs com trava repassada, imagem própria com os pacotes dos helpers, cofre (`cofre_hermes.py`: valor só nas ferramentas que agem e só em sessão com dono no mapa; máscara com todos os cofres no resultado e no pedido ao modelo). Falta: conferir se as chamadas internas do Hermes (resumo da compressão, título) passam pela máscara; senha colada fica sem máscara no histórico salvo do Hermes (a ponte já apaga o `/senha`); **convidados sem `terminal`/`execute_code` do Hermes** (só o `terminal_isolado`, como no A0: o terminal comum lê `/a0/usr/segredos` de todos — fase 6); aprovações; relógio |
| 3 | Skills e MCP (Google, GitHub) | as 27 skills listadas e usadas; Gmail lido |
| 4 | Navegador com os perfis logados (Instagram, Meta…) | Hermes abre o Instagram logado e lê um Direct sem enviar |
| 5 | Rotinas como agendamentos do Hermes (desligados) + acordar a VM | cada rotina rodada uma vez à mão, resultado só para o operador |
| 6 | Ponte com chave A0/Hermes; páginas (Segundo Cérebro, Painel, Tarefas, Cofre) com login próprio | operador conversa com o Hermes pelo Telegram de teste |
| 7 | Ensaio geral: um dia inteiro do Hermes "em sombra" (mesmas rotinas, saída só para o operador) | lista de conferência toda ✅ |
| 8 | Corte (com aviso ao Matheus) | Matheus usa só o Hermes; A0 parado 7 dias |
| 9 | Limpeza: remover o A0, atualizar CLAUDE.md, CI e documentos | nada mais aponta para o A0 |

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
| Compressão do contexto, aprovações de comando, navegador | os dele | só o cofre (§§secret) e as regras de sempre | — |
| Ler arquivo | `read_file` (texto) | `ler` (PDF, Word, planilha) | o dele não lê esses formatos |
| Imagem / vídeo | `vision_analyze`, `video_analyze` | `analisar_imagens`, `assistir_video` por enquanto | conferir na fase 3 se os dele funcionam pelo Bedrock; se sim, os nossos saem |
| Persona | `SOUL.md` curto (só regras que valem sempre) | — | regra longa no prompt atrapalha o Haiku |

### Ensaio até a virada
Até a fase 8 o Hermes **vê os dados do A0 só para leitura** (`ro` em `agentepessoal-hermes-dados.service`): lê tudo
(relatórios, fios, decisões, Pasta) e não grava nada em que o A0 aja. Liberar um post, registrar uma iniciativa ou um
rascunho, revisar os temas: pelo Hermes dá "ensaio: só leitura" e continua com o A0 (revisão OpenCode 23/10: um post
liberado pelo Hermes seria publicado pelo A0). O livro de ações (SQLite) não abre só para leitura: fica sem ele no
ensaio. Na fase 7 (dia de sombra) o Hermes roda numa cópia dos dados, gravando nela.
Além disso, `AGENTEPESSOAL_ENSAIO=1` (`subir.sh`): **nada vai ao celular de ninguém e nada se publica
na Meta** por ele, mesmo que uma ferramenta tente (botões de fios, iniciativa, rascunho, prospecção…). O que iria fica
em `/opt/hermes/data/agentepessoal/ensaio_celular.jsonl` para o operador conferir, sem fila de reenvio nem marca de
aviso em `/a0/usr` (o A0 mandaria depois, ou seguraria o dele). Na virada (fase 8) a variável sai e a ponte do celular
passa a entregar as respostas dos botões ao Hermes (fase 6). Pendente da fase 4: o navegador do Hermes logado no
Instagram também precisa respeitar o ensaio (Direct da prospecção).

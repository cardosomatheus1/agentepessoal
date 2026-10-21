# Auditoria de maturidade: o que Hermes e OpenClaw fazem que o nosso agente (A0 + plugins) não faz

Data: 21/10/2026. Só leitura; nada foi alterado.

**Fontes lidas:**
- **A0 (núcleo):** a cópia em `scratchpad/a0src`. O `_time_travel` não está nessa cópia, mas existe na VM (o `limpeza` mexe nele). Onde a VM pode estar diferente, marquei "conferir na VM".
- **Nossos plugins:** `infra/vm/plugins`, até o commit `16b06d6` (21/10 12:57), que outra sessão fez durante esta auditoria. Ele já trouxe o catálogo de erros do OpenClaw, a regra "insista" e a conferência do que foi digitado.
- **Hermes:** `/home/user/nousresearch/hermes-agent` @ `5575a085` (14/10).
- **OpenClaw:** `/home/user/openclaw` @ `598e945b` (20/10).

Caminhos curtos usados nas tabelas:
- **A0:** `a0src/…`
- **Nossos:** `plug/<plugin>/…` (= `infra/vm/plugins`)
- **Hermes:** `H:…` (a partir de `hermes-agent/`)
- **OpenClaw:** `OC:…`. Os do navegador ficam em `OC:ext/browser/…` (= `extensions/browser/src/…`)

Legenda: **Impacto** na autonomia (alto/médio/baixo). **Porte** do port: P (até 1 dia, um plugin), M (2 a 4 dias), G (uma semana ou mais).

---

## 1. Resumo em 10 linhas

1. **Já está bom ou portado:**
   - reparo e validação de argumentos;
   - esquema real das ferramentas;
   - ferramentas sob demanda;
   - ações em paralelo;
   - compactação com memória antes do resumo;
   - resultado repetido virando referência;
   - saída grande em arquivo;
   - revisão de skills;
   - alvo visível, print após a ação, download com o nome real e upload em campo escondido;
   - erros do navegador que ensinam o próximo passo, e o campo lido de volta depois de digitar (commit `16b06d6`).
2. **Maiores buracos que ainda travam tarefas reais:**
   - (a) o navegador **não trata diálogos JS** (confirm/alert): o Playwright os fecha sozinho, e "Excluir? OK" vira "Cancelar" sem ninguém saber;
   - (b) **não existe espera** por texto, elemento ou URL;
   - (c) o **detector de laço pausa a tarefa na 4ª repetição**, o que pega quem está esperando uma página carregar;
   - (d) o terminal **não mostra o código de saída** do comando;
   - (e) a **leitura de planilha** traz só 80 linhas × 30 colunas, e com fórmulas em vez de valores;
   - (f) **ninguém confere de fora** se o pedido foi cumprido antes do "pronto";
   - (g) não há **troca de modelo** quando o modelo falha, nem **recuperação de estouro de contexto**.
3. Os itens 1 a 9 da fila (seção 4) são quase todos pequenos e tiram o agente de travas bobas. Os maiores (juiz de conclusão, print com rótulos, troca de modelo) vêm depois.

---

## 2. Matriz completa

### 2.1 Navegador

| Capacidade | Hermes (arquivo:linha — como) | OpenClaw (arquivo:linha — como) | A0 hoje (presente/parcial/ausente — onde) | Impacto | Porte | Já portado? |
|---|---|---|---|---|---|---|
| Leitura da página com refs | `H:tools/browser_tool.py:495` — snapshot da árvore de acessibilidade, refs `@eN`; o navigate já devolve snapshot | `OC:ext/browser/browser-tool-description.ts:99-104` — snapshot `role`/`aria`, refs estáveis, `[new]` nos elementos que acabaram de aparecer, filtro `query` | Presente — `a0src/plugins/_browser/helpers/runtime.py:1682` (`content`) + texto da página em todo passo (`_browser/extensions/python/message_loop_prompts_after/_20_browser_context.py`) | — | — | Sim (corte de 20 mil caracteres no `navegador_rapido`) |
| Página grande: texto completo salvo em arquivo | `H:tools/browser_tool_snapshot.py:69` — corta a 15 mil caracteres e grava a página inteira num arquivo, com o caminho | — | Parcial — `plug/navegador_rapido` corta a 20 mil e manda usar `content` com `selector`; não grava arquivo | baixo/médio | P | Não |
| Marcar o que é novo (`[new]`) e filtrar (`query`) | — | `OC:ext/browser/browser-tool-description.ts:100,108` | Ausente | baixo/médio | M | Não |
| Diálogos JS (alert/confirm/prompt/beforeunload) | `H:tools/browser_dialog_tool.py:17` + `H:tools/browser_supervisor_dialogs.py:174` — guarda o diálogo em `pending_dialogs`; o agente aceita ou recusa | `OC:ext/browser/browser/pw-session-dialogs.ts:102` (`observeDialog`) + `pw-tools-core.downloads.ts:270` (`armDialog`) — ação `dialog`: aceitar, recusar ou deixar a resposta "armada" antes do clique | **Ausente**: não há `page.on("dialog")` em `_browser` nem nos plugins. O Playwright fecha o diálogo sozinho, então um `confirm()` volta `false` e a ação some sem aviso | **alto** | M | Não |
| Esperar por texto, elemento, URL ou carga | Ausente (só o `wait_for_load()` do `browser_exec`, `H:tools/browser_use_cli.py:841`) | `OC:ext/browser/browser/pw-tools-core.interactions.content.ts:146` — `act:wait` com `text`, `textGone`, `selector`, `url`, `loadState`, `fn` e timeout | **Ausente** — `runtime.py:2830` (`_settle`) espera só `domcontentloaded` por 1 a 5 s; a ferramenta `wait` só dorme | **alto** | P | Não |
| Print com rótulos (número da ref desenhado sobre o elemento) | `H:tools/browser_tool.py:1257` — `browser_vision(annotate=true)` desenha `[N]` = `@eN` | `OC:ext/browser/browser/pw-tools-core.interactions.content.ts:380` + `screenshot-annotate.ts` | Ausente — o print automático (`plug/navegador_rapido/helpers/ver_tela.py`) dá coordenadas, mas não liga a imagem às refs | médio/alto | M | Não (só o print sem rótulo) |
| Print depois de cada ação | Sob pedido (`browser_vision`) | Sob pedido | Presente (nosso) — `ver_tela.py` (AGEM, ORIENTACAO) | — | — | Sim |
| Erros do console e falhas de rede | `H:tools/browser_tool.py:601` (`browser_console`: logs, exceções JS, `expression`) | Ações `console`, `requests`, `errors` — `OC:ext/browser/browser-tool-action-facts.ts:25-27` | Ausente: nenhum `console`/`requestfailed` em `_browser`. "Cliquei e nada aconteceu" não tem diagnóstico | médio | P | Não |
| Erros que dizem o próximo passo | `H:agent/tool_guardrails.py:577` (dica genérica de recuperação) | `OC:ext/browser/browser/pw-tools-core.shared.ts:58-137` (`toAIFriendlyError`) | Presente (nosso, 21/10) — `plug/controle_agente/helpers/clique.py` (OUTROS). **Falta:** "cannot select options on <div>" (lista suspensa que não é `<select>`) e "helper-backed reference" (iframe), em `a0src/plugins/_browser/assets/browser-page-content.js:2507,2569,2694` | médio | P | Sim, em parte |
| Lista suspensa | Ausente (só clicar e digitar) | `selectOptionViaPlaywright` (`pw-tools-core.interactions.actions.ts:159`), só `<select>` nativo | Presente para `<select>` nativo — `runtime.py:2567`; as listas feitas em JS seguem as LICOES (`ver_tela.py`) | baixo | P (dica) | Sim, em parte |
| Upload | Ausente no núcleo (só via CDP) | `OC:ext/browser/browser/pw-tools-core.downloads.ts:256-268` — **arma o seletor de arquivo** e clica no gatilho na mesma chamada; também `inputRef` | Parcial — `runtime.py:2612` exige um `<input type=file>`; o nosso Fix 6 (`plug/navegador_rapido/helpers/correcoes.py:297`) cobre o campo escondido. **Falta** o seletor aberto por clique, quando o site cria o input na hora (`filechooser`) | médio | P | Em parte (campo escondido sim; seletor de arquivo não) |
| Download | — | `pw-tools-core.downloads.ts:310,361` — `waitfordownload` e `download` (clica e salva) | Presente — `runtime.py:1169` aceita downloads; o Fix 5 copia com o nome real e avisa | — | — | Sim |
| Abas e popups | Uma aba por sessão | `tabs`, `focus`, `close` | Presente — `open`/`list`/`set_active`/`close`, `focus_popup` (`runtime.py:1854`) | — | — | — |
| Iframes | `H:tools/browser_supervisor_frames.py:1` — árvore de frames e CDP por `frame_id` | `OC:ext/browser/browser/pw-role-snapshot-capture.ts:129` — snapshot entra nos frames | Parcial — `browser-page-content.js:484,1566` (refs com frame-chain); clicar funciona, mas **select e upload falham** em ref de iframe ("helper-backed", `:2569,:2694`) | médio/baixo | M | Não |
| Formulário inteiro numa chamada | — | `act:fill` com lista de campos (`pw-tools-core.interactions.actions.ts:230`) | Presente — `multi` (`runtime.py:1389`) | — | — | — |
| Conferir o que foi digitado | — | — | Presente (nosso, 21/10) — Fix 7 `conferir_digitado` (`correcoes.py:335`) | — | — | Sim (nem eles têm) |
| Login com cofre sem o modelo ver a senha | `H:tools/browser_vault_tool.py:399` (`browser_vault_fill`), `:334` (código) | `buildCredentialSafetyPrompt` | Presente — `§§secret(NOME)` (`a0src/helpers/secrets.py`) + `plug/cofre` + `pedir_codigo` | — | — | — |
| Salvar a página em PDF; emular aparelho | — | `pdf`, `emulate` (`browser-tool-action-facts.ts:29,31`) | Ausente (`set_viewport` existe) | baixo | P | Não |
| CDP cru | `H:tools/browser_cdp_tool.py:325` | `evaluate` | Parcial — `evaluate` (`runtime.py:1729`) | baixo | — | — |

### 2.2 Arquivos e anexos

| Capacidade | Hermes | OpenClaw | A0 hoje | Impacto | Porte | Já portado? |
|---|---|---|---|---|---|---|
| Ler XLSX inteiro, com valores | `H:tools/read_extract.py:497-560` — lê o valor calculado (`<v>`), até 5.000 linhas e 256 colunas por aba, pula abas escondidas, e o `read_file` pagina (`H:tools/file_tools.py:606,653`) | — | **Parcial e fraco** — `a0src/plugins/_office/helpers/artifact_editor.py:412-418`: `data_only=False` (vêm as **fórmulas**, não os valores), **80 linhas × 30 colunas × 8 abas**, corte de 12 mil caracteres (`:49`) e nenhum jeito de ler o resto | **alto** | P | Não |
| Ler DOCX | `H:tools/read_extract.py:474` | — | Presente — `artifact_editor.py` (`_read_docx`) e `document_query` | — | — | — |
| Ler PDF (aviso de página escaneada, OCR) | `H:tools/read_extract.py:291` (avisa quais páginas não têm texto e dá o comando `pdftoppm`), `:197` (OCR) | `OC:src/agents/tools/pdf-tool.ts:103,145` — **PDF nativo** para Anthropic/Google, `pages`, `password` | Parcial — `document_query` (liteparse/unstructured, OCR automático; `a0src/plugins/_document_query/helpers/parsers/liteparse.py:124`). Pede antes carregar a skill e responde por um modelo (resumo, não o texto cru). Não manda PDF nativo ao Claude. Conferir na VM se o liteparse está instalado | médio | M | Não |
| Anexo que chega pelo celular | A plataforma entrega o arquivo | Mídia como anexo | Presente — `plug/whatsapp/api/receber.py:297-339` (anexos → `UserMessage.attachments`) | — | — | — |
| Enviar arquivo ao dono | `send_message` com `MEDIA:` | `message(action=send)` | Presente — `whatsapp_enviar` | — | — | — |
| Ler e editar texto com linhas, aviso de leitura velha | `H:tools/file_tools.py:606` + `H:tools/file_state.py` | `apply-patch.ts` | Presente — `_text_editor` (patch, `patch_stale_read`) | — | — | — |
| Busca em arquivos | `search_files` (rg) | `glob`/`grep` | Parcial — pelo terminal | baixo | P | Não |

### 2.3 Terminal e código

| Capacidade | Hermes | OpenClaw | A0 hoje | Impacto | Porte | Já portado? |
|---|---|---|---|---|---|---|
| Código de saída de cada comando | `H:tools/terminal_tool_result.py:258` (`exit_code` em todo resultado), `:92` (o que o código quer dizer; sinal 137 = morto) | `OC:src/agents/bash-tools.exec-output.ts:26-32` | **Ausente** — `a0src/plugins/_code_execution/tools/code_execution_tool.py:333` só mostra o código quando o **shell** morre; um comando que falha sem imprimir nada parece sucesso | **alto** | M | Não |
| Dica pelo texto do erro | `H:tools/terminal_hints.py:46` ("command not found", `python` → `python3`, pip etc.) | — | Ausente (o prompt geral fala em "adaptar") | médio | P | Não |
| Processo em segundo plano com aviso ao terminar | `H:tools/process_registry.py:584` (`notify_on_complete`, `watch_patterns`), `H:tools/terminal_tool.py:164` | `OC:src/agents/bash-tools.schemas.ts:37-51` (`yieldMs`, `background`) + `bash-tools.exec-notify.ts` | Parcial — `parallel` com `wait:false` + `await` (`a0src/prompts/agent.system.tool.parallel.md`); não avisa sozinho quando acaba | médio | M | Não |
| Script que chama as ferramentas do agente (lote) | `H:tools/code_execution_tool.py:1-12,43` — `execute_code`: um script Python chama `web_search`, `read_file` etc. por RPC, e só o resultado volta ao modelo | `OC:src/agents/code-mode.ts` (code mode) | Ausente — o Python do A0 não enxerga as ferramentas do agente | médio/alto (lotes: 30 leads, 50 páginas) | G | Não |
| Tempo limite e devolução do controle | Foreground com timeout; o que é longo vai para segundo plano | `yieldMs` | Presente — `_code_execution/default_config.yaml` (30/15/240 s) + `fw.code.max_time.md` | — | — | — |

### 2.4 Erros, novas tentativas, laços e travamento

| Capacidade | Hermes | OpenClaw | A0 hoje | Impacto | Porte | Já portado? |
|---|---|---|---|---|---|---|
| Detector de laço: limites | `H:agent/tool_guardrails.py:120-133` — aviso na 2ª/3ª repetição. Parada dura **só fora da conversa** (rotina/gateway) e só na 5ª falha exata ou 8ª da mesma ferramenta; na conversa, só avisa (`_ATTENDED_PLATFORMS`, `:84`) | `OC:src/agents/tool-loop-detection.ts:57-59,540` — aviso na 10ª, bloqueio na 20ª, disjuntor na 30ª | **Agressivo demais** — `plug/controle_agente/extensions/python/tool_execute_after/_10_detector_loop.py:17-19`: avisa na 2ª e **pausa a tarefa na 4ª** (e a pausa espera a pessoa). Ficam de fora só `response` e `wait` | **alto** | P | Em parte (o detector existe; os limites não são os deles) |
| Consulta repetida que é espera legítima (polling) | `STALL_GUARD_REPEATABLE_TOOLS` + sufixos `_poll`/`_get_result` (`tool_guardrails.py:35-37`) | `isKnownPollToolCall`, limite próprio (`tool-loop-detection.ts:572-597`) | Ausente — `content`, `state` e `runtime=output` repetidos enquanto a página ou o comando terminam contam como laço | **alto** | P | Não |
| Laço alternado (A,B,A,B) e argumentos que mudam sem avanço | Ciclos de período até 4 (`tool_guardrails.py:39-46,491`) | ping-pong e "argument churn" (`tool-loop-detection.ts:485,540`; `tool-loop-argument-churn.ts:53`) | Parcial — aviso na 3ª falha seguida da mesma ferramenta (`plug/controle_agente`, `_12_guardas.py`); ciclo A/B não é pego | médio | P | Não |
| Ferramenta que não existe, chamada várias vezes | — | `UNKNOWN_TOOL_THRESHOLD` (`tool-loop-detection.ts:57,557`) | Parcial — `fw.tool_not_found.md` + o `ferramentas_extras` sugere a mais parecida | baixo | — | — |
| Novas tentativas do modelo (backoff, Retry-After) | `H:agent/retry_utils.py` (jitter, `Retry-After`, `:30`) + `H:agent/error_classifier.py:34-66` (cada erro diz o que fazer) | `OC:src/agents/failover/classify.ts` | Parcial — `a0src/models.py:576-648` (2 tentativas, 1,5 s fixo); o proxy tenta mais 1 vez (`infra/vm/bedrock_proxy.py:509`); `_error_retry` 1 vez; o `limpeza` refaz a rodada em 5/15/30 min | médio | P | Em parte |
| **Troca de modelo quando falha** | `H:agent/chat_completion_helpers.py:2086` (`try_activate_fallback`) + `H:agent/agent_init_fallback.py` (cadeia), `fallback_cooldown.py` | `OC:src/agents/model-fallback-runner.ts:138`, `model-fallback-candidates.ts:197` | **Ausente** — não há troca de modelo durante a tarefa (`consultar_sol` só aconselha) | médio | M | Não |
| **Estouro de contexto → resumir e tentar de novo** | `H:agent/turn_overflow.py:1-8,149` + `error_classifier.py:46-47` | `OC:src/agents/embedded-agent-runner/compact-reasons.ts` (compacta por `overflow`) | **Ausente** — nada em `a0src` trata "prompt is too long"; o resumo do A0 só age antes | médio | M | Não |
| Resposta vazia ou só raciocínio | `H:agent/empty_response_guard.py` | — | Presente — `a0src/prompts/fw.msg_empty_response.md`, `fw.msg_reasoning_only.md` | — | — | — |
| Retomar depois de reinício | `H:agent/turn_recovery*.py` | `OC:src/agents/restart-recovery-prompt.ts` | Presente — `plug/whatsapp` (`_56_retomar_pedido.py`) + `plug/limpeza` | — | — | Sim |
| Teto de passos | `H:agent/iteration_budget.py` | budget de tokens no goal | Presente — ajudante 40 / rodada 30, com aviso (`plug/controle_agente`) | — | — | Sim |

### 2.5 Plano, conclusão e verificação

| Capacidade | Hermes | OpenClaw | A0 hoje | Impacto | Porte | Já portado? |
|---|---|---|---|---|---|---|
| Lista de passos que sobrevive ao resumo | `H:tools/todo_tool.py:1-22,102` (reinjetada depois da compactação) | `progress-card-tool.ts:31` | Presente — `plug/objetivo_vivo` (`passos`), mas **não roda em rotinas nem em ajudantes** | baixo/médio | P | Sim (só na conversa) |
| **Juiz independente do "pronto"** | `H:hermes_cli/goals.py:1-7,113,894` — depois de cada turno, outro modelo diz se o objetivo foi cumprido; senão o agente continua. Portões de verdade por comando (`:48`) | `create_goal`/`update_goal` (`OC:src/agents/tools/goal-tools.ts:86,112`) + "Final claim needs evidence" (`system-prompt.ts:619`) | Parcial — `_goal` (`a0src/plugins/_goal/tools/response.py:13-25`): o **próprio agente** decide quando acabou, e só com goal ligado. Fora disso, só a regra "confira o efeito real" (`plug/prompt_enxuto/.../_12_regras_base.py:24`). A autoavaliação (`plug/rotinas/helpers/autoavaliacao.py`) só existe nas rotinas e só propõe melhoria | **alto** | M | Não |
| Lembrete "editou e não conferiu" | `H:agent/verification_stop.py:160` + `turn_stop_gates.py` (só código) | — | Ausente | baixo (código) | P | Não |
| Regras de execução no prompt (contas e datas por ferramenta; ler de volta depois de escrever fora; total declarado = total contado; não "consertar" ids; agir em vez de perguntar) | `H:agent/prompt_builder.py:436-517` (`OPENAI_MODEL_EXECUTION_GUIDANCE`), `:347`, `:386` | `OC:src/agents/system-prompt.ts:612-620` ("Execution Bias") + `promised-work-prompt.ts:2-12` ("Promised Work") | Parcial — `_12_regras_base.py:23` ("Insista até terminar", 21/10) e `a0src/prompts/agent.system.main.solving.md`. **Faltam:** ferramenta obrigatória para contas, datas e contagens; ler de volta o que escreveu num sistema de fora; total declarado contra o contado; "promessa de fazer depois = fazer agora" | **alto** (o modelo é o Haiku) | P | Em parte |
| Perguntar com opções sem perder a tarefa | `H:tools/clarify_tool.py:136` (até N perguntas com escolhas, espera com prazo, a tarefa continua) | `OC:src/agents/tools/ask-user-tool.ts:457` | Parcial — `response` encerra o turno e a resposta chega como mensagem nova (o `objetivo_vivo` guarda o pedido); só há botões para aprovações, código e rotinas | médio | M | Não |

### 2.6 Ajudantes e delegação

| Capacidade | Hermes | OpenClaw | A0 hoje | Impacto | Porte | Já portado? |
|---|---|---|---|---|---|---|
| Ajudante e ajudantes em paralelo | `H:tools/delegate_tool.py:696` (`delegate_task`, `tasks` em lote) | `OC:src/agents/tools/sessions-spawn-tool.ts:311`, `agents-wait-tool.ts:343` | Presente — `call_subordinate` + `parallel` (`a0src/prompts/agent.system.tool.parallel.md`), `delegar` (Hermes/OpenClaw em caixa isolada) | — | — | Sim |
| Contrato de saída do ajudante (esquema + 1 nova tentativa) | `H:tools/delegation_output_schema.py:1-8` | — | Ausente | baixo/médio | P | Não |
| Mensagem para o ajudante em andamento | steer (`_merge_late_steer`) | `sessions-send-tool.steering.ts` | Presente — `plug/controle_agente` (`_10_encaminhar_subagente.py`) | — | — | Sim |

### 2.7 Memória, skills e contexto

| Capacidade | Hermes | OpenClaw | A0 hoje | Impacto | Porte | Já portado? |
|---|---|---|---|---|---|---|
| Memória do dono e busca em conversas antigas | `H:tools/memory_tool.py`, `session_search_tool.py` | `memory-search.ts` | Presente — `plug/memoria_pessoal` (ficha, `lembrar` FTS5), `cerebro` | — | — | Sim |
| Aprender skills | `H:agent/background_review.py`, `curator.py` | `skill-workshop-tool.ts:75` | Presente — `plug/aprendizado`, `salvar_rotina` | — | — | Sim |
| Compactação com memória antes do resumo; âncoras | `H:agent/context_compressor*.py` | `OC:src/agents/compaction.ts:72`, `agent-tools.memory-flush.ts:17` | Presente — `plug/resumo_seguro` | — | — | Sim |
| Resultado grande em arquivo; repetido vira referência | `H:tools/tool_result_storage.py`, `tool_guardrails.py:47-50` | `tool-result-limits.ts` | Presente — `plug/resultados_grandes`, `controle_agente` | — | — | Sim |
| Ferramentas sob demanda | `H:tools/tool_search.py` | `tool-search*.ts` | Presente — `plug/prompt_enxuto` (`ferramentas_extras`) | — | — | Sim |

### 2.8 Aprovações, segurança e o que bloqueia demais

| Capacidade | Hermes | OpenClaw | A0 hoje | Impacto | Porte | Já portado? |
|---|---|---|---|---|---|---|
| Revisor de risco antes da ação | `H:tools/approval_smart.py:1-30` (modelo auxiliar aprova/nega/escala), `approval_floors.py` | `OC:src/agents/exec-auto-reviewer.ts` | Presente — `plug/aprovacoes` (categorias + regra fixa; "Nesta tarefa", "Sempre") | — | — | Sim |
| Pontos onde o nosso trava mais que eles | Na conversa, o laço só avisa; nas rotinas, para na 5ª/8ª | Aviso na 10ª, bloqueio na 20ª | (1) Pausa na 4ª repetição (`_10_detector_loop.py:19`). (2) Revisor fora do ar = a ação espera a pessoa (`plug/aprovacoes/README.md`). (3) Uma recusa diz ao agente "não tente nem por outro caminho" (correto, mas sem dizer o que fazer em vez disso). (4) `consultar_sol` antes de qualquer `blocked`. Itens 2 a 4 são decisões do Matheus: manter | alto (só o 1) | P | — |

### 2.9 Mensagens, avisos e agenda

| Capacidade | Hermes | OpenClaw | A0 hoje | Impacto | Porte | Já portado? |
|---|---|---|---|---|---|---|
| Aviso no meio da tarefa | `send_message_tool.py:35` | `message`, `progress_card` | Presente — `notify_user` + `plug/whatsapp` (andamento, demora) | — | — | Sim |
| Agenda e rotinas | `H:cron/`, `H:tools/cronjob_tools.py:986` | `OC:src/agents/tools/cron-tool.ts:135` | Presente — `scheduler` + `plug/rotinas`, `agenda_confiavel`, `limpeza` | — | — | Sim |

---

## 3. Detalhes que mudam a decisão

- **Diálogos JS:** o Playwright fecha sozinho todo diálogo que não tem quem o escute (`dismiss`). No `confirm()`, a página recebe `false`. O agente vê "click ok", a tela não muda e o detector de laço entra.
  - **Cuidado no port:** aceitar um "Excluir?" é ação destrutiva. A resposta `accept` precisa passar pelo `aprovacoes`, na categoria `apagar`/`publicar`.
  - O OpenClaw trava as ações enquanto há diálogo pendente (`abortActionsBlockedByDialog`, `pw-session-dialogs.ts:131`). Isso dá um erro claro em vez de um sumiço silencioso.
- **Detector de laço × espera:** sem uma ação de espera, quem espera uma página lenta repete `content`. Na 2ª vez recebe "mude de caminho"; na 4ª, a tarefa pausa e fica esperando o Matheus. O Hermes nunca para a conversa (só avisa) e não conta como laço as ferramentas de consulta.
- **Planilha:** com `data_only=False`, uma célula `=SOMA(B2:B90)` chega como fórmula. Junto com o corte de 80 linhas, qualquer conta sobre a planilha sai errada.
  - O Hermes lê o valor guardado (`<v>`) direto do XML, sem precisar do openpyxl.
- **Código de saída:** o A0 devolve a saída quando o prompt do shell volta. `grep` sem resultado, `curl` que falhou calado e `python` que deu `exit 1` sem imprimir nada parecem todos iguais a "deu certo".
- **Regras do Hermes para outros modelos:** o Hermes não manda o bloco "Execution discipline" para o Claude ("Claude does not exhibit these modes", `prompt_builder.py:368-372`). O nosso agente é o **Haiku 5.5**: vale testar no AR Board antes de ligar, e não ligar por fé.

---

## 4. Fila priorizada (top 15, por impacto ÷ porte)

| # | Item | Impacto | Porte | De onde portar | Onde entra no nosso |
|---|---|---|---|---|---|
| 1 | **Ação `wait` no navegador** (texto aparece ou some, seletor visível, URL, carga, com teto de tempo) | alto | P | `OC:ext/browser/browser/pw-tools-core.interactions.content.ts:146-200` (`waitForViaPlaywright`) | `plug/navegador_rapido/helpers/correcoes.py` (nova ação no `_dispatch_call`/`Browser.execute`) + linha em `prompt_enxuto/helpers/indice.py` |
| 2 | **Detector de laço sem pausar na conversa**: na conversa só aviso; pausa só em rotina/ajudante e na 5ª vez; consultas (`content`, `state`, `list`, `runtime=output`, `wait`) com limite próprio; pegar o ciclo A,B,A,B | alto | P | `H:agent/tool_guardrails.py:35-46,120-133,464,491-523` + `OC:src/agents/tool-loop-detection.ts:540-660` | `plug/controle_agente/extensions/python/tool_execute_after/_10_detector_loop.py` |
| 3 | **Regras de execução** (contas, datas e contagens só por ferramenta; ler de volta depois de escrever num sistema de fora; total declarado = total contado; ids literais; "vou fazer" = fazer agora) | alto | P | `H:agent/prompt_builder.py:436-517`, `OC:src/agents/system-prompt.ts:612-620`, `OC:src/agents/promised-work-prompt.ts:2-12` | `plug/prompt_enxuto/extensions/python/system_prompt/_12_regras_base.py` (calibrar no AR Board) |
| 4 | **Leitura completa de planilha** (valores, não fórmulas; até milhares de linhas; páginas; abas escondidas fora) e o mesmo `ler` para DOCX/PDF com aviso de página escaneada | alto | P/M | `H:tools/read_extract.py:474-560,291-320`, `H:tools/file_tools.py:428-460,606` | Novo plugin `ler_arquivo` (ferramenta `ler`, com `inicio`/`limite`), ou ajuste do `read` do `office_artifact` |
| 5 | **Diálogos JS**: ouvir `dialog` em cada página; `alert` aceito e anotado; `confirm`/`prompt`/`beforeunload` ficam pendentes e o próximo resultado diz "diálogo aberto: …"; ação `dialog` aceitar/recusar e "armar" antes do clique; o aceite passa pelo `aprovacoes` | alto | M | `OC:ext/browser/browser/pw-session-dialogs.ts:17-140`, `pw-tools-core.downloads.ts:270-308`; `H:tools/browser_dialog_tool.py:17-80` | `plug/navegador_rapido/helpers/correcoes.py` (no `_start`, como o Fix 5) + `aprovacoes/helpers/revisor.py` (`ACOES_BROWSER`) |
| 6 | **Código de saída no terminal** + dica pelo texto do erro (comando faltando, `python`→`python3`, sinal 137) | alto | M | `H:tools/terminal_tool_result.py:47-113,258`, `H:tools/terminal_hints.py:1-80` | Novo gancho `tool_execute_after` para `code_execution_tool`. O código de saída precisa de um marcador `echo __A0_RC=$?` no shell local do `_code_execution` (`helpers/shell_local.py`): conferir na VM |
| 7 | **Dicas que faltam no catálogo de erros**: "cannot select options on <div>" (lista suspensa feita em JS: clique para abrir e clique na opção) e "helper-backed reference" (iframe: clique pelas coordenadas do print) | médio | P | `a0src/plugins/_browser/assets/browser-page-content.js:2507,2569,2694` (os textos); `OC:.../pw-tools-core.shared.ts` (o modelo) | `plug/controle_agente/helpers/clique.py` (`OUTROS`) |
| 8 | **Upload pelo seletor de arquivos** (site que cria o input no clique): armar `filechooser` e clicar no gatilho numa chamada | médio | P | `OC:ext/browser/browser/pw-tools-core.downloads.ts:256-268` + `pw-tools-core.interactions.content.ts:535` | `plug/navegador_rapido/helpers/correcoes.py` (junto do Fix 6) |
| 9 | **Console e rede do navegador** (`errors`/`requests` recentes) para entender "cliquei e nada aconteceu" | médio | P | `H:tools/browser_tool.py:601-625,985`; `OC:ext/browser/browser-tool-description.ts:110-115` | `plug/navegador_rapido` (ouvir `console`, `pageerror`, `requestfailed`/status ≥400 no `_start`; nova ação) |
| 10 | **Juiz do "pronto"**: no fim de um pedido com passos ou longo, um modelo barato compara o pedido (`objetivo_vivo`) com a resposta e as provas; se faltar algo, o agente continua (no máximo 1–2 vezes; se o juiz falhar, a tarefa segue) | alto | M | `H:hermes_cli/goals.py:113-140,894-960` (prompt e parse), `H:agent/turn_stop_gates.py` (devolver o turno) | Gancho em `response` (como o `_goal/tools/response.py`) dentro do `objetivo_vivo` |
| 11 | **Página grande inteira em arquivo** (o corte de 20 mil passa a dar o caminho do texto completo) | baixo/médio | P | `H:tools/browser_tool_snapshot.py:40-110` | `plug/navegador_rapido/extensions/python/message_loop_prompts_after/_21_limitar_pagina.py` |
| 12 | **Print com rótulos**: o print automático desenha o nº da ref sobre cada elemento | médio/alto | M | `OC:ext/browser/browser/screenshot-annotate.ts`, `pw-tools-core.interactions.content.ts:380`; `H:tools/browser_tool.py:1222-1290` | `plug/navegador_rapido/helpers/ver_tela.py` |
| 13 | **Troca de modelo na falha** (sobrecarga, limite, recusa, resposta vazia repetida): Haiku → Sonnet nessa chamada, com espera mínima antes de voltar | médio | M | `H:agent/error_classifier.py:34-66`, `H:agent/chat_completion_helpers.py:2086-2140`, `H:agent/fallback_cooldown.py`; `OC:src/agents/model-fallback-runner.ts:138` | `infra/vm/bedrock_proxy.py` (no 429/5xx/`ThrottlingException`, refazer com o id do Sonnet) |
| 14 | **Estouro de contexto**: no erro de tamanho, resumir o histórico e tentar de novo uma vez | médio | M | `H:agent/turn_overflow.py:128-190`, `H:agent/error_classifier.py:46-47` | `handle_exception` (como o `_error_retry`) chamando o `resumo_seguro` |
| 15 | **Perguntar com opções** (botões no celular, a tarefa espera N min e continua no mesmo turno) | médio | M | `H:tools/clarify_tool.py:136-200`; `OC:src/agents/tools/ask-user-tool.ts:457` | Ferramenta nova no `plug/whatsapp` (a ponte já faz botões: `ponte.enviar(..., botoes=)`) |

**Logo depois do top 15:**
- processo em segundo plano com aviso ao terminar (`H:tools/process_registry.py:584`), porte M;
- contrato de saída de ajudante (`H:tools/delegation_output_schema.py`), porte P;
- select/upload dentro de iframe (`OC:.../pw-role-snapshot-capture.ts:129`), porte M;
- `[new]` e `query` no snapshot, porte M;
- script que chama as ferramentas do agente em lote (`H:tools/code_execution_tool.py`), porte G;
- PDF nativo para o Claude (`OC:src/agents/tools/pdf-tool.ts:361-480`), porte M.

---

### Andamento (21/10, fim do dia)

Todos os itens foram feitos na ordem, com teste e implantados, menos o 13 e o 14, medidos e deixados de lado:

| # | Situação | Conferido com o agente de verdade |
|---|---|---|
| 1 | feito (`wait`); a conferência de argumentos barrava o `timeout` e foi corrigida (`controle_agente/helpers/argumentos.py`, `EXTRAS`) | sim, na tradução 106.PS |
| 2, 3, 4 | feitos | — |
| 5, 7, 9 | feitos | — |
| 6 | feito (código de saída + próximo passo) | sim: `sleep 50` → o agente esperou com `runtime "output"` em vez de resetar |
| 8 | feito; faltava o caso sem ref (Outlook): a ferramenta acha "Anexar arquivo" → "Navegar neste computador" | sim: e-mails NCM e tradução enviados com anexo |
| 10 | feito (juiz do pronto); calibrado com 6 casos reais, 12/12 duas vezes (`objetivo_vivo/tests/bateria_juiz.py`) | sim: aprovou uma resposta correta |
| 11 | feito (página inteira em `/a0/usr/workdir/paginas`, o corte diz a linha para o `ler`) | — |
| 12 | feito; no servidor as refs eram cópias do ajudante de DOM e a conferência do digitado (Fix 7) também não achava o campo: as duas agora acham o elemento vivo | sim: print do DuckDuckGo com os números |
| 13 | **deixado de lado**: em 20 mil chamadas, nenhuma falhou; em 7 dias o proxy viu 2 respostas 503 e as duas passaram na nova tentativa que ele já faz | — |
| 14 | **deixado de lado**: nenhum erro de contexto estourado em 7 dias (o resumo do `resumo_seguro` age antes) | — |
| 15 | feito (ferramenta `perguntar`, botões `pg:`) | sim: pergunta no Telegram, o toque chegou em 36 s e a tarefa seguiu |

Além da fila, o registro de 4 dias de chamadas do agente mostrou e foi corrigido: clique por `selector` sem ref (55 falhas, com a dica errada "a página mudou"), lista feita pelo site (17), navegador que caía (19), `type` em `<div>` (3), teclas em maiúsculas e `scroll` sem ref.

Lição do dia: testar cada correção com a chamada exata que o agente fez quando falhou (tirada do registro) e
conferir no servidor rodando; três correções passaram nos testes locais e não pegaram no servidor (marca booleana que
impede reinstalar, troca do script vivo, ajudante de DOM ausente no teste).

## 5. Conferências que ficaram para a VM

- Se o `_browser` da VM é igual a esta cópia, principalmente que não há `page.on("dialog")` nem ação de espera:
  - `docker exec agent-zero grep -rn "dialog\|wait_for_selector" /a0/plugins/_browser`
- Se o `liteparse`/`unstructured` do `document_query` está instalado e lê XLSX e PDF escaneado.
- Como o shell local do `_code_execution` acha o fim do comando (para encaixar o código de saída sem quebrar a detecção do prompt).

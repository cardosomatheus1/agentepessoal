"""Short description of each tool for the model's tool list (one or two lines: what it is for and the main arguments).

The full description (the tool's own prompt, with rules and examples) is the tool's manual: it comes once per chat in
the tool's first result (tool_execute_after/_10_manual_na_primeira.py). The general safety rules (payment, messages
to third parties, deleting, captcha, secrets) stay in every call: system_prompt/_12_regras_base.py.

A tool missing here keeps its full description. Keep each line short: the whole list goes in every model call."""

CURTAS: dict[str, str] = {
    # --- Agent Zero
    "response": "Resposta final à pessoa (encerra a tarefa). `text`: a resposta, em Markdown, curta e direta.",
    "notify_user": "Aviso no meio de uma tarefa longa (chega no celular); a tarefa continua. `message`, opcional `title`, `type`.",
    "code_execution_tool": "Roda comandos. `runtime` terminal|python|nodejs|output (acompanhar o que está rodando)|reset, `code`, "
                           "`session` (padrão 0). Sessão travada: mesma `session` com `reset: true`. Programa interativo: `input`.",
    "input": "Manda teclas a um programa interativo do terminal. `keyboard`, `session`.",
    "text_editor": "Lê e escreve arquivos de texto/Markdown com linhas numeradas. `action` read (`path`, opcional `line_from`, "
                   "`line_to`) | write (`path`, `content`) | patch (`path`, `edits`: lista de {from, to, content}).",
    "browser": "Navegador com página renderizada (formulários, login, cliques). `action` open|list|navigate|content|click|type|"
               "type_submit|scroll|screenshot|evaluate|close… com `browser_id`, `url`, `ref`/`selector`, `text`. Para fluxos "
               "longos, carregue a skill `browser-automation`. Texto simples: prefira `pesquisar`/`search_engine`.",
    "search_engine": "Busca na web (lista de resultados). `query`. Para pesquisa com várias fontes use `pesquisar`.",
    "document_query": "Lê/resume/compara documentos (PDF, Office, HTML, arquivo grande) e responde perguntas sobre eles. "
                      "`document` (caminho ou URL, ou lista), opcional `queries` (lista de perguntas). Imagem: prefira `vision_load`.",
    "vision_load": "Carrega poucas imagens na conversa para você ver. `paths` (lista). Mais de ~5 imagens: `analisar_imagens`.",
    "call_subordinate": "Delega uma subtarefa a um ajudante. `message` (objetivo, dados e critério de pronto), `reset` (true = "
                        "tarefa nova e limpa), opcional `profile`, `name`, `context_id`, `attachments`.",
    "parallel": "Roda chamadas independentes ao mesmo tempo. `tool_calls`: lista de {tool_name, tool_args}; `wait` (padrão "
                "true); ou `action` await|collect|cancel com `job_ids`.",
    "skills_tool": "Skills (instruções sob demanda, rotinas). `action` search (`query`) | list | load (`skill_name`) | "
                   "read_file (`skill_name`, `file_path`).",
    "scheduler": "Tarefas agendadas. `action` list_tasks|find_task_by_name|show_task|run_task|update_task|delete_task|"
                 "create_scheduled_task|create_planned_task|create_adhoc_task|wait_for_task, com `name`, `uuid`, `prompt`, "
                 "`schedule` (cron: minute/hour/day/month/weekday/timezone), `plan`. Confira as existentes antes de criar.",
    "wait": "Espera um tempo. `seconds`/`minutes`/`hours` ou `until` (data e hora).",
    "memory_load": "Busca na memória de longo prazo desta conversa. `query`, opcional `threshold`, `limit`, `filter`.",
    "memory_save": "Guarda um fato durável na memória. `text`, opcional `area`. Fato sobre a pessoa vai na `ficha`; decisão, na `decisao`.",
    "memory_delete": "Apaga memórias pelo id. `ids` (separados por vírgula).",
    "memory_forget": "Apaga as memórias que combinam com a busca. `query`, opcional `threshold`, `filter`.",
    "behaviour_adjustment": "Muda as regras de comportamento permanentes do agente. `adjustments` (o que mudar).",
    "a2a_chat": "Conversa com outro agente remoto (FastA2A). `agent_url`, `message`, opcional `attachments`, `reset`.",
    "goal": "Objetivo da conversa (modo objetivo): `action` get|create (`objective`)|update (`status` complete|blocked, "
            "`note`). Só quando a pessoa pedir um objetivo.",
    "office_artifact": "Cria/abre/lê/edita/exporta documentos Office (odt ods odp docx xlsx pptx). `action` create|open|read|"
                       "edit|export…, `kind`, `title`, `format`, `content`, `path`/`file_id`.",
    "delegar": "Você orquestra: dá UMA tarefa ao Hermes (código, dados, planilhas, PDFs, arquivos) ou ao OpenClaw "
               "(pesquisa na web, vários passos, segunda opinião), com terminal, internet e navegador numa máquina isolada "
               "sem contas dele. `motor` auto|hermes|openclaw, `tarefa` (brief; entregas em /trabalho/saida/), `arquivos`, "
               "`minutos`, `esperar`; `acao` estado|parar `id`. Contas, mensagens e o que é curto: você.",
    "text_delegate": "Pede a Hermes ou OpenClaw uma crítica rápida só de texto, sem ferramentas (para trabalho de verdade use "
                     "`delegar`). `engine` hermes|openclaw, `task` (autossuficiente, até 10 mil caracteres; sem senhas).",
    # --- plugins deste repositório
    "prospeccao": "Prospecção da Raiz, só pela @raiz.connect (nunca o perfil pessoal). Tudo pré-aprovado pelo Matheus dentro "
                  "dos limites do dia; o revisor confere cada texto: reprovado volta com \"REESCREVA\" e o motivo (corrija só "
                  "esse item); execute só ações entregues como APROVADAS, com o texto exato. Regras e modelos: acao \"playbook\"; no navegador: skill `prospeccao-instagram`. `acao`: playbook | contexto | registrar | rejeitar | fontes | fontes_instagram | conferir_estoque | estoque_conferido | buscar_script | avaliar_api | perfis_script | avaliar_perfis | limite_consulta | liberar_consultas | liberar_bloqueio | scripts_conta | propor | comentar | comentado | pular_comentario | editar | caixa_lida | ler_direct | direct_script | falha | proxima | resultado | etapa | entrou | cartao | assumir | devolver | apagada | importar_lista | variante | token_meta | hoje | metricas. O manual completo vem depois do primeiro resultado.",
    "conversa_externa": "Fala com lojas e negócios pelo WhatsApp DA PRÓPRIA PESSOA, em nome dela, e vigia a resposta. `acao` "
                        "estado|conectar|abrir|enviar|ler|esperar_dono|encerrar|listar|responder_por_mim|sugerir_resposta… "
                        "Marcar, reservar, aceitar preço ou passar dado pessoal só com o sim dela (`esperar_dono`, `confirmado`); "
                        "nunca pague.",
    "celular": "Celular Android virtual da pessoa, num passo: faz a ação e devolve o texto da tela. `acao` ver|tocar (x, y)|"
               "tocar_texto (texto)|tocar_longo|deslizar (direcao)|digitar (texto, enviar)|voltar|inicio|enter|apagar|abrir "
               "(pacote)|esperar (segundos), ou `acoes` (lista, até 15). \"NÃO MUDOU\" = escolha outra ação.",
    "salvar_rotina": "Rotinas (viram skills). `acao` salvar (`nome`, `descricao`, `passos`, `verificar`, `entregar`, `aprovacao`, "
                     "`gatilhos`) | corrigir (`nome`, `correcao`) | ler (`nome`) | ajustar (`nome`, `trecho`, `novo`, `versao` lida).",
    "me_mostre": "Grava a pessoa fazendo uma tarefa no Navegador desta conversa para virar rotina. `acao` iniciar|parar.",
    "concorrentes": "Vigia de concorrentes da Raiz. `acao` coletar (lê as fontes e devolve o que é novo) | ultima | instagram | "
                    "listar | adicionar | fonte | tirar_fonte | grupo | remover. Fonte \"Sem cobertura\" não quer dizer sem novidade.",
    "ferramentas_extras": "As ferramentas fora desta lista (conectores Google/GitHub e as de uso raro; instrução que manda "
                          "usar uma que você não tem: está aqui). `acao` buscar (`texto`) | usar (`nome`, `args`).",
    "consultar_sol":"Conselho de um modelo mais forte (só aconselha; não é autorização da pessoa). `pergunta`, `contexto` "
                     "(o caso completo: ele não vê a conversa), opcional `imagens`. Até ~3 por tarefa.",
    "pesquisar": "Pesquisa na web em UMA chamada (~1–2 min, várias buscas, páginas e vídeos em paralelo, síntese com fontes). "
                 "`pergunta`, opcional `buscas`, `profundidade`. Use para qualquer pesquisa com várias fontes.",
    "rascunho": "Rascunho de resposta de e-mail no estilo da pessoa, entregue no celular dela (quem envia é ela; você nunca "
                "envia). `acao` criar (`para`, `assunto`, `texto`, `pedido`, `referencia`) | listar | amostras | estilo | estilo_salvar.",
    "reuniao": "Briefing antes e pergunta do pós-reunião de uma reunião da agenda. `acao` agendar (`evento_id`, `titulo`, "
               "`inicio`, `fim`, `participantes`, `local`) | cancelar | listar | pos_registrado (`evento_id`, `resumo`, `decisoes`).",
    "contas": "Contas e boletos com vencimento (lembretes saem sozinhos). `acao` salvar (`descricao`, `vencimento` AAAA-MM-DD, "
              "`valor`, `fonte`, `codigo`) | listar | paga | ignorar (`id`). Nunca pague.",
    "iniciativa": "Mensagens por iniciativa própria. `acao` contexto | candidatos (`candidatos`: 3–5 {titulo, tipo, nota, "
                  "porque}) | enviar (`titulo`, `texto`, `tipo`, opcional `arquivo`) | aprender (`aprendizado`).",
    "ler": "Lê arquivo inteiro em páginas: planilha (valores, não fórmulas), csv, docx, pdf, texto. `caminho`, opcional "
           "`inicio`, `limite`, `aba`.",
    "analisar_imagens": "Analisa muitas imagens uma a uma e devolve texto (e notas em arquivo). `caminhos` (arquivos, pastas "
                        "ou padrões), `pergunta`, opcional `contexto`. Use com mais de ~5 imagens.",
    "decisao": "Decisões da pessoa que valem até ela mudar. `acao` registrar (`tema`, `decisao`, `tipo` decisao|permissao|"
               "proibicao|preferencia, `citacao` = as palavras dela, `area`) | listar | historico | revogar (`id`, `motivo`).",
    "ficha": "Ficha \"Sobre\" de quem fala (fatos duradouros). `acao` add (`texto`) | patch (`trecho`, `novo`) | remove "
             "(`trecho`) | listar. Ordem ou permissão vai na `decisao`.",
    "lembrar": "Busca nas conversas antigas de quem fala. `busca` (palavras-chave), opcional `limite`.",
    "fios": "Fios soltos (o que ficou em aberto). `acao` listar | coletar (`horas`) | salvar (`fios`: lista de {titulo, dono, "
            "prazo, prioridade, proximo_passo, ligacoes, area}) | resolver (`resolvidos`/`id`) | adiar (`id`, `ate`) | avisar (`id`).",
    "cerebro": "Segundo Cérebro do Matheus (a Pasta). `acao` consultar (`texto`: responde \"o que decidi/onde parou/quem é\") | "
               "assunto (`titulo`/`ref`, `onde_parou`, `estado`, `area`) | assuntos | desfazer (`ref` ou \"ultimo\", `motivo`) | "
               "reuniao (`titulo`, `data`, `participantes`, `resumo`, `decisoes`, `proximos`) | "
               "contexto (entrevista: `secao`, `conteudo`, `aprovado`) | raiz (ler antes de algo da Raiz) | nota_do_dia | auditoria.",
    "videos_em_alta": "Vídeos do YouTube mais vistos das últimas N horas sobre um tema, assistidos. `tema`, opcional "
                      "`consultas`, `quantidade`, `horas`, `assistir`.",
    "assistir_video": "Assiste um vídeo inteiro (imagem e áudio) e descreve com os tempos. `url` ou `caminho`, opcional "
                      "`pergunta`, `modo` (\"rapido\" = só legendas). Não use o navegador para vídeo.",
    "criar_gatilho": "Gatilhos (endereço que um serviço chama quando algo acontece). `acao` criar (`nome`, `instrucao`) | listar | apagar.",
    "whatsapp_enviar": "Manda ao celular do dono desta conversa (só a ele) um arquivo ou recado. `arquivo` (caminho em /a0/usr), "
                       "opcional `legenda`, `texto`. A resposta final já chega sozinha.",
    "pedir_codigo": "Pede à pessoa, pelo celular, um código de uso único (2FA/SMS) e espera até 10 min. `pergunta` (site e qual código).",
    "whatsapp_guardar_token": "Guarda no cofre, sem você ler, o token ou a chave secreta visível na página da Meta. `campo` token|app_secret.",
    "terminal_isolado": "O computador Linux separado de um convidado. `acao` rodar (`comando`, `tempo`) | enviar (`arquivo`) | "
                        "trazer (`caminho`).",
    "especialista": "Especialistas (o Matheus não fala com eles). Antes de publicar ou mandar algo público: `acao` criticar "
                    "(`tipo` post|carrossel|oferta|landing|mensagem, `material`: texto ou JSON com `imagens`); reprovado não "
                    "sai. Peça visual: `acao` desenhar (`briefing`) devolve ficha, arquivos e crítica. `papel` critico|designer.",
    "conteudo": "Posts da @raiz.connect. `acao` agenda (`dias`) | arquivos (`data`) | desempenho (`dias`) | propor_semana | semana | aprovar_semana (`semana`, `numeros`) | liberar_post (só com ordem dele).",
    "monitor": "Monitor de evento conferido pelo Radar. `acao` criar (`fonte` gmail|agenda, `condicao`, `o_que_fazer`) | listar | remover (`id`).",
    "livro": "Livro de ações (o que o agente fez no mundo, imutável). `acao` hoje (`dias`) | conferir. Use em vez de responder de memória.",
    "tarefa_limite": "Fim e histórico de uma tarefa agendada. `uuid`, `acao` ver | terminar_em (`termina_em`: \"7d\" ou data) | permanente.",
    "cofre_descrever": "Registra para que serve uma senha do cofre (nunca o valor). `nome`, `para` (site e conta).",
}

# Tools whose result must never carry the manual: the response text goes to the person as it is.
SEM_MANUAL = {"response"}
MIN_GANHO = 200  # characters: a description that is already short stays as it is

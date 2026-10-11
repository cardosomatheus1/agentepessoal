# Agente pessoal — passagem para a conta nova do Claude

Retrato de 10/10/2026. A conversa antiga do Claude Code não passa para a conta nova: tudo o que importa está neste
repositório (código, este documento e `infra/operador/`) e na própria máquina do agente, que continua igual.

## O que é

O **agente pessoal do Matheus** é um Agent Zero rodando numa EC2 da AWS (conta `964862484412`, `us-east-1`), com
plugins próprios em `infra/vm/plugins/`. Ele fala com o Matheus pelo **Telegram** (e WhatsApp), roda rotinas
agendadas, navega com um navegador próprio por pessoa e usa modelos via Bedrock/OpenAI-compatível.

Nada do agente depende da conta do Claude: ele continua rodando durante e depois da troca.

| Peça | Onde | Observação |
|---|---|---|
| VM do agente | EC2 `i-0498b4f39560b01a9` | Acesso só por SSM (`infra/operador/vmcmd.py`) |
| Agent Zero | contêiner `agent-zero` | Dados em `/opt/a0/usr` (no contêiner, `/a0/usr`) |
| Plugins | `/opt/a0/usr/plugins/<nome>` | Fonte: `infra/vm/plugins/` deste repo |
| Proxy de modelos | `/opt/agentepessoal/bedrock_proxy.py`, serviço `agentepessoal-proxy`, porta 8787 | Luna (`openai.gpt-6-luna`), Haiku 5.5, Polly (voz), token do GCP |
| Ponte do celular | `/opt/agentepessoal/ponte_whatsapp.py`, serviço `agentepessoal-whatsapp`, porta 8789 | Telegram ligado ao login `matheus`; cofre `/senha` |
| Agendador | `/opt/a0/usr/scheduler/tasks.json` | Mexer só pelas APIs `scheduler_task_*` |
| Tarefas permanentes | `/opt/a0/usr/agenda/limites.json` | Senão o `agenda_confiavel` desativa após 30 dias |
| Backups/arquivos temporários | S3 `agentepessoal-backup-964862484412` (`tmp/`) | Usado para levar arquivos para a VM |

## Estado da troca (10/10, ~19h UTC)

- Conta nova: **sejaorbyte@gmail.com** (plano Max). GitHub e Linear conectados.
- Ambiente de nuvem criado: **"Agente pessoal e NEXOS"** (rede completa) com `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` e `A0_SENHA` — digitados pelo agente a partir do cofre dele
  (`CLAUDE_ENV_*`), sem os valores passarem pelo chat. A primeira coisa da sessão nova é conferir que funcionam
  (`aws sts get-caller-identity`). Depois disso, apagar os parâmetros temporários
  `/agentepessoal/transferencia/*` do SSM.
- **Branch**: todo o trabalho desta conversa está no branch `ccr-bcbe3101-9u4klv` (não mesclado no principal).
  A sessão nova parte dele.
- O navegador do agente está logado no claude.ai como sejaorbyte; a rotina 2FQESGed (acompanhar o Claude Code)
  vigiava a conta antiga e passa a ver a conta nova.
- IA Business: ver o branch `claude/handoff-conta-nova` do repositório `cardosomatheus1/aibusiness`.
- Máquina de build do IA Business: `infra/operador/vmcmd.py` serve com `VM_ID=i-08adac4830ec57e5a` (ros-dev-construcao,
  usuário `ec2-user`). A Main Opus roda no tmux `opus` (`/home/ec2-user/opus_rc.sh`, sessão única na árvore do
  principal), que o serviço `claude-main-opus` sobe sozinho quando a máquina liga (ver "Parada de 11/10").

## Parada de 11/10 e o que mudou

- **O que houve:** a Main Opus terminou o turno às 00:29 UTC perguntando se seguia numa sessão nova. A
  orquestradora a viu como "desconectada" e não mandou seguir. Sem atividade, a vigia da máquina
  (`/opt/ros-construcao/vigia.sh`, métrica `ROS/Construcao SessaoViva`) publicou 0 a partir das 00:50, e o alarme
  `ros-dev-construcao-ociosa` (60 min) **desligou a máquina às 01:50**. O Controle Remoto caiu junto, e o app passou
  a mostrar "Ambiente excluído". A VM do agente travou em paralelo, ao acordar da hibernação às 04:55
  (status "impaired", sem SSM).
- **Correções:**
  - `opus_rc.sh` virou um laço que **reata a mesma sessão** (`claude remote-control --session-id <id do
    bridge-pointer.json>`) e só abre outra se a reatada falhar.
  - O serviço `claude-main-opus.service` sobe o laço no boot.
  - Tudo roda com `--permission-mode bypassPermissions`. O Matheus pediu: o modo auto negava os comandos e as
    aprovações vindas da orquestradora.
  - `/home/ec2-user/.claude/settings.json` usa `defaultMode bypassPermissions`. Os hooks do repo continuam
    valendo.
  - `/home/ec2-user/.claude/CLAUDE.md` traz a **delegação**: mensagens da orquestradora valem como do Matheus
    (aprovações e HUMs), com os limites de deploy, pagamento, segredo e push.
  - O serviço `claude-remote-control` (spawn=worktree) também passou para bypassPermissions.
  - A orquestradora foi instruída a ligar a máquina (`aws ec2 start-instances`) se a encontrar parada e a mandar a
    Main Opus continuar.
  - Novo alarme `agentepessoal-vm-travada`: reinicia a VM do agente após 5 min de falha na checagem de status.

## O que a sessão nova precisa ter

1. **GitHub**: a conta nova conectada ao usuário `cardosomatheus1`, com acesso a `cardosomatheus1/agentepessoal`.
2. **Ambiente na nuvem** (claude.ai/code → ambiente → novo), com:
   - variáveis `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION=us-east-1` (a mesma credencial IAM usada
     hoje — o Matheus copia do ambiente antigo ou gera outra no IAM; nunca colar no chat);
   - `A0_SENHA` = senha do login `matheus` na interface do Agent Zero (o Matheus sabe; não vai para o git);
   - credenciais de rede, se quiser as mesmas de hoje: OpenAI, Tavily, TypeSafe (Jev) e Bedrock.
3. Dependências na sessão: `pip install boto3 playwright` (o Chromium já vem no contêiner do Claude Code).

## Como operar (scripts em `infra/operador/`)

As permissões em `.claude/settings.json` liberam esses scripts sem pedir aprovação (o modo automático barrava o
login na interface do agente com `A0_SENHA`). Rode-os sempre pelo caminho `python3 infra/operador/<script>` a
partir da raiz do repositório, para casar com as regras. `buildcmd.py` é o `vmcmd.py` da máquina de build do IA
Business (`ros-dev-construcao`, `i-08adac4830ec57e5a`); para mandar um script grande a ela, use base64 dentro do
comando (a máquina não lê o bucket S3).

| Script | Para quê |
|---|---|
| `vmcmd.py '<comando>'` | Roda um comando na VM do agente por SSM (até ~10 min) |
| `mandar_msg.py <arquivo> [chat]` | Manda uma mensagem ao agente como `matheus` (chat novo se não passar o id) |
| `rodar_testes.py [so\|LIMPAR]` | Suíte do plugin `auxiliar` |
| `rodar_testes_pro.py` | Suíte do plugin `prospeccao` (29 testes) |
| `infra/vm/plugins/prospeccao/rodadas.py [--criar] [buscar\|executar\|semana\|resumo]` | Cria/atualiza/dispara as rodadas da prospecção |
| `tarefas_auxiliar.py`, `resumo_novo.py` | Tarefas do auxiliar e do resumo diário |
| `resetar_chat.py <ctx>`, `apagar_chat.py` | Limpar conversas de teste |
| `ver_chat.sh <ctx>` (rodar na VM) | Últimas mensagens de uma conversa do agente |

**Implantar um plugin**: `tar czf pro.tgz -C infra/vm/plugins <plugin>` → `aws s3 cp` para `tmp/` do bucket →
`vmcmd.py` copiando para `/opt/a0/usr/plugins/` → `docker exec agent-zero curl -s -X POST http://127.0.0.1:80/api/cache_reset`.
Serviços do host (`bedrock_proxy.py`, `ponte_whatsapp.py`): `install -m 755` em `/opt/agentepessoal/` e
`systemctl restart agentepessoal-proxy|agentepessoal-whatsapp`.

**Mandar algo ao Telegram do Matheus** (na VM): carregar `/a0/usr/plugins/whatsapp/helpers/ponte.py` e chamar
`enviar("matheus", texto, tipo="resposta"|"urgente"|"progresso")`. Logins `teste_*` só gravam em
`/a0/usr/testes/celular.jsonl`.

## Memória e limpeza (incidente de 10/10)

O navegador do agente acumulava abas de todas as conversas e rodadas (75 processos, 11,8 GB): a VM congelou por
~30 min (SSM e túnel fora do ar) e foi reiniciada com `aws ec2 reboot-instances`. Desde então:

- **plugin `limpeza`** (`infra/vm/plugins/limpeza`): a cada 5 min fecha as abas de conversas paradas (20 min; 5 min
  com < 3 GB livres; todas as não rodando com < 1,5 GB). Log: `/opt/a0/usr/limpeza/log.jsonl`.
- **`memguard`** (`infra/vm/memguard.sh`, timer `agentepessoal-memguard.timer`, no `setup.sh`): memória < 700 MB por
  3 min → `docker restart agent-zero`. Log: `/var/lib/agentepessoal/memguard.log`.
- **skill `manutencao-maquina`**: instrui o agente a fechar as abas que abre e a conferir a memória antes de tarefas
  longas.
- **Se a VM travar mesmo assim** (comandos do `vmcmd.py` estourando o tempo, SSM "ConnectionLost", site 530): veja
  CPU/rede no CloudWatch; se não voltar em ~10 min, `aws ec2 reboot-instances --instance-ids i-0498b4f39560b01a9`
  (tudo sobe sozinho; o endereço do agente muda e é atualizado em `/agentepessoal/agent-url`). Depois confira as
  rotinas: as que estavam rodando no reboot podem falhar uma vez (o proxy sobe depois).

## Prospecção: velocidade e leitura de respostas (estado de 10/10, noite)

- **Achar contas:** `buscar_script` (busca do Instagram por termo, numa chamada) — funciona.
- **Avaliar:** `perfis_script` (5 perfis por chamada, 3 s entre elas) — em 10/10 o Instagram devolveu 429 depois de um
  dia de muito uso; a ferramenta pausa 15 min e o agente cai para abrir os perfis. Conferir nas rodadas de 11/10.
- **API oficial (business discovery):** código pronto (`avaliar_api`, `token_meta`), app **"Raiz Prospecção"** criado
  (ID 1616408683299666) com pages_show_list, pages_read_engagement e instagram_basic. Falta: a Página Raiz Connect
  pertence ao portfólio e só aparece com `business_management`, que esse tipo de app não oferece — precisa de um app
  do tipo "Empresa" com Login do Facebook para Empresas, ou adicionar o Matheus como admin direto da Página.
- **Respostas no Direct:** a tela da caixa de entrada não entrega a lista como texto e a API web do Direct deu 404.
  Método que funciona (testado): o `contexto` lista as conversas a conferir e o agente abre cada uma (perfil →
  Mensagem). Notificações (respostas em comentários) são lidas pela página de notificações.
- **WhatsApp do agente:** token invalidado pelo Facebook (sessão redefinida) foi trocado em 10/10; vale até 09/12/2026.
- **Rotinas presas após reboot:** o plugin `limpeza` volta para "idle" rotinas "running" há mais de 90 min sem trabalho vivo.

## Rotinas agendadas do agente (10/10)

| Id | Nome | Quando (America/Bahia) |
|---|---|---|
| nW924Nkj | 📰 Resumo do dia | 7:45 |
| HL76nfIg | 🔎 Radar (Gmail e Agenda) | 8:40, 11:40, 14:40, 17:40, 20:40 |
| 8COQyGTD | 🧵 Fios soltos | 9:10, 13:10, 18:10 |
| 2FIQTI0o | 💡 Iniciativa | 9:37 a 19:37, de 2 em 2 h |
| bMU33E1T | 🗓️ Revisão da semana | domingo 19:47 |
| INZXd4Gi | ✍️ Meu estilo de escrita | dia 1, 10:13 |
| lu1v3ube | Radar diário de IA (YouTube) | 5:00 |
| laMIuaPt | 🎯 Prospecção — buscar | 9:23, todo dia |
| F9Ku9frw | 🎯 Prospecção — executar | :20 e :50, 9h–19h, todo dia |
| aPzaUZiW | 🎯 Prospecção — resumo do dia | 20:17 |
| gOqdMBE3 | 🎯 Prospecção — semana | segunda 8:41 |
| H8kWmYP1 | Nexos — acompanhar fase 2 e lead | 0, 6, 12, 18 h |
| 2FQESGed | Acompanhar Claude Code — MVP | de hora em hora — **dependia do login antigo do claude.ai no navegador do agente**; o navegador agora está na conta `sejaorbyte@gmail.com` |

## Frentes de trabalho e onde pararam

- **Iniciativa** (`iniciativa`): mensagens proativas com revisor Luna; arquivos vão anexados (md → PDF).
- **Auxiliar** (`auxiliar`): rascunhos de e-mail no estilo do Matheus, briefing antes e pergunta depois de reunião,
  vigia do Google por Apps Script (**o Matheus ainda precisa instalar o `vigia_google.gs`**), esperando terceiros,
  contas com lembrete, revisão semanal, resumo da manhã em áudio (Polly Camila generative, só generative).
- **Cofre** (`cofre`): senhas com descrição de uso; o agente usa direto e só para em captcha, 2FA ou senha errada.
- **Prospecção Raiz Connect** (`prospeccao`) — a frente mais ativa:
  - o COMO no Instagram vive na skill `infra/vm/skills/prospeccao-instagram/SKILL.md` (instalada em
    `/opt/a0/usr/skills/`); as rodadas só mandam carregar a skill e seguir a seção certa; pedidos avulsos usam a mesma skill;
  - conta **@raiz.connect** (nunca a pessoal @cardosomatheus1); limites do piloto 8 aquecer / 5 DMs / 5 lembretes
    por dia na 1ª semana, depois 20/12/10;
  - nota do lead 0–100 calculada pelo código a partir das evidências (corte 55);
  - aquecer, 1ª mensagem e lembrete **pré-aprovados pelo Matheus** dentro dos limites, cada texto passa por um
    revisor Luna (bateria `tests/bateria_revisor.py`: 30/30); respostas e parceiros continuam com o ✅ dele;
  - 1ª mensagem: variante A = pergunta sobre como precifica (sem oferta, sem link); B = oferta do cálculo grátis;
  - links permitidos só no lembrete e nas respostas: calculadora
    `raizconnect.com.br/materiais/precificacao/calculadora` e simulador `.../materiais/quanto-sobra-no-delivery`;
  - cada rodada de execução lê o Direct e as notificações e registra (`conferido`) antes de executar; resposta em
    comentário ou no Direct avisa o Matheus no Telegram na hora (uma vez por resposta);
  - estado de 10/10: 9 leads (Salvador), 8 aquecidos, @zen.marmitas aprovado na fila; primeiras DMs na segunda 12/10;
    ninguém respondeu ainda.
- **Faturamento Vertex/Gemini**: liberado (R$ 0 de saldo devedor, orçamento de R$ 50).
- **Análise dos anúncios da Raiz** (só leitura): iscas com muito LPV e pouco cadastro; sugestões no histórico
  (calculadora como destino dos anúncios; Raio-X e 15 erros marcam "às vezes" como erro inteiro).

## Regras que o Matheus deu (valem sempre)

- Segredos só no cofre/SSM; nunca no chat, em arquivo ou no git. Nunca repetir senha ou token.
- Nada de pagamento, campanha com gasto ou meio de pagamento; contas de anúncio reais e o app Barber Dock: só leitura.
- Mensagem a terceiros só com aprovação (exceto a prospecção pré-aprovada, dentro dos limites).
- Não resolver nem contornar captcha; o Matheus resolve pela tela do navegador do agente.
- Sem identificador de modelo em commits; push só no branch de trabalho; PR só se ele pedir.
- Respostas a ele em português, curtas e objetivas; avisos só do que importa.

## Prompt para a primeira mensagem da sessão nova

```
Você continua o projeto do agente pessoal do Matheus (repo cardosomatheus1/agentepessoal), vindo de outra conta do
Claude. Faça git fetch origin ccr-bcbe3101-9u4klv e trabalhe a partir dele. Leia docs/HANDOFF_CONTA_NOVA.md e docs/CONTEXTO_COMPLETO.md inteiros antes de qualquer coisa e siga as regras deles. Confira o acesso:
aws sts get-caller-identity; python3 infra/operador/vmcmd.py 'docker ps --format "{{.Names}} {{.Status}}"'.
Depois rode python3 infra/operador/rodar_testes_pro.py e me diga em 3 linhas o estado (VM, testes, prospecção).
Responda sempre em português, curto.
```
